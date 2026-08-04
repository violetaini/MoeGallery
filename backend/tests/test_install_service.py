import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.services.admin_account_service import authenticate_admin
from app.services import install_service


class InstallServiceTests(unittest.TestCase):
    def setUp(self):
        self.original_database_url = settings.database_url
        self.original_storage_path = settings.storage_path
        self.original_token_ttl = settings.install_token_ttl_seconds
        self.original_api_keys = settings.api_keys
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-install-test-")
        self.temp_path = Path(self.temp_dir.name)
        settings.storage_path = self.temp_path / "storage"
        settings.install_token_ttl_seconds = 7200
        settings.api_keys = ""
        self.install_lock_patch = patch.object(
            install_service,
            "INSTALL_LOCK_PATH",
            self.temp_path / "installed.lock",
        )
        self.env_path_patch = patch.object(
            install_service,
            "ENV_PATH",
            self.temp_path / ".env",
        )
        self.install_lock_patch.start()
        self.env_path_patch.start()

    def tearDown(self):
        self.env_path_patch.stop()
        self.install_lock_patch.stop()
        settings.database_url = self.original_database_url
        settings.storage_path = self.original_storage_path
        settings.install_token_ttl_seconds = self.original_token_ttl
        settings.api_keys = self.original_api_keys
        self.temp_dir.cleanup()

    def _set_sqlite_database(self, name: str) -> str:
        database_url = f"sqlite:///{Path(self.temp_dir.name) / name}"
        settings.database_url = database_url
        return database_url

    def test_empty_alembic_version_table_is_not_initialized(self):
        database_url = self._set_sqlite_database("empty-version.db")
        engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(128) NOT NULL)"))
        finally:
            engine.dispose()

        self.assertFalse(install_service.current_database_is_initialized())

    def test_migrations_without_admin_are_not_initialized(self):
        database_url = self._set_sqlite_database("populated-version.db")
        engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(128) NOT NULL)"))
                connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0001_initial_schema')"))
        finally:
            engine.dispose()

        self.assertFalse(install_service.current_database_is_initialized())

    def _create_install_state(self, name: str, values: dict[str, str]) -> None:
        database_url = self._set_sqlite_database(name)
        engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(128) NOT NULL)"))
                connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0011_api_key_policies')"))
                connection.execute(text("CREATE TABLE app_settings (key VARCHAR(120) PRIMARY KEY, value TEXT NOT NULL)"))
                for key, value in values.items():
                    connection.execute(
                        text("INSERT INTO app_settings (key, value) VALUES (:key, :value)"),
                        {"key": key, "value": value},
                    )
        finally:
            engine.dispose()

    def test_legacy_admin_credentials_are_initialized(self):
        self._create_install_state(
            "legacy.db",
            {
                install_service.ADMIN_USERNAME_KEY: "admin",
                install_service.ADMIN_PASSWORD_HASH_KEY: "pbkdf2:placeholder",
            },
        )

        self.assertTrue(install_service.current_database_is_initialized())

    def test_in_progress_marker_keeps_partial_database_retryable(self):
        self._create_install_state(
            "partial.db",
            {
                install_service.ADMIN_USERNAME_KEY: "admin",
                install_service.ADMIN_PASSWORD_HASH_KEY: "pbkdf2:placeholder",
                install_service.INSTALLATION_IN_PROGRESS_KEY: "2026-07-30T00:00:00+00:00",
            },
        )

        self.assertFalse(install_service.current_database_is_initialized())

    def test_completed_marker_is_initialized(self):
        self._create_install_state(
            "completed.db",
            {install_service.INSTALLATION_COMPLETED_KEY: "2026-07-30T00:00:00+00:00"},
        )

        self.assertTrue(install_service.current_database_is_initialized())

    def test_install_token_is_hashed_and_expires(self):
        token = "t" * 48
        with patch.object(install_service, "is_installed", return_value=False), patch(
            "app.services.install_service.time.time",
            return_value=1_000,
        ):
            self.assertEqual(install_service.prepare_install_token(token), token)

        state_content = install_service.install_token_state_path().read_text(encoding="utf-8")
        self.assertNotIn(token, state_content)
        with patch("app.services.install_service.time.time", return_value=1_001):
            self.assertTrue(install_service.verify_install_token(token))
            self.assertFalse(install_service.verify_install_token("wrong-token"))
        with patch("app.services.install_service.time.time", return_value=9_000):
            self.assertFalse(install_service.verify_install_token(token))
        self.assertFalse(install_service.install_token_state_path().exists())

    def test_installation_lock_rejects_concurrent_entry(self):
        with install_service.installation_lock():
            with self.assertRaises(install_service.InstallInProgressError):
                with install_service.installation_lock():
                    self.fail("concurrent installation unexpectedly acquired the lock")

    def test_pending_install_lock_does_not_mark_partial_database_installed(self):
        self._create_install_state(
            "pending-lock.db",
            {install_service.INSTALLATION_IN_PROGRESS_KEY: "2026-07-30T00:00:00+00:00"},
        )
        install_service.write_install_lock("sqlite", settings.database_url, state="pending")

        self.assertFalse(install_service.is_installed())

    def test_fresh_sqlite_install_completes_end_to_end(self):
        database_url = self._set_sqlite_database("fresh-install.db")
        install_token = "fresh-install-token-" + "x" * 32
        admin_password = "Strong-Local-Password-2026"
        self.assertEqual(install_service.prepare_install_token(install_token), install_token)

        with patch.object(install_service, "request_managed_restart", return_value=True):
            with install_service.installation_lock():
                result = install_service.perform_install(
                    database_type="sqlite",
                    database_url=database_url,
                    admin_username="local-admin",
                    admin_password=admin_password,
                )

        self.assertTrue(result["installed"])
        self.assertTrue(install_service.current_database_is_initialized())
        self.assertTrue(install_service.INSTALL_LOCK_PATH.exists())
        self.assertEqual(install_service.read_install_lock()["state"], "completed")
        self.assertFalse(install_service.install_token_state_path().exists())
        self.assertFalse(install_service.verify_install_token(install_token))

        env_content = install_service.ENV_PATH.read_text(encoding="utf-8")
        self.assertIn("AGMS_AUTH_SECRET=", env_content)
        self.assertIn("AGMS_API_KEYS=default:agms_", env_content)
        self.assertNotIn("AGMS_ADMIN_PASSWORD", env_content)
        self.assertNotIn(admin_password, env_content)

        engine = install_service.create_database_engine(database_url)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        try:
            with Session() as db:
                account = authenticate_admin(db, "local-admin", admin_password)
                self.assertIsNotNone(account)
                self.assertFalse(account.password_change_required)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
