import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image as PilImage

from app.config import settings
from app.models import Image
from app.services.storage_service import ensure_storage_dirs
from scripts_convert_originals_to_webp import convert_image


def png_bytes() -> bytes:
    image = PilImage.new("RGB", (16, 10), color=(90, 140, 210))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class ConvertOriginalsMediaVersionTests(unittest.TestCase):
    def test_conversion_rotates_media_version(self):
        previous_storage_path = settings.storage_path
        with tempfile.TemporaryDirectory(prefix="agms-convert-version-") as temp_dir:
            settings.storage_path = Path(temp_dir) / "storage"
            ensure_storage_dirs()
            source = settings.storage_path / "original" / "source.png"
            source.write_bytes(png_bytes())
            image = Image(
                filename="source.png",
                original_filename="source.png",
                file_path="original/source.png",
                thumbnail_path="thumbnail/source.webp",
                media_version=7,
                mime_type="image/png",
                width=16,
                height=10,
            )

            try:
                self.assertEqual(convert_image(image, apply=True, keep_source=False), "converted")
                self.assertEqual(image.media_version, 8)
                self.assertEqual(image.mime_type, "image/webp")
                self.assertTrue((settings.storage_path / image.file_path).is_file())
                self.assertFalse(source.exists())
            finally:
                settings.storage_path = previous_storage_path


if __name__ == "__main__":
    unittest.main()
