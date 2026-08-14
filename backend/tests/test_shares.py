import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.auth import require_library_write
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Image, Share
from app.services.storage_service import ensure_storage_dirs
from app.utils.time import utcnow_naive


class ShareApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-share-test-")
        self.original_storage_path = settings.storage_path
        settings.storage_path = Path(self.temp_dir.name) / "storage"
        ensure_storage_dirs()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'shares.db'}",
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
        app.dependency_overrides[require_library_write] = lambda: {"sub": "admin"}
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_library_write, None)
        settings.storage_path = self.original_storage_path
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _image(self, number: int, *, is_public: bool) -> Image:
        filename = f"share-{number}.webp"
        with self.SessionTesting() as db:
            image = Image(
                filename=filename,
                original_filename=f"share-{number}.png",
                file_path=f"original/{filename}",
                thumbnail_path=f"thumbnail/{filename}",
                media_version=1,
                width=1200,
                height=800,
                orientation="landscape",
                file_size=32,
                mime_type="image/webp",
                sha256=f"{number:064x}",
                rating="hidden" if not is_public else "safe",
                is_public=is_public,
            )
            db.add(image)
            db.commit()
            db.refresh(image)
            image_id = image.id
        (settings.storage_path / "original" / filename).write_bytes(f"original-{number}".encode())
        (settings.storage_path / "thumbnail" / filename).write_bytes(f"thumbnail-{number}".encode())
        with self.SessionTesting() as db:
            return db.get(Image, image_id)

    def test_album_share_preserves_order_and_authorizes_private_media_until_revoked(self):
        private_image = self._image(1, is_public=False)
        public_image = self._image(2, is_public=True)

        created = self.client.post(
            "/api/shares",
            json={"image_ids": [public_image.id, private_image.id], "title": "精选相册"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        share = created.json()
        self.assertEqual(share["title"], "精选相册")
        self.assertTrue(share["is_active"])
        self.assertGreaterEqual(len(share["token"]), 20)

        public_view = self.client.get(f"/api/shares/{share['token']}")
        self.assertEqual(public_view.status_code, 200, public_view.text)
        payload = public_view.json()
        self.assertEqual(payload["title"], "精选相册")
        self.assertEqual([item["id"] for item in payload["images"]], [public_image.id, private_image.id])
        self.assertNotIn("file_path", payload["images"][0])

        private_detail = self.client.get(f"/api/shares/{share['token']}/images/{private_image.id}")
        self.assertEqual(private_detail.status_code, 200, private_detail.text)
        self.assertEqual(private_detail.json()["id"], private_image.id)
        self.assertEqual(private_detail.json()["file_size"], 32)

        denied = self.client.get(f"/media/{private_image.id}/original/1")
        self.assertEqual(denied.status_code, 404)

        allowed = self.client.get(f"/media/{private_image.id}/original/1?share={share['token']}")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.content, b"original-1")
        self.assertEqual(allowed.headers["cache-control"], "private, no-store, max-age=0")
        self.assertEqual(allowed.headers["cross-origin-resource-policy"], "cross-origin")

        listed = self.client.get("/api/shares")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["total"], 1)

        revoked = self.client.delete(f"/api/shares/{share['id']}")
        self.assertEqual(revoked.status_code, 204, revoked.text)
        self.assertEqual(self.client.get(f"/api/shares/{share['token']}").status_code, 404)
        self.assertEqual(
            self.client.get(f"/media/{private_image.id}/original/1?share={share['token']}").status_code,
            404,
        )

    def test_share_expiration_revokes_page_details_and_private_media(self):
        private_image = self._image(4, is_public=False)
        created = self.client.post(
            "/api/shares",
            json={"image_ids": [private_image.id], "expires_in_hours": 24},
        )
        self.assertEqual(created.status_code, 201, created.text)
        share = created.json()
        self.assertIsNotNone(share["expires_at"])

        with self.SessionTesting() as db:
            stored = db.get(Share, share["id"])
            stored.expires_at = utcnow_naive() - timedelta(seconds=1)
            db.commit()

        self.assertEqual(self.client.get(f"/api/shares/{share['token']}").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/shares/{share['token']}/images/{private_image.id}").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/media/{private_image.id}/original/1?share={share['token']}").status_code,
            404,
        )

    def test_active_share_can_update_title_and_expiration(self):
        image = self._image(5, is_public=True)
        created = self.client.post("/api/shares", json={"image_ids": [image.id], "title": "初始标题"})
        self.assertEqual(created.status_code, 201, created.text)
        share = created.json()

        updated = self.client.patch(
            f"/api/shares/{share['id']}",
            json={"title": "新标题", "expires_in_hours": 24},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["title"], "新标题")
        self.assertIsNotNone(updated.json()["expires_at"])

        permanent = self.client.patch(f"/api/shares/{share['id']}", json={"expires_in_hours": None})
        self.assertEqual(permanent.status_code, 200, permanent.text)
        self.assertIsNone(permanent.json()["expires_at"])

    def test_share_creation_rejects_unknown_images_and_duplicate_ids(self):
        image = self._image(3, is_public=True)
        response = self.client.post("/api/shares", json={"image_ids": [image.id, image.id, 999999]})
        self.assertEqual(response.status_code, 404)

        success = self.client.post("/api/shares", json={"image_ids": [image.id, image.id]})
        self.assertEqual(success.status_code, 201, success.text)
        self.assertEqual(len(success.json()["images"]), 1)


if __name__ == "__main__":
    unittest.main()
