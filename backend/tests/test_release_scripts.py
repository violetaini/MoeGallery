import importlib.util
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class ReleaseScriptSafetyTests(unittest.TestCase):
    DATABASE_EXCLUSIONS = ("*.db", "*.db-*", "*.sqlite", "*.sqlite-*", "*.sqlite3", "*.sqlite3-*")
    CACHE_EXCLUSIONS = ("__pycache__/", "*.pyc", "*.pyo")

    def test_reinstall_sync_preserves_application_data(self):
        script = (ROOT_DIR / "install.sh").read_text(encoding="utf-8")
        sync_start = script.index("rsync -a --delete")
        sync_end = script.index('"$STAGE_DIR/" "$APP_DIR/"', sync_start)
        sync_block = script[sync_start:sync_end]

        expected_exclusions = (
            ".env",
            "installed.lock",
            "frontend/dist/.user.ini",
            "storage/",
            "logs/",
            "backups/",
            "venv/",
            *self.DATABASE_EXCLUSIONS,
        )
        for exclusion in expected_exclusions:
            with self.subTest(exclusion=exclusion):
                self.assertIn(f"--exclude='{exclusion}'", sync_block)

    def test_panel_upgrade_preserves_supported_sqlite_names(self):
        script = (ROOT_DIR / "scripts" / "upgrade_release.sh").read_text(encoding="utf-8")
        sync_start = script.index("rsync -a --delete")
        sync_end = script.index('"$STAGE_DIR/backend/" "$APP_DIR/backend/"', sync_start)
        sync_block = script[sync_start:sync_end]

        for exclusion in self.DATABASE_EXCLUSIONS:
            with self.subTest(exclusion=exclusion):
                self.assertIn(f"--exclude='{exclusion}'", sync_block)

    def test_panel_upgrade_does_not_sync_python_caches(self):
        script = (ROOT_DIR / "scripts" / "upgrade_release.sh").read_text(encoding="utf-8")
        scripts_sync_end = script.index('"$STAGE_DIR/scripts/" "$APP_DIR/scripts/"')
        scripts_sync_start = script.rfind("run rsync -a --delete", 0, scripts_sync_end)
        scripts_sync_block = script[scripts_sync_start:scripts_sync_end]

        for exclusion in self.CACHE_EXCLUSIONS:
            with self.subTest(exclusion=exclusion):
                self.assertIn(f"--exclude='{exclusion}'", scripts_sync_block)

    def test_backup_and_restore_cover_supported_sqlite_names(self):
        for relative_path in ("scripts/backup_before_upgrade.sh", "scripts/restore_upgrade_backup.sh"):
            script = (ROOT_DIR / relative_path).read_text(encoding="utf-8")
            with self.subTest(script=relative_path):
                for exclusion in self.DATABASE_EXCLUSIONS:
                    self.assertIn(exclusion, script)

    def test_restore_does_not_touch_python_caches(self):
        script = (ROOT_DIR / "scripts" / "restore_upgrade_backup.sh").read_text(encoding="utf-8")
        for destination in ('"$APP_DIR/backend/"', '"$APP_DIR/scripts/"'):
            sync_end = script.index(destination)
            sync_start = script.rfind("rsync -a --delete", 0, sync_end)
            sync_block = script[sync_start:sync_end]
            with self.subTest(destination=destination):
                for exclusion in self.CACHE_EXCLUSIONS:
                    self.assertIn(f"--exclude='{exclusion}'", sync_block)

    def test_release_packager_ignores_supported_sqlite_names(self):
        module_path = ROOT_DIR / "scripts" / "package_release.py"
        spec = importlib.util.spec_from_file_location("moegallery_package_release", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        database_files = [
            "library.db",
            "library.db-wal",
            "library.db-shm",
            "library.sqlite",
            "library.sqlite-journal",
            "library.sqlite3",
            "library.sqlite3-wal",
        ]

        ignored = module._ignore_backend("backend", database_files + ["models.py"])

        self.assertTrue(set(database_files).issubset(ignored))
        self.assertNotIn("models.py", ignored)


if __name__ == "__main__":
    unittest.main()
