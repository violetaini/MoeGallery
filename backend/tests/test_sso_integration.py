import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app import sso


class SsoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"AGMS_AUTH_MODE": "sso"})
        self.env.start()
        self.client = TestClient(app, client=("127.0.0.1", 50000))

    def tearDown(self):
        self.env.stop()

    def test_sso_configuration_and_local_login_disabled(self):
        self.assertEqual(self.client.get("/api/auth/config").json()["mode"], "sso")
        self.assertEqual(self.client.post("/api/auth/login", json={"username": "any", "password": "any"}).status_code, 410)

    def test_browser_start_and_invalid_callback(self):
        with patch("app.sso.call", return_value={"location": "https://sso.chitanda.net/oauth/authorize", "cookies": ["test_flow=ok; HttpOnly; Secure; Path=/"]}):
            response = self.client.get("/api/auth/sso/start", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["location"].startswith("https://sso.chitanda.net/"))
            self.assertIn("HttpOnly", response.headers["set-cookie"])
        with patch("app.sso.call", side_effect=HTTPException(401, "Invalid flow")):
            response = self.client.get("/api/auth/sso/callback?code=bad&state=bad", follow_redirects=False)
            self.assertEqual(response.headers["location"], "/login?sso_error=1")

    def test_legacy_bearer_token_does_not_enter_sso_mode(self):
        self.assertEqual(self.client.get("/api/stats", headers={"Authorization": "Bearer legacy-token"}).status_code, 401)

    def test_local_profile_is_derived_only_from_the_authenticated_agent(self):
        from starlette.requests import Request
        request = Request({"type": "http", "method": "GET", "path": "/api/stats", "headers": [], "client": ("127.0.0.1", 20000), "server": ("testserver", 80), "scheme": "http", "query_string": b""})
        with patch("app.sso.call", return_value={"username": "sso-admin", "subject": "usr_fixture", "roles": ["admin"]}):
            self.assertEqual(sso.validate(request)["auth_type"], "sso")
        with patch("app.sso.call", side_effect=HTTPException(401, "Revoked")):
            with self.assertRaises(HTTPException):
                sso.validate(request)


if __name__ == "__main__":
    unittest.main()
