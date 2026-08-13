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
from app.models import Image


class RandomImageListPaginationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-random-list-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'random-list.db'}",
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
        self._seed_images(73)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _seed_images(self, count: int) -> None:
        with self.SessionTesting() as db:
            db.add_all(
                [
                    Image(
                        filename=f"random-{index}.webp",
                        original_filename=f"random-{index}.png",
                        file_path=f"original/random-{index}.webp",
                        thumbnail_path=f"thumbnail/random-{index}.webp",
                        preview_path=f"preview/random-{index}.webp",
                        width=1200,
                        height=800,
                        orientation="landscape",
                        file_size=1024,
                        mime_type="image/webp",
                        sha256=f"{index:064x}",
                        rating="safe",
                        is_public=True,
                    )
                    for index in range(1, count + 1)
                ]
            )
            db.commit()

    def _page_ids(self, page: int, seed: int | None = None) -> tuple[list[int], int]:
        params = {"sort": "random", "page": page, "page_size": 20}
        if seed is not None:
            params["random_seed"] = seed
        response = self.client.get("/api/images", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        return [item["id"] for item in payload["items"]], payload["random_seed"]

    def test_generated_seed_can_page_without_duplicates_or_gaps(self):
        first_page, seed = self._page_ids(1)
        pages = [first_page]
        for page in range(2, 5):
            ids, returned_seed = self._page_ids(page, seed)
            self.assertEqual(returned_seed, seed)
            pages.append(ids)

        flattened = [image_id for page in pages for image_id in page]
        self.assertEqual([len(page) for page in pages], [20, 20, 20, 13])
        self.assertEqual(len(flattened), 73)
        self.assertEqual(len(set(flattened)), 73)

    def test_same_seed_is_stable_and_different_seed_changes_order(self):
        first, _ = self._page_ids(1, 123456)
        repeated, _ = self._page_ids(1, 123456)
        different, _ = self._page_ids(1, 654321)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different)


if __name__ == "__main__":
    unittest.main()
