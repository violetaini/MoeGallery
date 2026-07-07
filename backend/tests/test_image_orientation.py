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

from app.database import Base
from app.config import settings
from app.services.image_service import ImageService, image_orientation


def png_bytes(width: int, height: int) -> bytes:
    path = Path(tempfile.gettempdir()) / f"agms-orientation-{width}x{height}.png"
    PillowImage.new("RGB", (width, height), (64, 128, 192)).save(path)
    try:
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


class ImageOrientationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-orientation-test-")
        self.previous_storage_path = settings.storage_path
        settings.storage_path = Path(self.temp_dir.name) / "storage"
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'orientation.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self):
        self.engine.dispose()
        settings.storage_path = self.previous_storage_path
        self.temp_dir.cleanup()

    def test_image_orientation_helper(self):
        self.assertEqual(image_orientation(1600, 900), "landscape")
        self.assertEqual(image_orientation(900, 1600), "portrait")
        self.assertEqual(image_orientation(1024, 1024), "square")

    def test_upload_sets_orientation(self):
        with self.SessionTesting() as db:
            service = ImageService(db)
            landscape, _ = service.create_from_bytes(
                data=png_bytes(320, 180),
                original_filename="wide.png",
                content_type="image/png",
            )
            portrait, _ = service.create_from_bytes(
                data=png_bytes(180, 320),
                original_filename="tall.png",
                content_type="image/png",
            )

            self.assertEqual(landscape.orientation, "landscape")
            self.assertEqual(portrait.orientation, "portrait")


if __name__ == "__main__":
    unittest.main()
