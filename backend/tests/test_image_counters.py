import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
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


class ImageCounterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-counter-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'counters.db'}",
            connect_args={"check_same_thread": False, "timeout": 15},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

        def override_get_db():
            with self.SessionTesting() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        with self.SessionTesting() as db:
            image = Image(
                filename="counter.webp",
                original_filename="counter.png",
                file_path="original/counter.webp",
                thumbnail_path="thumbnail/counter.webp",
                width=1200,
                height=800,
                orientation="landscape",
                file_size=1024,
                mime_type="image/webp",
                sha256="c" * 64,
                rating="safe",
                is_public=True,
            )
            db.add(image)
            db.commit()
            db.refresh(image)
            self.image_id = image.id

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _request(self, method: str, path: str) -> int:
        response = getattr(self.client, method)(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.status_code

    def test_concurrent_views_and_favorites_are_not_lost(self):
        view_path = f"/api/images/{self.image_id}/view"
        favorite_path = f"/api/images/{self.image_id}/favorite"
        with ThreadPoolExecutor(max_workers=8) as executor:
            view_results = list(executor.map(lambda _: self._request("post", view_path), range(24)))
            favorite_results = list(executor.map(lambda _: self._request("post", favorite_path), range(24)))

        self.assertEqual(len(view_results), 24)
        self.assertEqual(len(favorite_results), 24)
        with self.SessionTesting() as db:
            image = db.get(Image, self.image_id)
            self.assertEqual(image.view_count, 24)
            self.assertEqual(image.favorite_count, 24)

    def test_unfavorite_never_drops_below_zero(self):
        path = f"/api/images/{self.image_id}/favorite"
        for _ in range(3):
            self._request("post", path)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self._request("delete", path), range(12)))

        self.assertEqual(len(results), 12)
        with self.SessionTesting() as db:
            self.assertEqual(db.get(Image, self.image_id).favorite_count, 0)


if __name__ == "__main__":
    unittest.main()
