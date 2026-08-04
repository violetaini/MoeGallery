import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api import install as install_api
from app.config import settings
from app.main import app
from app.services.install_service import InstallInProgressError


class InstallSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_max_attempts = settings.install_rate_limit_max_attempts
        self.original_window = settings.install_rate_limit_window_seconds
        settings.install_rate_limit_max_attempts = 8
        settings.install_rate_limit_window_seconds = 300
        install_api._install_attempts.clear()
        self.client = TestClient(app)
        self.payload = {
            "database_type": "sqlite",
            "admin_username": "owner",
            "admin_password": "a-secure-password-2026",
        }

    def tearDown(self):
        settings.install_rate_limit_max_attempts = self.original_max_attempts
        settings.install_rate_limit_window_seconds = self.original_window
        install_api._install_attempts.clear()

    def test_missing_or_wrong_install_token_is_rejected(self):
        with patch.object(install_api, "is_installed", return_value=False), patch.object(
            install_api,
            "verify_install_token",
            return_value=False,
        ):
            missing = self.client.post("/api/install", json=self.payload)
            wrong = self.client.post(
                "/api/install",
                json=self.payload,
                headers={"X-Install-Token": "wrong"},
            )

        self.assertEqual(missing.status_code, 403)
        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(missing.json()["detail"], wrong.json()["detail"])

    def test_invalid_install_token_is_rate_limited(self):
        settings.install_rate_limit_max_attempts = 2
        with patch.object(install_api, "is_installed", return_value=False), patch.object(
            install_api,
            "verify_install_token",
            return_value=False,
        ):
            for _ in range(2):
                self.assertEqual(self.client.post("/api/install", json=self.payload).status_code, 403)
            blocked = self.client.post("/api/install", json=self.payload)

        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_valid_token_is_not_blocked_by_failed_attempt_counter(self):
        install_api._install_attempts["testclient"] = [1_000] * 20
        result = {"installed": True, "database_type": "sqlite", "restart_required": True}
        with patch("app.api.install.time.time", return_value=1_001), patch.object(
            install_api,
            "is_installed",
            return_value=False,
        ), patch.object(install_api, "verify_install_token", return_value=True), patch.object(
            install_api,
            "installation_lock",
            return_value=nullcontext(),
        ), patch.object(install_api, "perform_install", return_value=result):
            response = self.client.post(
                "/api/install",
                json=self.payload,
                headers={"X-Install-Token": "valid-install-token"},
            )

        self.assertEqual(response.status_code, 201)

    def test_valid_token_runs_install_once(self):
        result = {"installed": True, "database_type": "sqlite", "restart_required": True}
        with patch.object(install_api, "is_installed", return_value=False), patch.object(
            install_api,
            "verify_install_token",
            return_value=True,
        ), patch.object(install_api, "installation_lock", return_value=nullcontext()), patch.object(
            install_api,
            "perform_install",
            return_value=result,
        ) as perform:
            response = self.client.post(
                "/api/install",
                json=self.payload,
                headers={"X-Install-Token": "valid-install-token"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), result)
        perform.assert_called_once()

    def test_concurrent_install_returns_locked(self):
        with patch.object(install_api, "is_installed", return_value=False), patch.object(
            install_api,
            "verify_install_token",
            return_value=True,
        ), patch.object(
            install_api,
            "installation_lock",
            side_effect=InstallInProgressError("busy"),
        ):
            response = self.client.post(
                "/api/install",
                json=self.payload,
                headers={"X-Install-Token": "valid-install-token"},
            )

        self.assertEqual(response.status_code, 423)

    def test_internal_install_error_is_not_exposed(self):
        with self.assertLogs(install_api.logger, level="ERROR") as captured:
            with patch.object(install_api, "is_installed", return_value=False), patch.object(
                install_api,
                "verify_install_token",
                return_value=True,
            ), patch.object(install_api, "installation_lock", return_value=nullcontext()), patch.object(
                install_api,
                "perform_install",
                side_effect=RuntimeError("mysql://root:secret@example.invalid/database"),
            ):
                response = self.client.post(
                    "/api/install",
                    json=self.payload,
                    headers={"X-Install-Token": "valid-install-token"},
                )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("secret", response.json()["detail"])
        self.assertNotIn("secret", "\n".join(captured.output))

    def test_weak_admin_password_is_rejected_before_install(self):
        weak_payload = {**self.payload, "admin_password": "admin123"}
        response = self.client.post(
            "/api/install",
            json=weak_payload,
            headers={"X-Install-Token": "unused"},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
