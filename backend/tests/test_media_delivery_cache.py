import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.auth import require_library_write
from app.config import generate_api_key, settings
from app.database import Base, get_db
from app.main import app
from app.models import ApiKeyPolicy, AppSetting, Image
from app.services.api_key_service import API_KEY_POLICY_MIGRATION_KEY, api_key_hash
from app.services.storage_service import ensure_storage_dirs


class MediaDeliveryCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-media-delivery-")
        self.original_storage_path = settings.storage_path
        self.original_accel_prefix = settings.media_accel_redirect_prefix
        self.original_browser_cache = settings.media_public_browser_cache_seconds
        self.original_shared_cache = settings.media_public_shared_cache_seconds
        self.original_api_keys = settings.api_keys
        settings.storage_path = Path(self.temp_dir.name) / "storage"
        settings.media_accel_redirect_prefix = ""
        settings.media_public_browser_cache_seconds = 604800
        settings.media_public_shared_cache_seconds = 2592000
        ensure_storage_dirs()

        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'media.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

        def override_get_db():
            db = self.SessionTesting()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_library_write, None)
        settings.storage_path = self.original_storage_path
        settings.media_accel_redirect_prefix = self.original_accel_prefix
        settings.media_public_browser_cache_seconds = self.original_browser_cache
        settings.media_public_shared_cache_seconds = self.original_shared_cache
        settings.api_keys = self.original_api_keys
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _image(self, *, is_public=True, rating="safe", preview=False) -> Image:
        with self.SessionTesting() as db:
            image = Image(
                filename="media.webp",
                original_filename="media.png",
                file_path="original/media.webp",
                thumbnail_path="thumbnail/media.webp",
                preview_path="preview/media.webp" if preview else None,
                media_version=1,
                width=32,
                height=24,
                orientation="landscape",
                file_size=13,
                mime_type="image/webp",
                sha256=("a" if is_public else "b") * 64,
                rating=rating,
                is_public=is_public,
            )
            db.add(image)
            db.commit()
            db.refresh(image)
            image_id = image.id
        (settings.storage_path / "original" / "media.webp").write_bytes(b"original-data")
        (settings.storage_path / "thumbnail" / "media.webp").write_bytes(b"thumbnail-data")
        if preview:
            (settings.storage_path / "preview" / "media.webp").write_bytes(b"preview-data")
        with self.SessionTesting() as db:
            return db.get(Image, image_id)

    def _configure_keys(self) -> tuple[str, str]:
        upload_key = generate_api_key()
        reader_key = generate_api_key()
        settings.api_keys = f"upload:{upload_key},reader:{reader_key}"
        with self.SessionTesting() as db:
            db.add(AppSetting(key=API_KEY_POLICY_MIGRATION_KEY, value="completed"))
            db.add_all(
                [
                    ApiKeyPolicy(
                        key_hash=api_key_hash(upload_key),
                        name="upload",
                        scopes_json=json.dumps(["uploads:manage"]),
                    ),
                    ApiKeyPolicy(
                        key_hash=api_key_hash(reader_key),
                        name="reader",
                        scopes_json=json.dumps(["library:read"]),
                    ),
                ]
            )
            db.commit()
        return upload_key, reader_key

    def test_public_media_uses_versioned_cache_headers_and_etag(self):
        image = self._image(preview=True)
        response = self.client.get(f"/media/{image.id}/thumbnail/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"thumbnail-data")
        self.assertEqual(
            response.headers["cache-control"],
            "public, max-age=604800, s-maxage=2592000, must-revalidate",
        )
        self.assertEqual(response.headers["cross-origin-resource-policy"], "cross-origin")
        self.assertEqual(response.headers["x-agms-media-variant"], "thumbnail")
        self.assertTrue(response.headers["etag"].startswith('"'))

        not_modified = self.client.get(
            f"/media/{image.id}/thumbnail/1",
            headers={"If-None-Match": response.headers["etag"]},
        )
        self.assertEqual(not_modified.status_code, 304)
        self.assertEqual(not_modified.content, b"")

        wildcard_not_modified = self.client.get(
            f"/media/{image.id}/thumbnail/1",
            headers={"If-None-Match": "*"},
        )
        self.assertEqual(wildcard_not_modified.status_code, 304)

        head = self.client.head(f"/media/{image.id}/thumbnail/1")
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b"")
        self.assertEqual(head.headers["etag"], response.headers["etag"])

        stale = self.client.get(f"/media/{image.id}/thumbnail/2")
        self.assertEqual(stale.status_code, 404)
        self.assertIn("no-store", stale.headers["cache-control"])

    def test_preview_falls_back_to_original_and_legacy_route_remains_available(self):
        image = self._image()
        response = self.client.get(f"/media/{image.id}/preview/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"original-data")
        self.assertEqual(response.headers["x-agms-media-variant"], "original")

        legacy = self.client.get(f"/storage/{image.thumbnail_path}")
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(legacy.content, b"thumbnail-data")
        self.assertIn("s-maxage=2592000", legacy.headers["cache-control"])

    def test_private_and_hidden_media_require_admin_and_are_never_cached(self):
        private_image = self._image(is_public=False)
        self.assertEqual(self.client.get(f"/media/{private_image.id}/original/1").status_code, 404)

        upload_key, reader_key = self._configure_keys()
        denied = self.client.get(
            f"/media/{private_image.id}/original/1",
            headers={"Authorization": f"Bearer {upload_key}"},
        )
        self.assertEqual(denied.status_code, 403)

        private_response = self.client.get(
            f"/media/{private_image.id}/original/1",
            headers={"Authorization": f"Bearer {reader_key}"},
        )
        self.assertEqual(private_response.status_code, 200)
        self.assertEqual(private_response.headers["cache-control"], "private, no-store, max-age=0")
        self.assertEqual(private_response.headers["cross-origin-resource-policy"], "same-origin")

    def test_access_change_rotates_version_and_old_origin_url_stops_working(self):
        image = self._image()
        app.dependency_overrides[require_library_write] = lambda: {"sub": "admin"}
        update_response = self.client.put(f"/api/images/{image.id}", json={"rating": "hidden"})
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["media_version"], 2)
        self.assertEqual(self.client.get(f"/media/{image.id}/original/1").status_code, 404)
        self.assertEqual(self.client.get(f"/media/{image.id}/original/2").status_code, 404)

        _, reader_key = self._configure_keys()
        admin_response = self.client.get(
            f"/media/{image.id}/original/2",
            headers={"Authorization": f"Bearer {reader_key}"},
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertIn("no-store", admin_response.headers["cache-control"])

    def test_accel_redirect_and_lookup_indexes_are_available(self):
        image = self._image()
        settings.media_accel_redirect_prefix = "/_agms_media"
        response = self.client.get(f"/media/{image.id}/thumbnail/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-accel-redirect"], "/_agms_media/thumbnail/media.webp")

        image_indexes = {item["name"] for item in inspect(self.engine).get_indexes("images")}
        self.assertIn("ix_images_file_path", image_indexes)
        self.assertIn("ix_images_public_rating_created", image_indexes)
        character_indexes = {item["name"] for item in inspect(self.engine).get_indexes("image_characters")}
        self.assertIn("ix_image_characters_character_image", character_indexes)


if __name__ == "__main__":
    unittest.main()
