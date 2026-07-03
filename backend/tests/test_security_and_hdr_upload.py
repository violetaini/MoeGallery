import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal
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
    def test_private_image_not_publicly_accessible_by_path(self):
        import imagecodecs
        import numpy as np

        health = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing).StatusCode } catch { '0' }",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if health.stdout.strip() != "200":
            self.skipTest("local backend preview is not running on 127.0.0.1:8000")

        h, w = 32, 64
        x = np.linspace(0.0, 4.0, w, dtype=np.float32)
        y = np.linspace(0.0, 1.5, h, dtype=np.float32)[:, None]
        r = np.broadcast_to(x, (h, w))
        g = np.broadcast_to(y, (h, w))
        b = np.sqrt(np.maximum(r + g, 0.0))
        a = np.ones((h, w), dtype=np.float32)
        rgba = np.stack([r, g, b, a], axis=-1).astype(np.float16)
        jxr = imagecodecs.jpegxr_encode(rgba)

        created = None
        with SessionLocal() as db:
            service = ImageService(db)
            created, _ = service.create_from_bytes(
                data=jxr,
                original_filename="private.jxr",
                content_type="image/jxr",
                rating="hidden",
                is_public=False,
            )
            hidden_path = created.file_path

        try:
            response = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"$r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/storage/{hidden_path}' -UseBasicParsing -ErrorAction SilentlyContinue; if ($r) {{ [Console]::WriteLine($r.StatusCode) }} elseif ($Error[0].Exception.Response) {{ [Console]::WriteLine([int]$Error[0].Exception.Response.StatusCode) }} else {{ [Console]::WriteLine('0') }}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(response.stdout.strip(), "404")
        finally:
            if created is not None:
                with SessionLocal() as db:
                    row = db.get(ImageModel, created.id)
                    if row:
                        ImageService(db).delete_image(row)


if __name__ == "__main__":
    unittest.main()
