import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api import settings as settings_api
from app.database import Base
from app.models import Image


class PublicSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-settings-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'settings.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_public_hero_image_settings(self):
        with self.SessionTesting() as db:
            image = Image(
                filename="hero.webp",
                original_filename="hero.png",
                file_path="original/hero.webp",
                thumbnail_path="thumbnail/hero.webp",
                preview_path="preview/hero.webp",
                width=1600,
                height=720,
                file_size=1234,
                mime_type="image/webp",
                sha256="a" * 64,
                rating="safe",
                is_public=True,
                dynamic_range="sdr",
                bit_depth=8,
                is_animated=False,
                favorite_count=0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(image)
            db.commit()
            db.refresh(image)

            for prefix, key in settings_api.PUBLIC_HERO_IMAGE_SETTINGS.items():
                with self.subTest(prefix=prefix):
                    settings_api._set_image_setting(db, key, image.id)
                    db.commit()

                    public_settings = settings_api._read_public_settings(db)
                    self.assertEqual(public_settings[f"{prefix}_image_id"], image.id)
                    self.assertEqual(public_settings[f"{prefix}_image"].preview_path, "preview/hero.webp")

                    admin_settings = settings_api._read_settings(db)
                    self.assertEqual(admin_settings[f"{prefix}_image_id"], image.id)

                    settings_api._set_image_setting(db, key, None)
                    db.commit()
                    self.assertIsNone(settings_api._read_public_settings(db)[f"{prefix}_image_id"])

    def test_public_hero_rejects_missing_image(self):
        with self.SessionTesting() as db:
            for key in settings_api.PUBLIC_HERO_IMAGE_SETTINGS.values():
                with self.subTest(key=key):
                    with self.assertRaises(HTTPException):
                        settings_api._set_image_setting(db, key, 999)


if __name__ == "__main__":
    unittest.main()
