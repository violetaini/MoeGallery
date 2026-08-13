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

from app.database import Base, get_db
from app.main import app
from app.models import Character, Image, Work


class GalleryImageFilteringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-gallery-filter-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'gallery-filter.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

        def override_get_db():
            with self.SessionTesting() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.expected_gallery_ids = self._seed_library()

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()
        self.temp_dir.cleanup()

    @staticmethod
    def _image(index: int) -> Image:
        return Image(
            filename=f"filter-image-{index}.webp",
            original_filename=f"filter-image-{index}.png",
            file_path=f"original/filter-image-{index}.webp",
            thumbnail_path=f"thumbnail/filter-image-{index}.webp",
            width=1200,
            height=800,
            orientation="landscape",
            file_size=1024,
            mime_type="image/webp",
            sha256=f"{index:064x}",
            rating="safe",
            is_public=True,
        )

    def _seed_library(self) -> set[int]:
        with self.SessionTesting() as db:
            images = [self._image(index) for index in range(1, 7)]
            db.add_all(images)
            db.flush()
            work = Work(name="Filter Work", cover_image=images[3], backdrop_image=images[4])
            db.add(work)
            db.flush()
            character = Character(name="Filter Character", work_id=work.id, avatar_image=images[5])
            db.add(character)
            db.flush()

            images[0].works.append(work)
            images[3].works.append(work)
            images[4].works.append(work)
            images[5].works.append(work)
            images[1].characters.append(character)
            images[5].characters.append(character)
            db.commit()
            return {
                "gallery": {images[0].id, images[1].id, images[2].id},
                "work_id": work.id,
                "work_image_id": images[0].id,
                "character_id": character.id,
                "character_image_id": images[1].id,
            }

    def test_gallery_filters_keep_partial_and_unbound_images_but_remove_artwork(self):
        response = self.client.get(
            "/api/images",
            params={
                "q": "filter-image",
                "page_size": 100,
                "exclude_cover_images": True,
                "exclude_backdrop_images": True,
                "exclude_avatar_images": True,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual({item["id"] for item in response.json()["items"]}, self.expected_gallery_ids["gallery"])

    def test_global_search_uses_the_same_gallery_image_boundary(self):
        response = self.client.get("/api/search", params={"q": "filter-image", "limit": 50})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual({item["id"] for item in response.json()["images"]}, self.expected_gallery_ids["gallery"])

    def test_search_treats_like_metacharacters_as_text_and_rejects_blank_queries(self):
        wildcard = self.client.get("/api/search", params={"q": "%_"})
        blank = self.client.get("/api/search", params={"q": "   "})
        image_list = self.client.get("/api/images", params={"q": "%_"})

        self.assertEqual(wildcard.status_code, 200, wildcard.text)
        self.assertEqual(wildcard.json()["images"], [])
        self.assertEqual(wildcard.json()["works"], [])
        self.assertEqual(wildcard.json()["characters"], [])
        self.assertEqual(blank.status_code, 422, blank.text)
        self.assertEqual(image_list.status_code, 200, image_list.text)
        self.assertEqual(image_list.json()["total"], 0)

    def test_detail_counts_and_lists_exclude_structural_artwork(self):
        work_id = self.expected_gallery_ids["work_id"]
        character_id = self.expected_gallery_ids["character_id"]

        work = self.client.get(f"/api/works/{work_id}")
        character = self.client.get(f"/api/characters/{character_id}")
        work_images = self.client.get(
            "/api/images",
            params={
                "work_id": work_id,
                "exclude_cover_images": True,
                "exclude_backdrop_images": True,
                "exclude_avatar_images": True,
            },
        )
        character_images = self.client.get(
            "/api/images",
            params={
                "character_id": character_id,
                "exclude_cover_images": True,
                "exclude_backdrop_images": True,
                "exclude_avatar_images": True,
            },
        )

        self.assertEqual(work.status_code, 200, work.text)
        self.assertEqual(character.status_code, 200, character.text)
        self.assertEqual(work.json()["image_count"], 1)
        self.assertEqual(character.json()["image_count"], 1)
        self.assertEqual(
            [item["id"] for item in work_images.json()["items"]],
            [self.expected_gallery_ids["work_image_id"]],
        )
        self.assertEqual(
            [item["id"] for item in character_images.json()["items"]],
            [self.expected_gallery_ids["character_image_id"]],
        )


if __name__ == "__main__":
    unittest.main()
