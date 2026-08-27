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

    def test_upgrade_and_restore_avoid_metadata_preservation_failures(self):
        upgrade = (ROOT_DIR / "scripts" / "upgrade_release.sh").read_text(encoding="utf-8")
        restore = (ROOT_DIR / "scripts" / "restore_upgrade_backup.sh").read_text(encoding="utf-8")

        self.assertNotIn("cp -a", upgrade)
        self.assertNotIn("cp -a", restore)
        self.assertIn('run cp -f "$STAGE_DIR/$file" "$APP_DIR/$file"', upgrade)
        self.assertIn('cp -f "$WORK_DIR/$file" "$APP_DIR/$file"', restore)
        self.assertIn('cp -f "$BACKUP_DIR/env/.env" "$APP_DIR/.env"', restore)
        self.assertIn('cp -f "$BACKUP_DIR/install/installed.lock" "$APP_DIR/installed.lock"', restore)
        self.assertIn('cp -f "$BACKUP_DIR/install/VERSION" "$APP_DIR/VERSION"', restore)
        metadata_flags = "--no-times --no-owner --no-group --no-perms"
        self.assertGreaterEqual(upgrade.count(metadata_flags), 4)
        self.assertGreaterEqual(restore.count(metadata_flags), 5)
        self.assertNotIn("shutil.copy2", restore)
        self.assertNotIn("shutil.copymode", restore)

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

    def test_scheduled_backup_includes_durable_images_and_bounded_retention(self):
        scheduled_backup = (ROOT_DIR / "scripts" / "backup_gallery.sh").read_text(encoding="utf-8")
        upgrade_backup = (ROOT_DIR / "scripts" / "backup_before_upgrade.sh").read_text(encoding="utf-8")
        restore = (ROOT_DIR / "scripts" / "restore_upgrade_backup.sh").read_text(encoding="utf-8")

        self.assertIn("--include-storage", scheduled_backup)
        self.assertIn('SCHEDULED_ROOT="$BACKUP_ROOT/scheduled"', scheduled_backup)
        self.assertIn("-name 'upgrade-*'", scheduled_backup)
        self.assertIn('rm -rf -- "$candidate_real"', scheduled_backup)
        self.assertIn("storage-files.tar.gz", upgrade_backup)
        self.assertIn("storage-files.tar.gz", restore)
        self.assertIn("for directory in original preview thumbnail", restore)

    def test_backup_rehearsal_requires_explicit_mysql_opt_in(self):
        script = (ROOT_DIR / "scripts" / "verify_backup_restore.py").read_text(encoding="utf-8")
        self.assertIn("--allow-mysql", script)
        self.assertIn("TemporaryDirectory", script)
        self.assertIn("Expired scheduled backup was not pruned", script)

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

        ignored = module._ignore_backend("backend", database_files + ["requirements.txt"])

        self.assertTrue(set(database_files).issubset(ignored))
        self.assertNotIn("requirements.txt", ignored)

    def test_release_packager_excludes_local_only_scripts(self):
        module_path = ROOT_DIR / "scripts" / "package_release.py"
        spec = importlib.util.spec_from_file_location("moegallery_package_release_local_files", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        ignored = module._ignore_runtime_cache(
            str(ROOT_DIR / "scripts"),
            ["package_release.py", "upload_loud0715_to_cloud.py"],
        )

        self.assertNotIn("package_release.py", ignored)
        self.assertIn("upload_loud0715_to_cloud.py", ignored)

    def test_install_and_upgrade_require_hashed_dependency_lock(self):
        scripts = (
            ROOT_DIR / "install.sh",
            ROOT_DIR / "scripts" / "upgrade_release.sh",
        )
        for script_path in scripts:
            script = script_path.read_text(encoding="utf-8")
            with self.subTest(script=script_path.name):
                self.assertIn("requirements.lock.txt", script)
                self.assertIn("--require-hashes", script)
                self.assertIn('PIP_BOOTSTRAP_VERSION="26.2"', script)

    def test_panel_upgrade_retries_health_check_before_failing(self):
        script = (ROOT_DIR / "scripts" / "upgrade_release.sh").read_text(encoding="utf-8")

        self.assertIn('HEALTH_CHECK_ATTEMPTS="${HEALTH_CHECK_ATTEMPTS:-20}"', script)
        self.assertIn('for ((attempt = 1; attempt <= HEALTH_CHECK_ATTEMPTS; attempt++))', script)
        self.assertIn('curl --connect-timeout 2 --max-time 5 -fsS "$HEALTH_URL"', script)
        self.assertIn('Health check failed after ${HEALTH_CHECK_ATTEMPTS} attempts', script)

    def test_panel_upgrade_includes_durable_storage_in_backup(self):
        script = (ROOT_DIR / "scripts" / "upgrade_release.sh").read_text(encoding="utf-8")

        self.assertIn(
            'backup_before_upgrade.sh" --app-dir "$APP_DIR" --backup-root "$BACKUP_ROOT" --include-storage',
            script,
        )
        self.assertIn('backup_before_upgrade.sh --app-dir $APP_DIR --backup-root $BACKUP_ROOT --include-storage', script)

    def test_release_packager_requires_dependency_locks(self):
        script = (ROOT_DIR / "scripts" / "package_release.py").read_text(encoding="utf-8")
        self.assertIn('("requirements.lock.txt", "requirements-test.lock.txt")', script)


if __name__ == "__main__":
    unittest.main()
