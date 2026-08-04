import os
import sys
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import create_database_engine
from app.models import UploadTask
from app.services.upload_task_service import TASK_STATUS_PROCESSING, TASK_STATUS_QUEUED, claim_next_task


MYSQL_DATABASE_URL = os.environ.get("AGMS_DATABASE_URL", "")
IS_MYSQL = MYSQL_DATABASE_URL.startswith(("mysql", "mariadb"))


@unittest.skipUnless(IS_MYSQL, "requires AGMS_DATABASE_URL to point at MySQL or MariaDB")
class MysqlIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_database_engine(MYSQL_DATABASE_URL)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False, future=True)
        with cls.engine.connect() as connection:
            cls.server_version = connection.exec_driver_sql("SELECT VERSION()").scalar()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM upload_tasks"))

    def tearDown(self):
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM upload_tasks"))

    def test_migrations_reach_head_and_create_claim_index(self):
        config = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT_DIR / "backend" / "alembic"))
        expected_head = ScriptDirectory.from_config(config).get_current_head()
        with self.engine.connect() as connection:
            current_head = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()

        indexes = {item["name"] for item in inspect(self.engine).get_indexes("upload_tasks")}
        self.assertEqual(current_head, expected_head)
        self.assertIn("ix_upload_tasks_claim_ready", indexes)
        self.assertTrue(self.server_version)

    def test_parallel_mysql_claims_are_unique(self):
        task_count = 12
        worker_count = 8
        with self.Session() as db:
            db.add_all(
                [
                    UploadTask(
                        status=TASK_STATUS_QUEUED,
                        original_filename=f"mysql-{index}.png",
                        content_type="image/png",
                        staged_path=f"tasks/mysql-{index}.png",
                        file_size=1,
                        rating="safe",
                        is_public=True,
                        max_attempts=3,
                    )
                    for index in range(task_count)
                ]
            )
            db.commit()

        barrier = threading.Barrier(worker_count)
        claimed_ids: list[int] = []
        failures: list[Exception] = []
        result_lock = threading.Lock()

        def claim(slot: int) -> None:
            try:
                with self.Session() as db:
                    barrier.wait(timeout=10)
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        task = claim_next_task(db, worker_id=f"mysql-ci-{slot}", now=datetime.utcnow())
                        if task:
                            with result_lock:
                                claimed_ids.append(task.id)
                            return
                        # MySQL SKIP LOCKED can briefly return no row while candidates are locked.
                        # Normal workers retry on their next poll; keep the integration test bounded.
                        time.sleep(0.025)
            except Exception as exc:  # noqa: BLE001 - asserted in the parent thread.
                with result_lock:
                    failures.append(exc)

        threads = [threading.Thread(target=claim, args=(index,)) for index in range(worker_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        self.assertFalse(failures)
        self.assertEqual(len(claimed_ids), worker_count)
        self.assertEqual(len(set(claimed_ids)), worker_count)
        with self.Session() as db:
            processing = db.scalar(select(func.count(UploadTask.id)).where(UploadTask.status == TASK_STATUS_PROCESSING))
        self.assertEqual(processing, worker_count)


if __name__ == "__main__":
    unittest.main()
