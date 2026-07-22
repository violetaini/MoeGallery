import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import AppSetting, Character, Image, Work
from app.services.app_setting_service import RANDOM_API_DESKTOP_ORIENTATION_KEY


class RandomImageApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-random-api-test-")
        self.storage_path = Path(self.temp_dir.name) / "storage"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.previous_storage_path = settings.storage_path
        settings.storage_path = self.storage_path
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'random-api.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

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
        self.engine.dispose()
        settings.storage_path = self.previous_storage_path
        self.temp_dir.cleanup()

    def add_image(
        self,
        db,
        name: str,
        *,
        orientation: str,
        rating: str = "safe",
        is_public: bool = True,
        work: Work | None = None,
        character: Character | None = None,
        preview: bool = True,
    ) -> Image:
        now = datetime.utcnow()
        original_path = f"original/{name}.webp"
        preview_path = f"preview/{name}.webp" if preview else None
        thumbnail_path = f"thumbnail/{name}.webp"
        for relative_path in (original_path, preview_path, thumbnail_path):
            if not relative_path:
                continue
            target = self.storage_path / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(name.encode("ascii"))
        image = Image(
            filename=f"{name}.webp",
            original_filename=f"{name}.png",
            file_path=original_path,
            preview_path=preview_path,
            thumbnail_path=thumbnail_path,
            width=1600 if orientation == "landscape" else 900,
            height=1600 if orientation == "portrait" else 900,
            orientation=orientation,
            file_size=len(name),
            mime_type="image/webp",
            sha256=(name[0] * 64),
            rating=rating,
            is_public=is_public,
            dynamic_range="sdr",
            bit_depth=8,
            is_animated=False,
            favorite_count=0,
            created_at=now,
            updated_at=now,
        )
        if work:
            image.works.append(work)
        if character:
            image.characters.append(character)
        db.add(image)
        db.commit()
        db.refresh(image)
        return image

    def test_no_parameters_use_pc_landscape_safe_defaults(self):
        with self.SessionTesting() as db:
            landscape = self.add_image(db, "a", orientation="landscape")
            self.add_image(db, "b", orientation="portrait")
            self.add_image(db, "c", orientation="landscape", rating="sensitive")

        response = self.client.get("/api/images/random", follow_redirects=False)

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], f"/storage/{landscape.preview_path}")
        self.assertEqual(response.headers["cache-control"], "no-store, max-age=0")
        target_response = self.client.get(response.headers["location"])
        self.assertEqual(target_response.status_code, 200)
        self.assertEqual(target_response.headers["cross-origin-resource-policy"], "cross-origin")

    def test_mobile_defaults_to_portrait_and_json_can_be_requested(self):
        with self.SessionTesting() as db:
            portrait = self.add_image(db, "d", orientation="portrait")
            self.add_image(db, "e", orientation="landscape")

        response = self.client.get(
            "/api/images/random?response=json",
            headers={"Sec-CH-UA-Mobile": "?1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["image"]["id"], portrait.id)
        self.assertEqual(payload["resolved_device"], "mobile")
        self.assertEqual(payload["applied_orientation"], "portrait")
        self.assertEqual(payload["applied_rating"], "safe")
        self.assertEqual(payload["served_variant"], "preview")

    def test_explicit_relationship_and_sensitive_filters_override_defaults(self):
        with self.SessionTesting() as db:
            work = Work(name="Work")
            db.add(work)
            db.flush()
            character = Character(name="Character", work_id=work.id)
            db.add(character)
            db.commit()
            target = self.add_image(
                db,
                "f",
                orientation="portrait",
                rating="sensitive",
                work=work,
                character=character,
            )
            self.add_image(db, "g", orientation="portrait", rating="sensitive")

        response = self.client.get(
            "/api/images/random",
            params={
                "work_id": work.id,
                "character_id": character.id,
                "rating": "sensitive",
                "orientation": "portrait",
                "variant": "original",
                "response": "json",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["image"]["id"], target.id)
        self.assertEqual(payload["image_url"], f"/storage/{target.file_path}")
        self.assertEqual(payload["requested_variant"], "original")

    def test_character_name_filter_supports_chinese_japanese_and_aliases(self):
        with self.SessionTesting() as db:
            work = Work(name="魔女之旅", original_name="魔女の旅々")
            db.add(work)
            db.flush()
            character = Character(
                name="伊蕾娜",
                original_name="イレイナ",
                aliases="The Ashen Witch; 灰之魔女",
                work_id=work.id,
            )
            db.add(character)
            db.commit()
            target = self.add_image(
                db,
                "name-filter",
                orientation="portrait",
                work=work,
                character=character,
            )

        for value in ("伊蕾娜", "イレイナ", "灰之魔女"):
            with self.subTest(value=value):
                response = self.client.get(
                    "/api/images/random",
                    params={"character": value, "orientation": "portrait", "response": "json"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["image"]["id"], target.id)

        list_response = self.client.get(
            "/api/images",
            params={"character": "イレイナ", "orientation": "portrait"},
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["id"] for item in list_response.json()["items"]], [target.id])

    def test_any_rating_never_returns_hidden_or_private_images(self):
        with self.SessionTesting() as db:
            visible = self.add_image(db, "h", orientation="landscape", rating="sensitive")
            self.add_image(db, "i", orientation="landscape", rating="hidden")
            self.add_image(db, "j", orientation="landscape", is_public=False)
            self.add_image(db, "m", orientation="landscape", rating="legacy")

        response = self.client.get(
            "/api/images/random?rating=any&orientation=landscape&response=json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["image"]["id"], visible.id)
        self.assertEqual(self.client.get("/api/images/random?rating=hidden").status_code, 422)

    def test_admin_default_override_and_variant_fallback(self):
        with self.SessionTesting() as db:
            portrait = self.add_image(db, "k", orientation="portrait", preview=False)
            db.add(AppSetting(key=RANDOM_API_DESKTOP_ORIENTATION_KEY, value="portrait"))
            db.commit()

        response = self.client.get("/api/images/random?response=json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["image"]["id"], portrait.id)
        self.assertEqual(payload["requested_variant"], "preview")
        self.assertEqual(payload["served_variant"], "original")

    def test_no_matching_public_image_returns_404(self):
        with self.SessionTesting() as db:
            self.add_image(db, "l", orientation="portrait", rating="hidden")

        response = self.client.get("/api/images/random?orientation=portrait&rating=any")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
