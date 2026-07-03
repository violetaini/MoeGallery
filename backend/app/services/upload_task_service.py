from datetime import datetime
from threading import Lock, Thread

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.database import SessionLocal
from app.models import Image, UploadTask
from app.services.app_setting_service import get_upload_claim_batch_size, get_upload_worker_count
from app.services.image_service import ImageService
from app.services.storage_service import delete_storage_file, resolve_storage_file

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_SUCCESS = "success"
TASK_STATUS_FAILED = "failed"

_worker_lock = Lock()
_worker_threads: list[Thread] = []
_claim_lock = Lock()


def csv_to_ids(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(part) for part in value.split(",") if part.strip()]


def ids_to_csv(values: list[int] | None) -> str | None:
    if not values:
        return None
    return ",".join(str(value) for value in values)


def task_options():
    return (
        selectinload(UploadTask.image),
        selectinload(UploadTask.image).selectinload(Image.works),
        selectinload(UploadTask.image).selectinload(Image.characters),
        selectinload(UploadTask.image).selectinload(Image.tags),
    )


def create_upload_task(
    db: Session,
    *,
    staged_path: str,
    original_filename: str | None,
    content_type: str | None,
    file_size: int,
    rating: str,
    is_public: bool,
    source_url: str | None,
    artist_name: str | None,
    work_ids: list[int] | None,
    character_ids: list[int] | None,
    merge_duplicate_relations: bool = False,
) -> UploadTask:
    task = UploadTask(
        status=TASK_STATUS_QUEUED,
        original_filename=original_filename,
        content_type=content_type,
        staged_path=staged_path,
        file_size=file_size,
        rating=rating,
        is_public=is_public,
        source_url=source_url,
        artist_name=artist_name,
        work_ids_csv=ids_to_csv(work_ids),
        character_ids_csv=ids_to_csv(character_ids),
        merge_duplicate_relations=merge_duplicate_relations,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def claim_next_task(db: Session) -> UploadTask | None:
    with _claim_lock:
        task_id = db.scalar(
            select(UploadTask.id)
            .where(UploadTask.status == TASK_STATUS_QUEUED)
            .order_by(UploadTask.created_at, UploadTask.id)
            .limit(1)
        )
        if not task_id:
            return None
        now = datetime.utcnow()
        updated = db.execute(
            update(UploadTask)
            .where(UploadTask.id == task_id, UploadTask.status == TASK_STATUS_QUEUED)
            .values(status=TASK_STATUS_PROCESSING, started_at=now, error_message=None)
        ).rowcount
        db.commit()
        if not updated:
            return None
        return db.get(UploadTask, task_id)


def process_task(db: Session, task: UploadTask) -> None:
    try:
        data = resolve_storage_file(task.staged_path).read_bytes()
        image, duplicate = ImageService(db).create_from_bytes(
            data=data,
            original_filename=task.original_filename,
            content_type=task.content_type,
            rating=task.rating,
            is_public=task.is_public,
            source_url=task.source_url,
            artist_name=task.artist_name,
            work_ids=csv_to_ids(task.work_ids_csv),
            character_ids=csv_to_ids(task.character_ids_csv),
            merge_duplicate_relations=task.merge_duplicate_relations,
        )
        task.status = TASK_STATUS_SUCCESS
        task.image_id = image.id
        task.duplicate = duplicate
        task.finished_at = datetime.utcnow()
        task.error_message = None
        db.commit()
        delete_storage_file(task.staged_path)
    except Exception as exc:  # noqa: BLE001 - task failures must be persisted for the UI.
        db.rollback()
        failed = db.get(UploadTask, task.id)
        if failed:
            failed.status = TASK_STATUS_FAILED
            failed.error_message = str(exc)
            failed.finished_at = datetime.utcnow()
            db.commit()


def run_worker_once() -> bool:
    with SessionLocal() as db:
        processed = False
        batch_size = get_upload_claim_batch_size(db)
        for _ in range(batch_size):
            task = claim_next_task(db)
            if not task:
                return processed
            process_task(db, task)
            processed = True
        return processed


def run_worker_loop() -> None:
    while run_worker_once():
        pass


def start_upload_worker() -> None:
    with _worker_lock:
        alive = [thread for thread in _worker_threads if thread.is_alive()]
        _worker_threads[:] = alive
        with SessionLocal() as db:
            target_count = get_upload_worker_count(db)
        if len(_worker_threads) >= target_count:
            return
        for index in range(len(_worker_threads), target_count):
            thread = Thread(target=run_worker_loop, name=f"agms-upload-worker-{index + 1}", daemon=True)
            _worker_threads.append(thread)
            thread.start()
