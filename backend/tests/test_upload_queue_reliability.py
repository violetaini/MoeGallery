import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image as PillowImage
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.auth import require_uploads_manage
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Image, UploadTask
from app.services.image_service import ImageService
from app.services.storage_service import resolve_storage_file, save_upload_task_file
from app.services.upload_task_service import (
    TASK_STATUS_CANCELED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PROCESSING,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RETRY_WAIT,
    TASK_STATUS_SUCCESS,
    cancel_upload_task,
    claim_next_task,
    cleanup_expired_upload_tasks,
    process_task,
    recover_stale_upload_tasks,
    renew_task_lease,
    retry_upload_task,
)
from app.utils.time import utcnow_naive


def png_bytes() -> bytes:
    output = BytesIO()
    PillowImage.new("RGB", (32, 24), (120, 80, 160)).save(output, format="PNG")
    return output.getvalue()


class UploadQueueReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-upload-reliability-")
        self.original_storage_path = settings.storage_path
        settings.storage_path = Path(self.temp_dir.name) / "storage"
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'queue.db'}",
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
        app.dependency_overrides[require_uploads_manage] = lambda: {"method": "test-admin"}
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(require_uploads_manage, None)
        app.dependency_overrides.pop(get_db, None)
        settings.storage_path = self.original_storage_path
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _new_task(self, db, *, status=TASK_STATUS_QUEUED, staged=True, **values) -> UploadTask:
        staged_path = save_upload_task_file(png_bytes(), values.pop("original_filename", "task.png")) if staged else None
        task = UploadTask(
            status=status,
            original_filename="task.png",
            content_type="image/png",
            staged_path=staged_path,
            file_size=len(png_bytes()),
            rating="safe",
            is_public=True,
            max_attempts=3,
            **values,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def test_claim_and_heartbeat_create_and_extend_a_fenced_lease(self):
        base = datetime(2026, 7, 31, 10, 0, 0)
        with self.SessionTesting() as db:
            queued = self._new_task(db)
            claimed = claim_next_task(db, worker_id="worker-a", now=base)

            self.assertEqual(claimed.id, queued.id)
            self.assertEqual(claimed.status, TASK_STATUS_PROCESSING)
            self.assertEqual(claimed.attempt_count, 1)
            self.assertEqual(claimed.worker_id, "worker-a")
            self.assertTrue(claimed.lease_token)
            first_expiry = claimed.lease_expires_at
            self.assertTrue(
                renew_task_lease(
                    claimed.id,
                    claimed.lease_token,
                    db=db,
                    now=base + timedelta(minutes=1),
                )
            )
            db.refresh(claimed)
            self.assertGreater(claimed.lease_expires_at, first_expiry)
            self.assertEqual(claimed.heartbeat_at, base + timedelta(minutes=1))

    def test_recovery_requeues_expired_lease_but_keeps_live_task(self):
        now = datetime(2026, 7, 31, 12, 0, 0)
        with self.SessionTesting() as db:
            expired = self._new_task(
                db,
                status=TASK_STATUS_PROCESSING,
                attempt_count=1,
                lease_token="expired",
                lease_expires_at=now - timedelta(seconds=1),
            )
            live = self._new_task(
                db,
                status=TASK_STATUS_PROCESSING,
                attempt_count=1,
                lease_token="live",
                lease_expires_at=now + timedelta(minutes=5),
            )
            missing = self._new_task(
                db,
                status=TASK_STATUS_PROCESSING,
                staged=False,
                attempt_count=1,
                lease_token="missing",
                lease_expires_at=now - timedelta(seconds=1),
            )

            result = recover_stale_upload_tasks(db, now)
            db.refresh(expired)
            db.refresh(live)
            db.refresh(missing)

            self.assertEqual(result, {"recovered": 1, "failed": 1, "canceled": 0})
            self.assertEqual(expired.status, TASK_STATUS_RETRY_WAIT)
            self.assertEqual(expired.next_attempt_at, now)
            self.assertIsNone(expired.lease_token)
            self.assertEqual(live.status, TASK_STATUS_PROCESSING)
            self.assertEqual(live.lease_token, "live")
            self.assertEqual(missing.status, TASK_STATUS_FAILED)
            self.assertEqual(missing.error_code, "staged_file_missing")

    def test_processing_failure_retries_then_becomes_terminal(self):
        with self.SessionTesting() as db:
            task = self._new_task(
                db,
                status=TASK_STATUS_PROCESSING,
                attempt_count=1,
                lease_token="attempt-one",
                lease_expires_at=utcnow_naive() + timedelta(minutes=5),
            )
            with patch.object(ImageService, "create_from_bytes", side_effect=OSError("disk busy")):
                process_task(db, task)
            db.refresh(task)
            self.assertEqual(task.status, TASK_STATUS_RETRY_WAIT)
            self.assertEqual(task.error_code, "storage_io")
            self.assertIsNotNone(task.next_attempt_at)
            self.assertTrue(task.staged_path)

            task.status = TASK_STATUS_PROCESSING
            task.attempt_count = 3
            task.lease_token = "attempt-three"
            task.lease_expires_at = utcnow_naive() + timedelta(minutes=5)
            db.commit()
            with patch.object(ImageService, "create_from_bytes", side_effect=OSError("disk busy")):
                process_task(db, task)
            db.refresh(task)
            self.assertEqual(task.status, TASK_STATUS_FAILED)
            self.assertIsNotNone(task.finished_at)
            self.assertTrue(task.staged_path)

    def test_expired_worker_cannot_finalize_after_lease_is_reassigned(self):
        with self.SessionTesting() as db:
            image = Image(
                filename="lease-result.webp",
                original_filename="task.png",
                file_path="original/lease-result.webp",
                width=32,
                height=24,
                orientation="landscape",
                file_size=128,
                mime_type="image/webp",
                sha256="f" * 64,
                rating="safe",
                is_public=True,
            )
            db.add(image)
            db.commit()
            task = self._new_task(
                db,
                status=TASK_STATUS_PROCESSING,
                attempt_count=1,
                lease_token="old-lease",
                lease_expires_at=utcnow_naive() + timedelta(minutes=5),
            )
            task_id = task.id

            def reassign_lease(**_kwargs):
                with self.SessionTesting() as other_db:
                    other_db.execute(
                        update(UploadTask)
                        .where(UploadTask.id == task_id)
                        .values(worker_id="worker-new", lease_token="new-lease")
                    )
                    other_db.commit()
                return image, False

            with patch.object(ImageService, "create_from_bytes", side_effect=reassign_lease):
                process_task(db, task)

        with self.SessionTesting() as verify_db:
            current = verify_db.get(UploadTask, task_id)
            self.assertEqual(current.status, TASK_STATUS_PROCESSING)
            self.assertEqual(current.worker_id, "worker-new")
            self.assertEqual(current.lease_token, "new-lease")
            self.assertIsNone(current.image_id)

    def test_cancel_and_manual_retry_manage_staged_files(self):
        with self.SessionTesting() as db:
            queued = self._new_task(db)
            queued_path = resolve_storage_file(queued.staged_path)
            self.assertTrue(cancel_upload_task(db, queued))
            db.refresh(queued)
            self.assertEqual(queued.status, TASK_STATUS_CANCELED)
            self.assertFalse(queued_path.exists())
            self.assertIsNone(queued.staged_path)

            processing = self._new_task(
                db,
                status=TASK_STATUS_PROCESSING,
                attempt_count=1,
                lease_token="processing",
                lease_expires_at=utcnow_naive() + timedelta(minutes=5),
            )
            self.assertTrue(cancel_upload_task(db, processing))
            db.refresh(processing)
            self.assertEqual(processing.status, TASK_STATUS_PROCESSING)
            self.assertTrue(processing.cancel_requested)

            failed = self._new_task(
                db,
                status=TASK_STATUS_FAILED,
                attempt_count=3,
                finished_at=utcnow_naive(),
            )
            self.assertTrue(retry_upload_task(db, failed))
            db.refresh(failed)
            self.assertEqual(failed.status, TASK_STATUS_QUEUED)
            self.assertEqual(failed.attempt_count, 0)
            self.assertIsNone(failed.finished_at)
            failed.status = TASK_STATUS_FAILED
            failed.finished_at = utcnow_naive()
            db.commit()
            self.assertFalse(cancel_upload_task(db, failed))

    def test_cleanup_removes_expired_staging_and_old_history(self):
        now = datetime(2026, 7, 31, 12, 0, 0)
        with self.SessionTesting() as db:
            failed = self._new_task(
                db,
                status=TASK_STATUS_FAILED,
                finished_at=now - timedelta(days=8),
            )
            failed_path = resolve_storage_file(failed.staged_path)
            old_success = self._new_task(
                db,
                status=TASK_STATUS_SUCCESS,
                staged=False,
                finished_at=now - timedelta(days=91),
            )
            recent = self._new_task(
                db,
                status=TASK_STATUS_SUCCESS,
                staged=False,
                finished_at=now - timedelta(days=1),
            )
            failed_id = failed.id
            old_success_id = old_success.id
            recent_id = recent.id

            result = cleanup_expired_upload_tasks(db, now)

            self.assertEqual(result, {"staged_cleaned": 1, "records_deleted": 1})
            self.assertFalse(failed_path.exists())
            self.assertIsNotNone(db.get(UploadTask, failed_id))
            self.assertIsNone(db.get(UploadTask, old_success_id))
            self.assertIsNotNone(db.get(UploadTask, recent_id))

    def test_api_lists_pages_and_runs_batch_actions(self):
        with self.SessionTesting() as db:
            first = self._new_task(db)
            second = self._new_task(db)
            task_ids = [first.id, second.id]

        response = self.client.get("/api/upload-tasks", params={"page": 1, "page_size": 1})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["page_size"], 1)
        self.assertEqual(len(payload["items"]), 1)

        with patch("app.api.upload_tasks.start_upload_worker"):
            action = self.client.post(
                "/api/upload-tasks/batch/actions",
                json={"ids": task_ids, "action": "cancel"},
            )
        self.assertEqual(action.status_code, 200)
        self.assertEqual(action.json(), {"affected": 2, "skipped": 0})

        filtered = self.client.get(
            "/api/upload-tasks",
            params={"status": TASK_STATUS_CANCELED, "page_size": 10},
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["total"], 2)


if __name__ == "__main__":
    unittest.main()
