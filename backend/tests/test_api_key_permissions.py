import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import generate_api_key, settings
from app.database import Base, get_db
from app.main import app
from app.models import ApiKeyPolicy, AppSetting
from app.services.api_key_service import (
    ALL_API_KEY_SCOPES,
    API_KEY_POLICY_MIGRATION_KEY,
    api_key_hash,
    policy_scopes,
)
from app.utils.time import utcnow_naive


class ApiKeyPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-api-key-permissions-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'api-keys.db'}",
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

    def _add_key(self, scopes, *, expires_at=None, revoked_at=None, name="test"):
        key = generate_api_key()
        settings.api_keys = f"{name}:{key}"
        with self.SessionTesting() as db:
            db.add(AppSetting(key=API_KEY_POLICY_MIGRATION_KEY, value="completed"))
            db.add(
                ApiKeyPolicy(
                    key_hash=api_key_hash(key),
                    name=name,
                    scopes_json=json.dumps(list(scopes)),
                    expires_at=expires_at,
                    revoked_at=revoked_at,
                )
            )
            db.commit()
        return key

    @staticmethod
    def _headers(key):
        return {"Authorization": f"Bearer {key}"}

    def test_existing_key_is_migrated_with_every_permission_and_remains_visible(self):
        key = generate_api_key()
        settings.api_keys = f"legacy:{key}"

        response = self.client.get("/api/settings", headers=self._headers(key))

        self.assertEqual(response.status_code, 200)
        item = response.json()["operations_api_keys"][0]
        self.assertEqual(item["key"], key)
        self.assertTrue(item["full_access"])
        self.assertEqual(item["scopes"], list(ALL_API_KEY_SCOPES))
        with self.SessionTesting() as db:
            policy = db.query(ApiKeyPolicy).one()
            self.assertEqual(policy_scopes(policy), list(ALL_API_KEY_SCOPES))

    def test_limited_key_can_upload_but_cannot_read_private_data_or_control_system(self):
        key = self._add_key(["uploads:manage"])
        headers = self._headers(key)

        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/upload-tasks", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/images?public_only=false", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/stats", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/settings", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/updates/check", headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/api-keys/1/rotate", headers=headers).status_code, 403)
        self.assertEqual(self.client.delete("/api/images/999", headers=headers).status_code, 403)

    def test_settings_key_does_not_receive_other_api_keys(self):
        key = self._add_key(["settings:manage"])

        response = self.client.get("/api/settings", headers=self._headers(key))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["operations_api_keys"], [])

    def test_expired_and_revoked_keys_are_rejected(self):
        expired = self._add_key(["system:read"], expires_at=utcnow_naive() - timedelta(seconds=1), name="expired")
        self.assertEqual(self.client.get("/api/stats", headers=self._headers(expired)).status_code, 401)

        with self.SessionTesting() as db:
            db.query(ApiKeyPolicy).delete()
            db.query(AppSetting).delete()
            db.commit()
        revoked = self._add_key(["system:read"], revoked_at=utcnow_naive(), name="revoked")
        self.assertEqual(self.client.get("/api/stats", headers=self._headers(revoked)).status_code, 401)

    def test_all_permissions_cover_every_control_category(self):
        key = self._add_key(ALL_API_KEY_SCOPES, name="full")
        headers = self._headers(key)
        checks = [
            self.client.get("/api/images?public_only=false", headers=headers),
            self.client.get("/api/upload-tasks", headers=headers),
            self.client.put("/api/images/999", headers=headers, json={}),
            self.client.delete("/api/images/999", headers=headers),
            self.client.get("/api/stats", headers=headers),
            self.client.get("/api/settings", headers=headers),
            self.client.get("/api/updates/tasks", headers=headers),
            self.client.get("/api/settings/api-keys", headers=headers),
        ]
        for response in checks:
            self.assertNotIn(response.status_code, {401, 403})

        with patch(
            "app.api.updates.update_service.create_update_task",
            side_effect=ValueError("test reached update handler"),
        ):
            update = self.client.post("/api/updates/tasks", headers=headers, json={"dry_run": True})
        self.assertEqual(update.status_code, 422)
        self.assertIn("test reached update handler", update.json()["detail"])

    def test_key_crud_and_revoke_take_effect_immediately(self):
        manager_key = self._add_key(["api_keys:manage"], name="manager")
        headers = self._headers(manager_key)
        with patch("app.services.api_key_service.write_env"):
            created = self.client.post(
                "/api/settings/api-keys",
                headers=headers,
                json={"name": "uploader", "scopes": ["uploads:manage"], "expires_at": None},
            )
            self.assertEqual(created.status_code, 201)
            item = created.json()
            self.assertEqual(item["scopes"], ["uploads:manage"])
            self.assertEqual(self.client.get("/api/upload-tasks", headers=self._headers(item["key"])).status_code, 200)
            self.assertEqual(self.client.get("/api/stats", headers=self._headers(item["key"])).status_code, 403)

            updated = self.client.put(
                f"/api/settings/api-keys/{item['id']}",
                headers=headers,
                json={"name": "monitor", "scopes": ["system:read"], "expires_at": None},
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(self.client.get("/api/stats", headers=self._headers(item["key"])).status_code, 200)
            self.assertEqual(self.client.get("/api/upload-tasks", headers=self._headers(item["key"])).status_code, 403)

            rotated = self.client.post(f"/api/settings/api-keys/{item['id']}/rotate", headers=headers)
            self.assertEqual(rotated.status_code, 200)
            refreshed = rotated.json()
            self.assertEqual(refreshed["id"], item["id"])
            self.assertEqual(refreshed["name"], "monitor")
            self.assertEqual(refreshed["scopes"], ["system:read"])
            self.assertNotEqual(refreshed["key"], item["key"])
            self.assertEqual(self.client.get("/api/auth/me", headers=self._headers(item["key"])).status_code, 401)
            self.assertEqual(self.client.get("/api/stats", headers=self._headers(refreshed["key"])).status_code, 200)

            revoked = self.client.delete(f"/api/settings/api-keys/{item['id']}", headers=headers)
            self.assertEqual(revoked.status_code, 204)
            self.assertEqual(self.client.get("/api/auth/me", headers=self._headers(refreshed["key"])).status_code, 401)

    def test_openapi_documents_required_scopes(self):
        key = self._add_key(["system:read"])
        response = self.client.get("/api-docs/openapi.json", headers=self._headers(key))

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["paths"]["/api/images/upload"]["post"]["x-api-key-scopes"], ["uploads:manage"])
        self.assertEqual(
            schema["paths"]["/api/upload-tasks/{task_id}/retry"]["post"]["x-api-key-scopes"],
            ["uploads:manage"],
        )
        self.assertEqual(
            schema["paths"]["/api/upload-tasks/batch/actions"]["post"]["x-api-key-scopes"],
            ["uploads:manage"],
        )
        self.assertEqual(schema["paths"]["/api/updates/tasks"]["post"]["x-api-key-scopes"], ["updates:run"])
        self.assertEqual(schema["paths"]["/api/settings/api-keys"]["post"]["x-api-key-scopes"], ["api_keys:manage"])
        self.assertEqual(
            schema["paths"]["/api/settings/api-keys/{key_id}/rotate"]["post"]["x-api-key-scopes"],
            ["api_keys:manage"],
        )


if __name__ == "__main__":
    unittest.main()
