import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.config import settings
from app.models import CdnWarmTask, Image
from app.services.cdn_warm_service import (
    browser_fetch,
    cdn_warm_stats,
    detect_cdn_provider,
    enqueue_image_for_warm,
    get_cdn_warm_config,
    normalize_cdn_warm_base_url,
    requeue_expired_cdn_warm_tasks,
    TASK_STATUS_QUEUED,
    TASK_STATUS_SUCCESS,
    utcnow,
    update_cdn_warm_config,
)


class _FakeResponse:
    def __init__(self, headers=None, body=b"image-bytes"):
        self.headers = headers or {}
        self.status = 200
        self._body = body
        self._offset = 0

    def getcode(self):
        return self.status

    def read(self, size=-1):
        if size == -1:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return self.response


class CdnWarmServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-cdn-warm-")
        engine = create_engine(f"sqlite:///{Path(self.temp_dir.name) / 'test.db'}", future=True)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, future=True)
        self.engine = engine

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _image(self, db, *, media_version=1, is_public=True, rating="safe"):
        image = Image(
            filename="image.webp",
            original_filename="image.png",
            file_path="original/image.webp",
            thumbnail_path="thumbnail/image.webp",
            media_version=media_version,
            width=32,
            height=24,
            file_size=32,
            mime_type="image/webp",
            sha256="a" * 64,
            is_public=is_public,
            rating=rating,
        )
        db.add(image)
        db.commit()
        return image

    def test_rejects_local_unbound_and_ip_origins(self):
        for value in (
            "http://cdn.example.com",
            "https://localhost",
            "https://127.0.0.1",
            "https://10.0.0.8",
            "https://203.0.113.8",
            "https://gallery",
            "https://cdn.example.com/path",
        ):
            with self.assertRaises(ValueError, msg=value):
                normalize_cdn_warm_base_url(value)
        self.assertEqual(normalize_cdn_warm_base_url("https://CDN.Example.com/"), "https://cdn.example.com")

    def test_detects_supported_cdn_cache_headers(self):
        self.assertEqual(detect_cdn_provider({"X-Site-Cache-Status": "HIT"}), ("esa", "HIT"))
        self.assertEqual(detect_cdn_provider({"EO-Cache-Status": "RefreshHit"}), ("edgeone", "REFRESHHIT"))
        self.assertEqual(detect_cdn_provider({"CF-Cache-Status": "MISS", "CF-Ray": "abc"}), ("cloudflare", "MISS"))
        self.assertEqual(detect_cdn_provider({"Server": "nginx"}), ("direct", "DIRECT"))

    def test_browser_fetch_uses_image_request_headers_without_cookies(self):
        opener = _FakeOpener(_FakeResponse({"X-Site-Cache-Status": "MISS"}))
        with patch("app.services.cdn_warm_service.urllib.request.build_opener", return_value=opener):
            result = browser_fetch("https://cdn.example.com/media/1/thumbnail/1", base_url="https://cdn.example.com")
        self.assertEqual(result.provider, "esa")
        self.assertEqual(result.cache_status, "MISS")
        self.assertEqual(result.response_bytes, len(b"image-bytes"))
        self.assertIn("Mozilla/5.0", opener.request.get_header("User-agent"))
        self.assertEqual(opener.request.get_header("Sec-fetch-dest"), "image")
        self.assertIsNone(opener.request.get_header("Cookie"))

    def test_queue_uses_versioned_thumbnail_url_and_deduplicates(self):
        with self.Session() as db:
            config = update_cdn_warm_config(
                db,
                enabled=True,
                base_url="https://cdn.example.com",
                auto_new_uploads=True,
            )
            db.commit()
            self.assertTrue(config["valid"])
            image = self._image(db, media_version=4)
            task, outcome = enqueue_image_for_warm(db, image)
            self.assertEqual(outcome, "queued")
            self.assertEqual(task.target_url, f"https://cdn.example.com/media/{image.id}/thumbnail/4")
            db.commit()
            duplicate, duplicate_outcome = enqueue_image_for_warm(db, image)
            self.assertEqual(duplicate_outcome, "existing")
            self.assertEqual(duplicate.id, task.id)
            self.assertEqual(db.query(CdnWarmTask).count(), 1)
            self.assertEqual(cdn_warm_stats(db)["queued"], 1)
            self.assertTrue(get_cdn_warm_config(db)["enabled"])

    def test_expired_successful_thumbnail_returns_to_queue_and_progress_tracks_current_version(self):
        with self.Session() as db:
            update_cdn_warm_config(
                db,
                enabled=True,
                base_url="https://cdn.example.com",
                auto_new_uploads=True,
            )
            db.commit()
            image = self._image(db, media_version=2)
            task, _outcome = enqueue_image_for_warm(db, image)
            task.status = TASK_STATUS_SUCCESS
            task.finished_at = utcnow()
            db.commit()
            stats = cdn_warm_stats(db)
            self.assertEqual(stats["coverage_total"], 1)
            self.assertEqual(stats["coverage_fresh"], 1)
            self.assertEqual(stats["coverage_percentage"], 100)

            task.finished_at = utcnow() - timedelta(seconds=settings.media_public_shared_cache_seconds)
            db.commit()
            self.assertEqual(requeue_expired_cdn_warm_tasks(db), 1)
            db.refresh(task)
            self.assertEqual(task.status, TASK_STATUS_QUEUED)


if __name__ == "__main__":
    unittest.main()
