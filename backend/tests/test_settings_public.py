import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api import settings as settings_api
from app.database import Base
from app.models import Image
from app.schemas.settings import AdminSettingsUpdate
from app.services.app_setting_service import (
    RANDOM_API_DEFAULT_RATING_KEY,
    RANDOM_API_DESKTOP_ORIENTATION_KEY,
)
from app.utils.time import utcnow_naive


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

    @staticmethod
    def _new_image(filename: str, *, rating: str = "safe", is_public: bool = True) -> Image:
        return Image(
            filename=filename,
            original_filename=filename,
            file_path=f"original/{filename}",
            thumbnail_path=f"thumbnail/{filename}",
            preview_path=f"preview/{filename}",
            width=1600,
            height=720,
            file_size=1234,
            mime_type="image/webp",
            sha256=(filename[0] if filename else "a") * 64,
            rating=rating,
            is_public=is_public,
            dynamic_range="sdr",
            bit_depth=8,
            is_animated=False,
            favorite_count=0,
            created_at=utcnow_naive(),
            updated_at=utcnow_naive(),
        )

    def test_public_hero_image_settings(self):
        with self.SessionTesting() as db:
            image = self._new_image("hero.webp")
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

    def test_public_settings_hide_stale_private_and_hidden_images(self):
        with self.SessionTesting() as db:
            private_image = self._new_image("private.webp", is_public=False)
            hidden_image = self._new_image("hidden.webp", rating="hidden")
            db.add_all([private_image, hidden_image])
            db.commit()

            settings_api._set_value(db, settings_api.HOME_HERO_IMAGE_ID_KEY, str(private_image.id))
            settings_api._set_value(
                db,
                settings_api.HOME_SLIDESHOW_IMAGE_IDS_KEY,
                f"[{private_image.id},{hidden_image.id}]",
            )
            db.commit()

            public_settings = settings_api._read_public_settings(db)
            self.assertIsNone(public_settings["home_hero_image_id"])
            self.assertIsNone(public_settings["home_hero_image"])
            self.assertEqual(public_settings["home_slideshow_image_ids"], [])
            self.assertEqual(public_settings["home_slideshow_images"], [])

            admin_settings = settings_api._read_settings(db)
            self.assertEqual(admin_settings["home_hero_image_id"], private_image.id)
            self.assertEqual(
                admin_settings["home_slideshow_image_ids"],
                [private_image.id, hidden_image.id],
            )

    def test_public_image_settings_reject_private_and_hidden_images(self):
        with self.SessionTesting() as db:
            private_image = self._new_image("private.webp", is_public=False)
            hidden_image = self._new_image("hidden.webp", rating="hidden")
            db.add_all([private_image, hidden_image])
            db.commit()

            for image in (private_image, hidden_image):
                with self.subTest(image_id=image.id):
                    with self.assertRaises(HTTPException):
                        settings_api._set_image_setting(
                            db,
                            settings_api.HOME_HERO_IMAGE_ID_KEY,
                            image.id,
                            public_only=True,
                        )
                    with self.assertRaises(HTTPException):
                        settings_api._set_image_list_setting(
                            db,
                            settings_api.HOME_SLIDESHOW_IMAGE_IDS_KEY,
                            [image.id],
                            public_only=True,
                        )

    def test_home_slideshow_accepts_forty_eight_images(self):
        image_ids = list(range(1, 49))
        self.assertEqual(settings_api._normalize_image_id_list(image_ids), image_ids)
        self.assertEqual(AdminSettingsUpdate(home_slideshow_image_ids=image_ids).home_slideshow_image_ids, image_ids)

        with self.assertRaisesRegex(ValueError, "at most 48 images"):
            settings_api._normalize_image_id_list(list(range(1, 50)))
        with self.assertRaises(ValidationError):
            AdminSettingsUpdate(home_slideshow_image_ids=list(range(1, 50)))

    def test_random_api_admin_defaults_are_normalized(self):
        with self.SessionTesting() as db:
            defaults = settings_api._read_settings(db)
            self.assertEqual(defaults["random_api_desktop_orientation"], "landscape")
            self.assertEqual(defaults["random_api_mobile_orientation"], "portrait")
            self.assertEqual(defaults["random_api_default_rating"], "safe")
            self.assertEqual(defaults["random_api_default_variant"], "preview")

            settings_api._set_value(db, RANDOM_API_DESKTOP_ORIENTATION_KEY, "portrait")
            settings_api._set_value(db, RANDOM_API_DEFAULT_RATING_KEY, "any")
            db.commit()
            updated = settings_api._read_settings(db)
            self.assertEqual(updated["random_api_desktop_orientation"], "portrait")
            self.assertEqual(updated["random_api_default_rating"], "any")


if __name__ == "__main__":
    unittest.main()
