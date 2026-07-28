import io
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image as PillowImage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.database import Base
from app.models import Image
from app.services.image_service import image_orientation
from app.services.preview_cleanup_service import prune_redundant_previews
from app.services.storage_service import save_image_files
from app.utils.image_process import inspect_image


def png_bytes(size: tuple[int, int] = (32, 24)) -> bytes:
    buffer = io.BytesIO()
    PillowImage.new("RGB", size, "#7ba7d8").save(buffer, format="PNG")
    return buffer.getvalue()


def animated_gif_bytes() -> bytes:
    buffer = io.BytesIO()
    first = PillowImage.new("RGB", (32, 24), "#7ba7d8")
    second = PillowImage.new("RGB", (32, 24), "#d88a7b")
    first.save(buffer, format="GIF", save_all=True, append_images=[second], duration=120, loop=0)
    return buffer.getvalue()


def hdr_png_bytes() -> bytes:
    image = PillowImage.new("I;16", (16, 12))
    image.putdata([index * 255 for index in range(16 * 12)])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ImageVariantStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-image-variants-")
        self.previous_storage_path = settings.storage_path
        settings.storage_path = Path(self.temp_dir.name) / "storage"
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'variants.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self):
        self.engine.dispose()
        settings.storage_path = self.previous_storage_path
        self.temp_dir.cleanup()

    def save(self, data: bytes, filename: str, marker: str):
        inspection = inspect_image(data)
        paths = save_image_files(data, marker * 64, filename, inspection)
        return inspection, paths

    def add_image(self, db, inspection, paths, sha256: str, preview_path=None):
        image = Image(
            filename=paths["filename"],
            original_filename=paths["original_filename"],
            file_path=paths["file_path"],
            preview_path=paths["preview_path"] if preview_path is None else preview_path,
            thumbnail_path=paths["thumbnail_path"],
            width=inspection.width,
            height=inspection.height,
            orientation=image_orientation(inspection.width, inspection.height),
            file_size=paths["file_size"],
            mime_type=paths["mime_type"],
            is_animated=inspection.is_animated,
            dynamic_range=inspection.dynamic_range,
            bit_depth=inspection.bit_depth,
            color_profile=inspection.color_profile,
            sha256=sha256,
        )
        db.add(image)
        db.commit()
        return image

    def assert_storage_file(self, relative_path):
        self.assertTrue((settings.storage_path / relative_path).is_file(), relative_path)

    def test_static_sdr_stores_master_and_thumbnail_only(self):
        inspection, paths = self.save(png_bytes(), "static.png", "a")

        self.assertEqual(inspection.dynamic_range, "sdr")
        self.assertFalse(inspection.is_animated)
        self.assertIsNone(paths["preview_path"])
        self.assert_storage_file(paths["file_path"])
        self.assert_storage_file(paths["thumbnail_path"])
        self.assertEqual(list((settings.storage_path / "preview").glob("*")), [])

    def test_animated_image_stores_original_and_thumbnail_only(self):
        inspection, paths = self.save(animated_gif_bytes(), "animated.gif", "b")

        self.assertTrue(inspection.is_animated)
        self.assertTrue(paths["file_path"].endswith(".gif"))
        self.assertIsNone(paths["preview_path"])
        self.assert_storage_file(paths["file_path"])
        self.assert_storage_file(paths["thumbnail_path"])

    def test_hdr_image_keeps_sdr_preview_and_thumbnail(self):
        inspection, paths = self.save(hdr_png_bytes(), "hdr.png", "c")

        self.assertEqual(inspection.dynamic_range, "hdr")
        self.assertIsNotNone(paths["preview_path"])
        self.assert_storage_file(paths["file_path"])
        self.assert_storage_file(paths["preview_path"])
        self.assert_storage_file(paths["thumbnail_path"])

    def test_cleanup_removes_verified_legacy_preview_and_keeps_hdr_preview(self):
        static_inspection, static_paths = self.save(png_bytes(), "static.png", "d")
        hdr_inspection, hdr_paths = self.save(hdr_png_bytes(), "hdr.png", "e")
        legacy_preview_path = "preview/legacy-static.webp"
        legacy_target = settings.storage_path / legacy_preview_path
        legacy_target.parent.mkdir(parents=True, exist_ok=True)
        legacy_target.write_bytes(b"legacy-preview")

        with self.SessionTesting() as db:
            static = self.add_image(db, static_inspection, static_paths, "d" * 64, preview_path=legacy_preview_path)
            hdr = self.add_image(db, hdr_inspection, hdr_paths, "e" * 64)

            dry_run = prune_redundant_previews(db, apply=False)
            self.assertEqual(dry_run.candidates, 1)
            self.assertEqual(dry_run.retained_hdr, 1)
            self.assertEqual(db.get(Image, static.id).preview_path, legacy_preview_path)
            self.assertTrue(legacy_target.exists())

            applied = prune_redundant_previews(db, apply=True)
            self.assertEqual(applied.removed, 1)
            self.assertFalse(legacy_target.exists())
            self.assertIsNone(db.get(Image, static.id).preview_path)
            self.assertEqual(db.get(Image, hdr.id).preview_path, hdr_paths["preview_path"])
            self.assert_storage_file(hdr_paths["preview_path"])


if __name__ == "__main__":
    unittest.main()
