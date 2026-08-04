import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base
from app.models import AppSetting
from app.services import install_service
from app.services.admin_account_service import (
    ADMIN_PASSWORD_CHANGE_REQUIRED_KEY,
    ADMIN_PASSWORD_HASH_KEY,
    ADMIN_USERNAME_KEY,
    authenticate_admin,
    hash_password,
    update_admin_account,
    verify_password,
)


class AdminPasswordStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-password-storage-")
        self.root = Path(self.temp_dir.name)
        self.env_path = self.root / ".env"
        self.database_path = self.root / "test.db"
        self.database_url = f"sqlite:///{self.database_path.as_posix()}"
        self.engine = create_engine(
            self.database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.env_path_patch = patch.object(install_service, "ENV_PATH", self.env_path)
        self.env_path_patch.start()
        self.original_process_password = os.environ.pop(install_service.LEGACY_ADMIN_PASSWORD_ENV, None)

    def tearDown(self):
        if self.original_process_password is not None:
            os.environ[install_service.LEGACY_ADMIN_PASSWORD_ENV] = self.original_process_password
        else:
            os.environ.pop(install_service.LEGACY_ADMIN_PASSWORD_ENV, None)
        self.env_path_patch.stop()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _setting(self, key: str) -> str | None:
        with self.Session() as db:
            setting = db.get(AppSetting, key)
            return setting.value if setting else None

    def _mark_database_initialized(self) -> None:
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(128) NOT NULL)")
            connection.exec_driver_sql(
                "INSERT INTO alembic_version (version_num) VALUES ('0001_initial_schema')"
            )

    def test_new_install_never_writes_plaintext_admin_password(self):
        self.env_path.write_text(
            "AGMS_ADMIN_PASSWORD=stale-plaintext\nAGMS_STORAGE_PATH=/srv/images\n",
            encoding="utf-8",
        )
        with (
            patch.object(install_service, "test_database_url"),
            patch.object(install_service, "run_migrations"),
            patch.object(install_service, "initialize_admin") as initialize_admin,
            patch.object(install_service, "ensure_storage_dirs"),
            patch.object(install_service, "write_install_lock"),
            patch.object(install_service, "mark_installation_complete"),
            patch.object(install_service, "clear_install_token"),
            patch.object(install_service, "request_managed_restart"),
        ):
            install_service.perform_install(
                database_type="sqlite",
                database_url=self.database_url,
                admin_username="owner",
                admin_password="new-install-password",
            )

        initialize_admin.assert_called_once_with(self.database_url, "owner", "new-install-password")
        content = self.env_path.read_text(encoding="utf-8")
        self.assertNotIn("AGMS_ADMIN_PASSWORD", content)
        self.assertNotIn("new-install-password", content)
        self.assertNotIn("stale-plaintext", content)
        self.assertIn("AGMS_STORAGE_PATH=/srv/images", content)

    def test_legacy_password_is_hashed_before_env_is_scrubbed(self):
        self.env_path.write_text(
            "AGMS_ADMIN_USERNAME=legacy-owner\nAGMS_ADMIN_PASSWORD=legacy-password\n",
            encoding="utf-8",
        )

        result = install_service.migrate_legacy_admin_password(self.database_url)

        self.assertEqual(result, "password-hash-migrated")
        self.assertEqual(self._setting(ADMIN_USERNAME_KEY), "legacy-owner")
        self.assertTrue(verify_password("legacy-password", self._setting(ADMIN_PASSWORD_HASH_KEY)))
        self.assertNotIn("AGMS_ADMIN_PASSWORD", self.env_path.read_text(encoding="utf-8"))

    def test_stale_env_password_never_overwrites_database_password(self):
        current_hash = hash_password("current-database-password")
        with self.Session() as db:
            db.add_all(
                [
                    AppSetting(key=ADMIN_USERNAME_KEY, value="owner"),
                    AppSetting(key=ADMIN_PASSWORD_HASH_KEY, value=current_hash),
                ]
            )
            db.commit()
        self.env_path.write_text("AGMS_ADMIN_PASSWORD=obsolete-password\n", encoding="utf-8")

        result = install_service.migrate_legacy_admin_password(self.database_url)

        self.assertEqual(result, "password-hash-present")
        stored_hash = self._setting(ADMIN_PASSWORD_HASH_KEY)
        self.assertEqual(stored_hash, current_hash)
        self.assertTrue(verify_password("current-database-password", stored_hash))
        self.assertFalse(verify_password("obsolete-password", stored_hash))
        self.assertNotIn("AGMS_ADMIN_PASSWORD", self.env_path.read_text(encoding="utf-8"))

    def test_missing_database_hash_rejects_all_passwords(self):
        with self.Session() as db:
            db.add(AppSetting(key=ADMIN_USERNAME_KEY, value="admin"))
            db.commit()

        with self.Session() as db:
            self.assertIsNone(authenticate_admin(db, "admin", "admin123"))
            self.assertIsNone(authenticate_admin(db, "admin", "any-password"))

    def test_installed_legacy_default_is_migrated_and_requires_replacement(self):
        self._mark_database_initialized()

        result = install_service.migrate_legacy_admin_password(self.database_url)

        self.assertEqual(result, "legacy-default-hash-migrated")
        self.assertTrue(
            verify_password(
                install_service.LEGACY_BUILTIN_ADMIN_PASSWORD,
                self._setting(ADMIN_PASSWORD_HASH_KEY),
            )
        )
        self.assertEqual(self._setting(ADMIN_PASSWORD_CHANGE_REQUIRED_KEY), "1")

        with self.Session() as db:
            account = authenticate_admin(db, "admin", install_service.LEGACY_BUILTIN_ADMIN_PASSWORD)
            self.assertIsNotNone(account)
            self.assertTrue(account.password_change_required)
            update_admin_account(db, password="replacement-password")
            db.commit()

        self.assertIsNone(self._setting(ADMIN_PASSWORD_CHANGE_REQUIRED_KEY))
        self.assertTrue(verify_password("replacement-password", self._setting(ADMIN_PASSWORD_HASH_KEY)))
        self.assertFalse(
            verify_password(
                install_service.LEGACY_BUILTIN_ADMIN_PASSWORD,
                self._setting(ADMIN_PASSWORD_HASH_KEY),
            )
        )


if __name__ == "__main__":
    unittest.main()
