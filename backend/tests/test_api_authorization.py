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

from app.config import generate_api_key, settings
from app.database import Base, get_db
from app.main import app


class ApiAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-api-auth-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'api-auth.db'}",
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
        self.original_api_keys = settings.api_keys
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        settings.api_keys = self.original_api_keys
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_public_endpoints_allow_anonymous_but_reject_bad_authorization_header(self):
        public_get_paths = [
            "/api/health",
            "/api/settings/public",
            "/api/images",
            "/api/works",
            "/api/characters",
            "/api/tags",
            "/api/search?q=none",
        ]
        for path in public_get_paths:
            with self.subTest(path=path, mode="anonymous"):
                self.assertEqual(self.client.get(path).status_code, 200)
            with self.subTest(path=path, mode="bad-bearer"):
                response = self.client.get(path, headers={"Authorization": "Bearer wrong-token"})
                self.assertEqual(response.status_code, 401)
            with self.subTest(path=path, mode="bad-scheme"):
                response = self.client.get(path, headers={"Authorization": "Basic wrong-token"})
                self.assertEqual(response.status_code, 401)

    def test_protected_get_endpoints_reject_missing_and_bad_token(self):
        protected_get_paths = [
            "/api/auth/me",
            "/api/settings",
            "/api/stats",
            "/api/system/health",
            "/api/updates/check",
            "/api/upload-tasks",
            "/api/imports/metadata/template?format=csv",
            "/api-docs",
            "/api-docs/openapi.json",
            "/openapi.json",
        ]
        for path in protected_get_paths:
            with self.subTest(path=path, mode="missing"):
                self.assertEqual(self.client.get(path).status_code, 401)
            with self.subTest(path=path, mode="bad-bearer"):
                response = self.client.get(path, headers={"Authorization": "Bearer wrong-token"})
                self.assertEqual(response.status_code, 401)

    def test_protected_write_endpoints_reject_missing_and_bad_token(self):
        requests = [
            ("post", "/api/auth/logout", None),
            ("post", "/api/settings/auth-secret/rotate", None),
            ("post", "/api/settings/api-keys/reset", None),
            ("post", "/api/updates/tasks", {"dry_run": True, "force": True}),
            ("delete", "/api/images/1", None),
            ("delete", "/api/works/1", None),
            ("delete", "/api/characters/1", None),
        ]
        for method, path, body in requests:
            caller = getattr(self.client, method)
            kwargs = {"json": body} if body is not None else {}
            with self.subTest(path=path, method=method, mode="missing"):
                self.assertEqual(caller(path, **kwargs).status_code, 401)
            with self.subTest(path=path, method=method, mode="bad-bearer"):
                response = caller(path, headers={"Authorization": "Bearer wrong-token"}, **kwargs)
                self.assertEqual(response.status_code, 401)

    def test_valid_api_key_can_call_protected_endpoint(self):
        api_key = generate_api_key()
        settings.api_keys = f"ops:{api_key}"

        response = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {api_key}"})

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
