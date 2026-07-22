import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.database import Base, SessionLocal, get_db
from app.main import app
from app.models import Image as ImageModel
from app.services.image_service import ImageService
from app.utils.hash import sha256_bytes
from app.utils.image_process import render_webp_preview_bytes


class HdrUploadPolicyTests(unittest.TestCase):
    def test_allows_supported_sdr_png_upload(self):
        image = Image.new("RGB", (8, 8), "#ffffff")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        created = None
        with SessionLocal() as db:
            service = ImageService(db)
            created, _ = service.create_from_bytes(
                data=buffer.getvalue(),
                original_filename="plain.png",
                content_type="image/png",
                rating="safe",
                is_public=True,
            )
            self.assertEqual(created.dynamic_range, "sdr")
            self.assertEqual(created.mime_type, "image/webp")
            self.assertTrue(created.file_path.endswith(".webp"))

        if created is not None:
            with SessionLocal() as db:
                row = db.get(ImageModel, created.id)
                if row:
                    ImageService(db).delete_image(row)

    def test_allows_hdr_png_suffix_but_still_enforces_hdr_content(self):
        image = Image.new("I;16", (8, 8))
        image.putdata([i * 1024 for i in range(64)])
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        created = None
        with SessionLocal() as db:
            service = ImageService(db)
            created, _ = service.create_from_bytes(
                data=buffer.getvalue(),
                original_filename="hdr-source.png",
                content_type="image/png",
                rating="safe",
                is_public=True,
            )
            self.assertEqual(created.dynamic_range, "hdr")
            self.assertTrue(created.file_path.endswith(".png"))

        if created is not None:
            with SessionLocal() as db:
                row = db.get(ImageModel, created.id)
                if row:
                    ImageService(db).delete_image(row)

    def test_rejects_unsupported_filename_suffix(self):
        image = Image.new("RGB", (8, 8), "#ffffff")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        with SessionLocal() as db:
            service = ImageService(db)
            with self.assertRaisesRegex(Exception, "仅支持以下图片后缀上传"):
                service.create_from_bytes(
                    data=buffer.getvalue(),
                    original_filename="plain.txt",
                    content_type="text/plain",
                    rating="safe",
                    is_public=True,
                )

    def test_preview_generation_supports_sdr_png(self):
        image = Image.new("RGB", (32, 24), "#ffffff")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        preview = render_webp_preview_bytes(buffer.getvalue(), max_size=128)
        self.assertTrue(preview.startswith(b"RIFF"))

    def test_preview_generation_supports_hdr_jxr(self):
        import imagecodecs
        import numpy as np

        h, w = 24, 32
        x = np.linspace(0.0, 4.0, w, dtype=np.float32)
        y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        r = np.broadcast_to(x, (h, w))
        g = np.broadcast_to(y, (h, w))
        b = np.sqrt(np.maximum(r + g, 0.0))
        a = np.ones((h, w), dtype=np.float32)
        rgba = np.stack([r, g, b, a], axis=-1).astype(np.float16)
        jxr = imagecodecs.jpegxr_encode(rgba)
        preview = render_webp_preview_bytes(jxr, max_size=128)
        self.assertTrue(preview.startswith(b"RIFF"))


class StorageRouteSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-storage-route-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'storage-route.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.original_storage_path = settings.storage_path
        settings.storage_path = Path(self.temp_dir.name) / "storage"

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
        settings.storage_path = self.original_storage_path
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_private_image_not_publicly_accessible_by_path(self):
        hidden_path = "original/private.webp"
        target = settings.storage_path / hidden_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"private-image")
        with self.SessionTesting() as db:
            db.add(
                ImageModel(
                    filename="private.webp",
                    original_filename="private.webp",
                    file_path=hidden_path,
                    preview_path="preview/private.webp",
                    thumbnail_path="thumbnail/private.webp",
                    width=1,
                    height=1,
                    orientation="square",
                    file_size=target.stat().st_size,
                    mime_type="image/webp",
                    sha256="0" * 64,
                    rating="hidden",
                    is_public=False,
                )
            )
            db.commit()

        response = self.client.get(f"/storage/{hidden_path}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "File not found"})
        self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
