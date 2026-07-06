import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.auth import require_admin
from app.database import get_db
from app.main import app
from app.services import update_service
from app.services.release_service import LATEST_RELEASE_URL, build_latest_release_url


class ReleaseServiceTests(unittest.TestCase):
    def test_build_latest_release_url_supports_proxy_modes(self):
        self.assertEqual(build_latest_release_url(""), LATEST_RELEASE_URL)
        self.assertEqual(
            build_latest_release_url("https://gh-proxy.example.com/"),
            f"https://gh-proxy.example.com/{LATEST_RELEASE_URL}",
        )
        self.assertEqual(
            build_latest_release_url("https://proxy.example.com/?target={raw_url}"),
            f"https://proxy.example.com/?target={LATEST_RELEASE_URL}",
        )
        self.assertIn(
            "https%3A%2F%2Fapi.github.com",
            build_latest_release_url("https://proxy.example.com/?target={url}"),
        )


class UpdateServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-update-test-")
        self.original_storage_path = settings.storage_path
        self.original_update_trigger_command = settings.update_trigger_command
        settings.storage_path = Path(self.temp_dir.name) / "storage"
        settings.update_trigger_command = ""

    def tearDown(self):
        settings.storage_path = self.original_storage_path
        settings.update_trigger_command = self.original_update_trigger_command
        self.temp_dir.cleanup()

    def _fake_release(self):
        return {
            "available": True,
            "version": "v9.9.9",
            "url": "https://github.com/violetaini/MoeGallery/releases/tag/v9.9.9",
            "assets": [
                {
                    "name": "MoeGallery-v9.9.9.tar.gz",
                    "size": 100,
                    "browser_download_url": "https://example.com/MoeGallery-v9.9.9.tar.gz",
                },
                {
                    "name": "SHA256SUMS.txt",
                    "size": 80,
                    "browser_download_url": "https://example.com/SHA256SUMS.txt",
                },
            ],
        }

    def test_create_update_task_persists_task_and_blocks_concurrent_tasks(self):
        with (
            patch("app.services.update_service.current_app_version", return_value="v1.0.0"),
            patch("app.services.update_service.latest_release_info", return_value=self._fake_release()),
            patch("app.services.update_service.trigger_update_task", return_value=None),
        ):
            task = update_service.create_update_task(None, dry_run=True)

        self.assertEqual(task["status"], "queued")
        self.assertEqual(task["target_version"], "v9.9.9")
        self.assertEqual(task["archive_name"], "MoeGallery-v9.9.9.tar.gz")
        self.assertTrue(update_service.task_file(task["id"]).exists())

        with (
            patch("app.services.update_service.current_app_version", return_value="v1.0.0"),
            patch("app.services.update_service.latest_release_info", return_value=self._fake_release()),
            patch("app.services.update_service.trigger_update_task", return_value=None),
        ):
            with self.assertRaises(ValueError):
                update_service.create_update_task(None, dry_run=True)


class UpdateApiTests(unittest.TestCase):
    def setUp(self):
        def override_admin():
            return {"sub": "admin"}

        def override_db():
            yield None

        app.dependency_overrides[require_admin] = override_admin
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)

    def test_update_check_endpoint(self):
        with patch(
            "app.api.updates.update_service.check_for_updates",
            return_value={
                "current_version": "v1.0.0",
                "latest_release": {
                    "available": True,
                    "version": "v1.1.0",
                    "url": "https://example.com/releases/v1.1.0",
                    "assets": [],
                    "proxied": False,
                    "checked_at": 1,
                    "message": "ok",
                },
                "update_available": True,
                "updater_available": True,
                "updater_mode": "command",
            },
        ):
            response = self.client.get("/api/updates/check")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["update_available"])

    def test_create_update_task_endpoint(self):
        now = datetime.now(UTC).isoformat()
        with patch(
            "app.api.updates.update_service.create_update_task",
            return_value={
                "id": "a" * 32,
                "status": "queued",
                "current_version": "v1.0.0",
                "target_version": "v1.1.0",
                "release_url": "https://example.com/releases/v1.1.0",
                "archive_url": "https://example.com/MoeGallery-v1.1.0.tar.gz",
                "checksum_url": "https://example.com/SHA256SUMS.txt",
                "archive_name": "MoeGallery-v1.1.0.tar.gz",
                "dry_run": True,
                "progress": 0,
                "message": "等待更新任务启动",
                "log": ["created"],
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "finished_at": None,
            },
        ):
            response = self.client.post("/api/updates/tasks", json={"dry_run": True, "force": True})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["id"], "a" * 32)


if __name__ == "__main__":
    unittest.main()
