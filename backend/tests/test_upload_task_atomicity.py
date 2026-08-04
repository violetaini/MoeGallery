import hashlib
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image as PillowImage
from sqlalchemy import create_engine, event, func, select
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
from app.services.upload_task_service import process_task


def png_bytes(color: tuple[int, int, int] = (64, 128, 192)) -> bytes:
    output = BytesIO()
    PillowImage.new("RGB", (48, 32), color).save(output, format="PNG")
    return output.getvalue()


class UploadTaskAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-upload-atomicity-")
        self.original_storage_path = settings.storage_path
        settings.storage_path = Path(self.temp_dir.name) / "storage"
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'upload-tasks.db'}",
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

    def _files(self, *items: tuple[str, bytes]):
        return [("files", (name, data, "image/png")) for name, data in items]

    def _stored_files(self, directory: str) -> list[Path]:
        path = settings.storage_path / directory
        return list(path.iterdir()) if path.exists() else []

    def _counts(self) -> tuple[int, int]:
        with self.SessionTesting() as db:
            return (
                db.scalar(select(func.count()).select_from(UploadTask)) or 0,
                db.scalar(select(func.count()).select_from(Image)) or 0,
            )

    def test_invalid_file_rolls_back_the_entire_batch_and_staging(self):
        with patch("app.api.upload_tasks.start_upload_worker") as worker:
            response = self.client.post(
                "/api/upload-tasks",
                files=self._files(("valid.png", png_bytes()), ("broken.png", b"not-an-image")),
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._counts(), (0, 0))
        self.assertEqual(self._stored_files("tasks"), [])
        worker.assert_not_called()

    def test_invalid_relation_is_rejected_before_staging(self):
        with patch("app.api.upload_tasks.start_upload_worker") as worker:
            response = self.client.post(
                "/api/upload-tasks",
                data={"work_ids": "999999"},
                files=self._files(("valid.png", png_bytes())),
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self._counts(), (0, 0))
        self.assertEqual(self._stored_files("tasks"), [])
        worker.assert_not_called()

    def test_task_insert_failure_removes_all_staged_files(self):
        with (
            patch("app.api.upload_tasks.create_upload_task_batch", side_effect=RuntimeError("database unavailable")),
            patch("app.api.upload_tasks.start_upload_worker") as worker,
        ):
            response = self.client.post(
                "/api/upload-tasks",
                files=self._files(("one.png", png_bytes()), ("two.png", png_bytes((32, 64, 96)))),
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "批量上传任务创建失败，本批文件未提交")
        self.assertEqual(self._counts(), (0, 0))
        self.assertEqual(self._stored_files("tasks"), [])
        worker.assert_not_called()

    def test_duplicate_batch_is_created_atomically_and_marked_during_preflight(self):
        data = png_bytes()
        with patch("app.api.upload_tasks.start_upload_worker") as worker:
            response = self.client.post(
                "/api/upload-tasks",
                files=self._files(("first.png", data), ("second.png", data)),
            )

        self.assertEqual(response.status_code, 202)
        items = response.json()["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["sha256"], items[1]["sha256"])
        self.assertFalse(items[0]["preflight_duplicate"])
        self.assertTrue(items[1]["preflight_duplicate"])
        self.assertEqual(self._counts(), (2, 0))
        self.assertEqual(len(self._stored_files("tasks")), 2)
        worker.assert_called_once_with()

        duplicate_response = self.client.post(
            "/api/upload-tasks/check-duplicates",
            json={"items": [{"filename": "third.png", "sha256": items[0]["sha256"]}]},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        duplicate_item = duplicate_response.json()["items"][0]
        self.assertFalse(duplicate_item["duplicate"])
        self.assertTrue(duplicate_item["duplicate_in_queue"])

    def test_hash_duplicate_check_uses_one_image_query_for_a_normal_batch(self):
        image_statements: list[str] = []
        task_statements: list[str] = []

        def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
            normalized = " ".join(statement.lower().split())
            if " from images " in f" {normalized} ":
                image_statements.append(normalized)
            if " from upload_tasks " in f" {normalized} ":
                task_statements.append(normalized)

        event.listen(self.engine, "before_cursor_execute", capture_statement)
        try:
            payload = {
                "items": [
                    {
                        "filename": f"image-{index}.png",
                        "sha256": hashlib.sha256(str(index).encode("ascii")).hexdigest(),
                    }
                    for index in range(500)
                ]
            }
            response = self.client.post("/api/upload-tasks/check-duplicates", json=payload)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture_statement)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 500)
        self.assertEqual(len(image_statements), 1)
        self.assertEqual(len(task_statements), 1)

    def test_concurrent_same_hash_tasks_create_one_image_and_clean_staging(self):
        data = png_bytes()
        with patch("app.api.upload_tasks.start_upload_worker"):
            response = self.client.post(
                "/api/upload-tasks",
                files=self._files(("first.png", data), ("second.png", data)),
            )
        task_ids = [item["id"] for item in response.json()["items"]]

        def process(task_id: int):
            with self.SessionTesting() as db:
                process_task(db, db.get(UploadTask, task_id))

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(process, task_ids))

        with self.SessionTesting() as db:
            tasks = db.scalars(select(UploadTask).order_by(UploadTask.id)).all()
            image_count = db.scalar(select(func.count()).select_from(Image))

        self.assertEqual(image_count, 1)
        self.assertEqual([task.status for task in tasks], ["success", "success"])
        self.assertEqual(len({task.image_id for task in tasks}), 1)
        self.assertEqual(sorted(task.duplicate for task in tasks), [False, True])
        self.assertEqual(len(self._stored_files("original")), 1)
        self.assertEqual(len(self._stored_files("thumbnail")), 1)
        self.assertEqual(self._stored_files("preview"), [])
        self.assertEqual(self._stored_files("tasks"), [])

    def test_image_creation_failure_removes_generated_derivatives(self):
        with self.SessionTesting() as db:
            with patch.object(ImageService, "_apply_relations", side_effect=RuntimeError("relation failure")):
                with self.assertRaisesRegex(RuntimeError, "relation failure"):
                    ImageService(db).create_from_bytes(
                        data=png_bytes(),
                        original_filename="failure.png",
                        content_type="image/png",
                    )

        self.assertEqual(self._counts(), (0, 0))
        self.assertEqual(self._stored_files("original"), [])
        self.assertEqual(self._stored_files("thumbnail"), [])
        self.assertEqual(self._stored_files("preview"), [])


if __name__ == "__main__":
    unittest.main()
