import json
import sys
import time
import unittest
import tempfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import auth
from app.api import auth as auth_api
from app.config import generate_api_key, generate_auth_secret, is_weak_auth_secret, settings
from app.database import Base, get_db
from app.main import app
from app.models import AdminSession


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None, client_host: str = "127.0.0.1"):
        self.headers = headers or {}
        self.client = _FakeClient(client_host)


class AuthSecretSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_secret = settings.auth_secret
        settings.auth_secret = generate_auth_secret()

    def tearDown(self):
        settings.auth_secret = self.original_secret

    def test_generated_secret_is_not_weak(self):
        self.assertFalse(is_weak_auth_secret(generate_auth_secret()))

    def test_token_invalid_after_secret_rotation(self):
        token = auth.create_access_token("admin")
        settings.auth_secret = generate_auth_secret()

        with self.assertRaises(HTTPException):
            auth.verify_access_token(token)

    def test_rejects_valid_signature_with_wrong_token_type(self):
        now = int(time.time())
        payload = auth._b64encode(
            json.dumps(
                {
                    "sub": "admin",
                    "typ": "api-key",
                    "jti": "test",
                    "sv": auth._secret_version(),
                    "iat": now,
                    "nbf": now,
                    "exp": now + settings.auth_token_ttl_seconds,
                    "iss": settings.auth_issuer,
                    "aud": settings.auth_audience,
                },
                separators=(",", ":"),
            ).encode("utf-8")
        )
        token = f"{payload}.{auth._sign(payload)}"

        with self.assertRaises(HTTPException):
            auth.verify_access_token(token)


class LoginRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.original_max_attempts = settings.login_rate_limit_max_attempts
        self.original_window_seconds = settings.login_rate_limit_window_seconds
        settings.login_rate_limit_max_attempts = 2
        settings.login_rate_limit_window_seconds = 300
        auth_api._login_attempts.clear()

    def tearDown(self):
        settings.login_rate_limit_max_attempts = self.original_max_attempts
        settings.login_rate_limit_window_seconds = self.original_window_seconds
        auth_api._login_attempts.clear()

    def test_trusted_proxy_uses_rightmost_forwarded_ip(self):
        request = _FakeRequest(
            headers={"x-forwarded-for": "9.9.9.9, 8.8.8.8"},
            client_host="127.0.0.1",
        )

        self.assertEqual(auth_api._client_ip(request), "8.8.8.8")

    def test_untrusted_peer_cannot_spoof_forwarded_ip(self):
        request = _FakeRequest(
            headers={"x-forwarded-for": "1.1.1.1"},
            client_host="9.9.9.9",
        )

        self.assertEqual(auth_api._client_ip(request), "9.9.9.9")

    def test_rate_limit_applies_to_username_across_ips(self):
        for ip in ("1.1.1.1", "8.8.8.8"):
            request = _FakeRequest(headers={"x-forwarded-for": ip})
            auth_api._enforce_login_rate_limit(request, "Admin")
            auth_api._record_login_failure(request, "Admin")

        blocked = _FakeRequest(headers={"x-forwarded-for": "9.9.9.9"})
        with self.assertRaises(HTTPException) as raised:
            auth_api._enforce_login_rate_limit(blocked, " admin ")
        self.assertEqual(raised.exception.status_code, 429)

    def test_rate_limit_applies_to_real_ip_when_forwarded_prefix_changes(self):
        for index, spoofed_ip in enumerate(("9.9.9.9", "8.8.8.8")):
            request = _FakeRequest(headers={"x-forwarded-for": f"{spoofed_ip}, 1.1.1.1"})
            auth_api._enforce_login_rate_limit(request, f"probe-{index}")
            auth_api._record_login_failure(request, f"probe-{index}")

        blocked = _FakeRequest(headers={"x-forwarded-for": "7.7.7.7, 1.1.1.1"})
        with self.assertRaises(HTTPException) as raised:
            auth_api._enforce_login_rate_limit(blocked, "another-probe")
        self.assertEqual(raised.exception.status_code, 429)


class CookieSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-auth-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'auth-test.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

        def override_get_db():
            db = self.SessionTesting()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.env_path = BACKEND_DIR.parent / ".env"
        self.original_env = self.env_path.read_text(encoding="utf-8") if self.env_path.exists() else None
        self.original_secret = settings.auth_secret
        self.original_api_keys = settings.api_keys
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        settings.auth_secret = self.original_secret
        settings.api_keys = self.original_api_keys
        if self.original_env is None:
            if self.env_path.exists():
                self.env_path.unlink()
        else:
            self.env_path.write_text(self.original_env, encoding="utf-8")
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_login_sets_httponly_cookie_and_me_uses_session(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("agms_admin_session=", response.headers.get("set-cookie", ""))
        self.assertIn("HttpOnly", response.headers.get("set-cookie", ""))
        self.assertEqual(response.json()["access_token"], "")

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], settings.admin_username)

    def test_write_request_requires_csrf_header(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        self.assertEqual(login.status_code, 200)

        blocked = self.client.post("/api/settings/auth-secret/rotate")
        self.assertEqual(blocked.status_code, 403)

    def test_logout_revokes_session(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        self.assertEqual(login.status_code, 200)
        csrf = self.client.cookies.get("agms_admin_csrf")
        logout = self.client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        self.assertEqual(logout.status_code, 200)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_rotate_secret_revokes_active_sessions(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        self.assertEqual(login.status_code, 200)
        old_session_cookie = self.client.cookies.get("agms_admin_session")
        csrf = self.client.cookies.get("agms_admin_csrf")

        response = self.client.post("/api/settings/auth-secret/rotate", headers={"X-CSRF-Token": csrf})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["rotated"])
        self.assertGreaterEqual(response.json()["revoked_sessions"], 1)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 401)

        old_cookie_me = self.client.get(
            "/api/auth/me",
            headers={"Cookie": f"agms_admin_session={old_session_cookie}"},
        )
        self.assertEqual(old_cookie_me.status_code, 401)

    def test_api_key_can_access_admin_endpoint_without_cookie_or_csrf(self):
        api_key = generate_api_key()
        settings.api_keys = f"ops:{api_key}"

        response = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {api_key}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], settings.admin_username)

        health = self.client.get("/api/system/health", headers={"Authorization": f"Bearer {api_key}"})
        self.assertEqual(health.status_code, 200)

    def test_invalid_api_key_is_rejected(self):
        settings.api_keys = f"ops:{generate_api_key()}"

        response = self.client.get("/api/auth/me", headers={"Authorization": "Bearer wrong-key"})
        self.assertEqual(response.status_code, 401)

    def test_api_docs_are_protected_and_accept_api_key(self):
        api_key = generate_api_key()
        settings.api_keys = f"ops:{api_key}"

        blocked = self.client.get("/api-docs")
        self.assertEqual(blocked.status_code, 401)

        docs = self.client.get("/api-docs", headers={"Authorization": f"Bearer {api_key}"})
        self.assertEqual(docs.status_code, 200)
        self.assertIn("api-reference", docs.text)

        openapi = self.client.get("/api-docs/openapi.json", headers={"Authorization": f"Bearer {api_key}"})
        self.assertEqual(openapi.status_code, 200)
        self.assertIn("OperationsApiKey", openapi.json()["components"]["securitySchemes"])


if __name__ == "__main__":
    unittest.main()
