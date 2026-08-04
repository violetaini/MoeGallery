import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.api.settings import update_settings
from app.database import Base, create_database_engine
from app.models import AppSetting, UploadTask
from app.schemas.settings import AdminSettingsUpdate
from app.services.app_setting_service import (
    UPLOAD_WORKER_COUNT_KEY,
    get_upload_worker_profile,
    upload_worker_limit_for_dialect,
)
from app.services.upload_task_service import (
    TASK_STATUS_PROCESSING,
    TASK_STATUS_QUEUED,
    _claimable_task_statement,
    claim_next_task,
)


class DatabaseConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-db-concurrency-")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_file_sqlite_engine_enables_wal_busy_timeout_and_foreign_keys(self):
        database_path = Path(self.temp_dir.name) / "concurrency.db"
        with patch.object(settings, "sqlite_busy_timeout_ms", 4321):
            engine = create_database_engine(f"sqlite:///{database_path.as_posix()}")
            try:
                with engine.connect() as connection:
                    self.assertEqual(connection.exec_driver_sql("PRAGMA journal_mode").scalar(), "wal")
                    self.assertEqual(connection.exec_driver_sql("PRAGMA busy_timeout").scalar(), 4321)
                    self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1)
                    self.assertEqual(connection.exec_driver_sql("PRAGMA synchronous").scalar(), 1)
            finally:
                engine.dispose()

    def test_mysql_engine_uses_configured_pool_capacity(self):
        with (
            patch.object(settings, "mysql_pool_size", 11),
            patch.object(settings, "mysql_max_overflow", 7),
            patch.object(settings, "mysql_pool_timeout_seconds", 19),
            patch.object(settings, "mysql_pool_recycle_seconds", 321),
        ):
            engine = create_database_engine("mysql+pymysql://user:password@127.0.0.1:3306/gallery?charset=utf8mb4")
            try:
                self.assertEqual(engine.pool.size(), 11)
                self.assertEqual(engine.pool._max_overflow, 7)
                self.assertEqual(engine.pool._timeout, 19)
                self.assertEqual(engine.pool._recycle, 321)
                self.assertTrue(engine.pool._pre_ping)
            finally:
                engine.dispose()

    def test_sqlite_worker_profile_is_capped_before_workers_start(self):
        engine = create_database_engine(f"sqlite:///{Path(self.temp_dir.name) / 'profile.db'}")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        try:
            with patch.object(settings, "sqlite_upload_worker_limit", 4), Session() as db:
                db.add(AppSetting(key=UPLOAD_WORKER_COUNT_KEY, value="12"))
                db.commit()
                profile = get_upload_worker_profile(db)
                self.assertEqual(profile["profile"], "sqlite_conservative")
                self.assertEqual(profile["requested"], 12)
                self.assertEqual(profile["effective"], 4)
                self.assertEqual(profile["limit"], 4)
        finally:
            engine.dispose()

    def test_sqlite_settings_rejects_worker_count_above_effective_limit(self):
        engine = create_database_engine(f"sqlite:///{Path(self.temp_dir.name) / 'settings.db'}")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        try:
            with patch.object(settings, "sqlite_upload_worker_limit", 4), Session() as db:
                with self.assertRaises(HTTPException) as raised:
                    update_settings(
                        AdminSettingsUpdate(upload_worker_count=5),
                        db,
                        {"auth_type": "session", "api_key_scopes": []},
                    )
                self.assertEqual(raised.exception.status_code, 422)
                self.assertIn("worker", str(raised.exception.detail))
        finally:
            engine.dispose()

    def test_mysql_worker_limit_reserves_connections_for_requests(self):
        with (
            patch.object(settings, "mysql_pool_size", 24),
            patch.object(settings, "mysql_max_overflow", 40),
        ):
            self.assertEqual(upload_worker_limit_for_dialect("mysql"), 60)

    def test_mysql_claim_statement_uses_skip_locked(self):
        statement = _claimable_task_statement(datetime(2026, 8, 3), skip_locked=True)
        compiled = str(statement.compile(dialect=mysql.dialect()))
        self.assertIn("FOR UPDATE SKIP LOCKED", compiled)

    def test_sqlite_concurrent_claims_are_unique(self):
        engine = create_database_engine(f"sqlite:///{Path(self.temp_dir.name) / 'claims.db'}")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        try:
            with Session() as db:
                db.add_all(
                    [
                        UploadTask(
                            status=TASK_STATUS_QUEUED,
                            original_filename=f"{index}.png",
                            content_type="image/png",
                            staged_path=f"tasks/{index}.png",
                            file_size=1,
                            rating="safe",
                            is_public=True,
                            max_attempts=3,
                        )
                        for index in range(16)
                    ]
                )
                db.commit()

            barrier = threading.Barrier(8)
            claimed_ids: list[int] = []
            failures: list[Exception] = []
            result_lock = threading.Lock()

            def claim(slot: int) -> None:
                try:
                    with Session() as db:
                        barrier.wait(timeout=5)
                        task = claim_next_task(db, worker_id=f"worker-{slot}")
                        if task:
                            with result_lock:
                                claimed_ids.append(task.id)
                except Exception as exc:  # noqa: BLE001 - assertion is made in the parent thread.
                    with result_lock:
                        failures.append(exc)

            threads = [threading.Thread(target=claim, args=(index,)) for index in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertFalse(failures)
            self.assertEqual(len(claimed_ids), 8)
            self.assertEqual(len(set(claimed_ids)), 8)
            with Session() as db:
                processing = db.scalar(
                    select(func.count(UploadTask.id)).where(UploadTask.status == TASK_STATUS_PROCESSING)
                )
                self.assertEqual(processing, 8)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
