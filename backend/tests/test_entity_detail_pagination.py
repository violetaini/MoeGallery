import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.auth import optional_admin
from app.database import Base, get_db
from app.main import app
from app.models import Character, Image, Work


class EntityDetailPaginationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-detail-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'detail.db'}",
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
        self.work_id, self.character_id = self._seed_library()

    def tearDown(self):
        app.dependency_overrides.pop(optional_admin, None)
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _image(self, name: str, *, rating: str = "safe", is_public: bool = True) -> Image:
        return Image(
            filename=f"{name}.webp",
            original_filename=f"{name}.png",
            file_path=f"original/{name}.webp",
            thumbnail_path=f"thumbnail/{name}.webp",
            preview_path=None,
            width=1200,
            height=800,
            orientation="landscape",
            file_size=1024,
            mime_type="image/webp",
            is_animated=False,
            dynamic_range="sdr",
            bit_depth=8,
            sha256=name.ljust(64, "0"),
            rating=rating,
            is_public=is_public,
        )

    def _seed_library(self) -> tuple[int, int]:
        with self.SessionTesting() as db:
            work = Work(name="Detail Test Work")
            db.add(work)
            db.flush()
            character = Character(name="Main Character", work_id=work.id)
            extra_characters = [Character(name=f"Character {index}", work_id=work.id) for index in range(2)]
            db.add_all([character, *extra_characters])
            db.flush()

            public_image = self._image("public")
            hidden_image = self._image("hidden", rating="hidden")
            private_image = self._image("private", is_public=False)
            for image in (public_image, hidden_image, private_image):
                image.works.append(work)
                image.characters.append(character)
            work.cover_image = hidden_image
            character.avatar_image = hidden_image
            db.add_all([public_image, hidden_image, private_image])
            db.commit()
            return work.id, character.id

    def test_public_details_return_counts_without_embedded_collections(self):
        work_response = self.client.get(f"/api/works/{self.work_id}")
        character_response = self.client.get(f"/api/characters/{self.character_id}")

        self.assertEqual(work_response.status_code, 200)
        work = work_response.json()
        self.assertEqual(work["image_count"], 1)
        self.assertEqual(work["character_count"], 3)
        self.assertIsNone(work["cover_image"])
        self.assertNotIn("images", work)
        self.assertNotIn("characters", work)

        self.assertEqual(character_response.status_code, 200)
        character = character_response.json()
        self.assertEqual(character["image_count"], 1)
        self.assertIsNone(character["avatar_image"])
        self.assertNotIn("images", character)

    def test_admin_details_count_private_and_hidden_images(self):
        app.dependency_overrides[optional_admin] = lambda: {"method": "test-admin"}

        work = self.client.get(f"/api/works/{self.work_id}").json()
        character = self.client.get(f"/api/characters/{self.character_id}").json()

        self.assertEqual(work["image_count"], 3)
        self.assertEqual(work["character_count"], 3)
        self.assertIsNotNone(work["cover_image"])
        self.assertEqual(character["image_count"], 3)
        self.assertIsNotNone(character["avatar_image"])

    def test_existing_list_endpoints_page_relationships(self):
        character_page = self.client.get(
            "/api/characters",
            params={"work_id": self.work_id, "page": 2, "page_size": 2},
        ).json()
        image_page = self.client.get(
            "/api/images",
            params={"character_id": self.character_id, "page": 1, "page_size": 1},
        ).json()

        self.assertEqual(character_page["total"], 3)
        self.assertEqual(len(character_page["items"]), 1)
        self.assertEqual(image_page["total"], 1)
        self.assertEqual(len(image_page["items"]), 1)


if __name__ == "__main__":
    unittest.main()
