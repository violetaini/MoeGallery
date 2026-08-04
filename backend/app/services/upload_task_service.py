import json
import logging
import os
import socket
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from threading import Event, Lock, Thread, current_thread
from uuid import uuid4

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import SessionLocal
from app.models import Image, UploadTask
from app.services.app_setting_service import (
    get_upload_claim_batch_size,
    get_upload_failed_retention_days,
    get_upload_task_max_attempts,
    get_upload_worker_count,
)
from app.services.image_service import ImageService
from app.services.storage_service import delete_storage_file, resolve_storage_file
from app.utils.hash import sha256_bytes
from app.utils.image_process import ImageInspection, InvalidImageError

logger = logging.getLogger(__name__)

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_RETRY_WAIT = "retry_wait"
TASK_STATUS_SUCCESS = "success"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_CANCELED = "canceled"
ACTIVE_TASK_STATUSES = (TASK_STATUS_QUEUED, TASK_STATUS_PROCESSING, TASK_STATUS_RETRY_WAIT)
TERMINAL_TASK_STATUSES = (TASK_STATUS_SUCCESS, TASK_STATUS_FAILED, TASK_STATUS_CANCELED)

WORKER_POLL_SECONDS = 1.0
MAINTENANCE_INTERVAL_SECONDS = 60
_worker_instance_id = f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
_worker_lock = Lock()
_worker_threads: dict[tuple[int, int], Thread] = {}
_worker_target_count = 0
_worker_generation = 0
_worker_wakeup = Event()
_worker_shutdown = Event()
_claim_lock = Lock()
_maintenance_lock = Lock()
_last_maintenance_at: datetime | None = None
_hash_locks_guard = Lock()
_hash_locks: dict[str, tuple[Lock, int]] = {}


@dataclass(frozen=True)
class UploadTaskDraft:
    staged_path: str
    original_filename: str | None
    content_type: str | None
    file_size: int
    sha256: str
    inspection: ImageInspection
    preflight_duplicate: bool
    rating: str
    is_public: bool
    source_url: str | None
    artist_name: str | None
    work_ids: list[int] | None
    character_ids: list[int] | None
    merge_duplicate_relations: bool = False


def utcnow() -> datetime:
    return datetime.utcnow()


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


def inspection_to_json(inspection: ImageInspection) -> str:
    return json.dumps(asdict(inspection), ensure_ascii=True, separators=(",", ":"))


def inspection_from_json(value: str | None) -> ImageInspection | None:
    if not value:
        return None
    try:
        payload = json.loads(value)
        return ImageInspection(**payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def create_upload_task_batch(db: Session, drafts: list[UploadTaskDraft]) -> list[UploadTask]:
    max_attempts = get_upload_task_max_attempts(db)
    tasks = [
        UploadTask(
            status=TASK_STATUS_QUEUED,
            original_filename=draft.original_filename,
            content_type=draft.content_type,
            staged_path=draft.staged_path,
            file_size=draft.file_size,
            sha256=draft.sha256,
            inspection_json=inspection_to_json(draft.inspection),
            preflight_duplicate=draft.preflight_duplicate,
            rating=draft.rating,
            is_public=draft.is_public,
            source_url=draft.source_url,
            artist_name=draft.artist_name,
            work_ids_csv=ids_to_csv(draft.work_ids),
            character_ids_csv=ids_to_csv(draft.character_ids),
            merge_duplicate_relations=draft.merge_duplicate_relations,
            max_attempts=max_attempts,
        )
        for draft in drafts
    ]
    try:
        db.add_all(tasks)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return tasks


@contextmanager
def image_hash_lock(digest: str):
    with _hash_locks_guard:
        entry = _hash_locks.get(digest)
        if entry:
            lock, users = entry
        else:
            lock, users = Lock(), 0
        _hash_locks[digest] = (lock, users + 1)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _hash_locks_guard:
            current_lock, users = _hash_locks[digest]
            if users <= 1:
                _hash_locks.pop(digest, None)
            else:
                _hash_locks[digest] = (current_lock, users - 1)


def _eligible_task_condition(now: datetime):
    return or_(
        UploadTask.status == TASK_STATUS_QUEUED,
        and_(
            UploadTask.status == TASK_STATUS_RETRY_WAIT,
            or_(UploadTask.next_attempt_at.is_(None), UploadTask.next_attempt_at <= now),
        ),
    )


def _claimable_task_statement(now: datetime, *, skip_locked: bool = False):
    statement = (
        select(UploadTask)
        .where(
            _eligible_task_condition(now),
            UploadTask.cancel_requested.is_(False),
            UploadTask.attempt_count < UploadTask.max_attempts,
            UploadTask.staged_path.is_not(None),
        )
        .order_by(UploadTask.next_attempt_at, UploadTask.created_at, UploadTask.id)
        .limit(1)
    )
    return statement.with_for_update(skip_locked=True) if skip_locked else statement


def _supports_mysql_skip_locked(db: Session) -> bool:
    dialect = db.get_bind().dialect
    if dialect.name != "mysql" or bool(getattr(dialect, "is_mariadb", False)):
        return False
    version = getattr(dialect, "server_version_info", None)
    return not version or tuple(version) >= (8, 0, 1)


def _mark_task_claimed(
    task: UploadTask,
    *,
    owner: str,
    lease_token: str,
    claimed_at: datetime,
    lease_expires_at: datetime,
) -> None:
    task.status = TASK_STATUS_PROCESSING
    task.attempt_count += 1
    task.next_attempt_at = None
    task.worker_id = owner
    task.lease_token = lease_token
    task.lease_expires_at = lease_expires_at
    task.heartbeat_at = claimed_at
    task.started_at = claimed_at
    task.finished_at = None
    task.error_code = None
    task.error_message = None


def _claim_next_task_with_skip_locked(
    db: Session,
    *,
    owner: str,
    lease_token: str,
    claimed_at: datetime,
    lease_expires_at: datetime,
) -> UploadTask | None:
    task = db.scalar(_claimable_task_statement(claimed_at, skip_locked=True))
    if not task:
        return None
    _mark_task_claimed(
        task,
        owner=owner,
        lease_token=lease_token,
        claimed_at=claimed_at,
        lease_expires_at=lease_expires_at,
    )
    db.commit()
    db.refresh(task)
    return task


def _claim_next_task_with_compare_update(
    db: Session,
    *,
    owner: str,
    lease_token: str,
    claimed_at: datetime,
    lease_expires_at: datetime,
) -> UploadTask | None:
    task_id = db.scalar(_claimable_task_statement(claimed_at).with_only_columns(UploadTask.id))
    if not task_id:
        return None
    updated = db.execute(
        update(UploadTask)
        .where(
            UploadTask.id == task_id,
            _eligible_task_condition(claimed_at),
            UploadTask.cancel_requested.is_(False),
            UploadTask.attempt_count < UploadTask.max_attempts,
        )
        .values(
            status=TASK_STATUS_PROCESSING,
            attempt_count=UploadTask.attempt_count + 1,
            next_attempt_at=None,
            worker_id=owner,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            heartbeat_at=claimed_at,
            started_at=claimed_at,
            finished_at=None,
            error_code=None,
            error_message=None,
        )
    ).rowcount
    db.commit()
    if not updated:
        return None
    return db.get(UploadTask, task_id)


def _is_transient_claim_error(exc: OperationalError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return any(
        marker in message
        for marker in (
            "database is locked",
            "database is busy",
            "lock wait timeout",
            "deadlock found",
            "try restarting transaction",
        )
    )


def claim_next_task(db: Session, worker_id: str | None = None, now: datetime | None = None) -> UploadTask | None:
    claimed_at = now or utcnow()
    owner = worker_id or _worker_instance_id
    lease_token = uuid4().hex
    lease_expires_at = claimed_at + timedelta(seconds=max(60, settings.upload_task_lease_seconds))
    try:
        if _supports_mysql_skip_locked(db):
            return _claim_next_task_with_skip_locked(
                db,
                owner=owner,
                lease_token=lease_token,
                claimed_at=claimed_at,
                lease_expires_at=lease_expires_at,
            )
        with _claim_lock:
            return _claim_next_task_with_compare_update(
                db,
                owner=owner,
                lease_token=lease_token,
                claimed_at=claimed_at,
                lease_expires_at=lease_expires_at,
            )
    except OperationalError as exc:
        db.rollback()
        if _is_transient_claim_error(exc):
            logger.warning("Upload task claim will retry after transient database contention")
            return None
        raise
    except SQLAlchemyError:
        db.rollback()
        raise


def renew_task_lease(
    task_id: int,
    lease_token: str,
    *,
    db: Session | None = None,
    now: datetime | None = None,
) -> bool:
    heartbeat_at = now or utcnow()
    lease_expires_at = heartbeat_at + timedelta(seconds=max(60, settings.upload_task_lease_seconds))
    owns_session = db is None
    session = db or SessionLocal()
    try:
        updated = session.execute(
            update(UploadTask)
            .where(
                UploadTask.id == task_id,
                UploadTask.status == TASK_STATUS_PROCESSING,
                UploadTask.lease_token == lease_token,
            )
            .values(heartbeat_at=heartbeat_at, lease_expires_at=lease_expires_at)
        ).rowcount
        session.commit()
        return bool(updated)
    except Exception:
        session.rollback()
        return False
    finally:
        if owns_session:
            session.close()


class TaskLeaseHeartbeat:
    def __init__(self, task_id: int, lease_token: str | None):
        self.task_id = task_id
        self.lease_token = lease_token
        self.stop_event = Event()
        self.thread: Thread | None = None

    def __enter__(self):
        if not self.lease_token:
            return self
        self.thread = Thread(
            target=self._run,
            name=f"agms-upload-heartbeat-{self.task_id}",
            daemon=True,
        )
        self.thread.start()
        return self

    def _run(self) -> None:
        interval = max(5, settings.upload_task_heartbeat_seconds)
        while not self.stop_event.wait(interval):
            if not renew_task_lease(self.task_id, self.lease_token or ""):
                return

    def __exit__(self, _exc_type, _exc, _traceback):
        self.stop_event.set()
        if self.thread and self.thread is not current_thread():
            self.thread.join(timeout=1)


def _clear_lease(task: UploadTask) -> None:
    task.worker_id = None
    task.lease_token = None
    task.lease_expires_at = None
    task.heartbeat_at = None


def _delete_staged_file(task: UploadTask, deleted_at: datetime | None = None) -> bool:
    if not task.staged_path:
        if not task.staged_file_deleted_at:
            task.staged_file_deleted_at = deleted_at or utcnow()
        return True
    try:
        delete_storage_file(task.staged_path)
    except (OSError, ValueError):
        return False
    task.staged_path = None
    task.staged_file_deleted_at = deleted_at or utcnow()
    return True


def _staged_file_exists(task: UploadTask) -> bool:
    if not task.staged_path:
        return False
    try:
        return resolve_storage_file(task.staged_path).is_file()
    except ValueError:
        return False


def _task_error(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, FileNotFoundError):
        return "staged_file_missing", "上传暂存文件不存在", False
    if isinstance(exc, InvalidImageError):
        return "invalid_image", str(exc)[:1000], False
    if isinstance(exc, OSError):
        return "storage_io", str(exc)[:1000] or "图片存储读写失败", True
    if isinstance(exc, SQLAlchemyError):
        return "database_error", "数据库暂时无法完成上传任务", True
    return "processing_error", str(exc)[:1000] or type(exc).__name__, True


def retry_delay_seconds(attempt_count: int) -> int:
    base = max(1, settings.upload_task_retry_base_seconds)
    multipliers = (1, 3, 12)
    index = max(0, min(len(multipliers) - 1, attempt_count - 1))
    return min(300, base * multipliers[index])


def _finish_canceled(db: Session, task: UploadTask, now: datetime) -> None:
    task.status = TASK_STATUS_CANCELED
    task.cancel_requested = True
    task.next_attempt_at = None
    task.finished_at = now
    task.error_code = "canceled"
    task.error_message = "任务已取消"
    _clear_lease(task)
    _delete_staged_file(task, now)
    db.commit()


def _handle_task_failure(
    db: Session,
    task_id: int,
    lease_token: str | None,
    exc: Exception,
) -> None:
    db.rollback()
    task = db.get(UploadTask, task_id)
    if not task:
        return
    if lease_token and task.lease_token != lease_token:
        return
    now = utcnow()
    if task.cancel_requested:
        _finish_canceled(db, task, now)
        return
    error_code, error_message, retryable = _task_error(exc)
    task.error_code = error_code
    task.error_message = error_message
    _clear_lease(task)
    if retryable and task.attempt_count < task.max_attempts and task.staged_path:
        task.status = TASK_STATUS_RETRY_WAIT
        task.next_attempt_at = now + timedelta(seconds=retry_delay_seconds(task.attempt_count))
        task.finished_at = None
        _worker_wakeup.set()
    else:
        task.status = TASK_STATUS_FAILED
        task.next_attempt_at = None
        task.finished_at = now
    db.commit()


def process_task(db: Session, task: UploadTask) -> None:
    task_id = task.id
    lease_token = task.lease_token
    staged_path = task.staged_path
    try:
        db.refresh(task)
        if task.cancel_requested:
            _finish_canceled(db, task, utcnow())
            return
        if not task.staged_path:
            raise FileNotFoundError("Upload staging path is unavailable")
        data = resolve_storage_file(task.staged_path).read_bytes()
        digest = task.sha256 or sha256_bytes(data)
        with TaskLeaseHeartbeat(task_id, lease_token), image_hash_lock(digest):
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
                precomputed_sha256=digest,
                precomputed_inspection=inspection_from_json(task.inspection_json),
            )

        finished_at = utcnow()
        ownership_filters = [UploadTask.id == task_id]
        if lease_token:
            ownership_filters.extend(
                (
                    UploadTask.status == TASK_STATUS_PROCESSING,
                    UploadTask.lease_token == lease_token,
                )
            )
        else:
            ownership_filters.append(
                UploadTask.status.in_((TASK_STATUS_QUEUED, TASK_STATUS_PROCESSING))
            )
        updated = db.execute(
            update(UploadTask)
            .where(*ownership_filters)
            .values(
                status=TASK_STATUS_SUCCESS,
                sha256=digest,
                image_id=image.id,
                duplicate=duplicate,
                finished_at=finished_at,
                next_attempt_at=None,
                cancel_requested=False,
                error_code=None,
                error_message=None,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
            )
        ).rowcount
        db.commit()
        if not updated:
            return
        try:
            if staged_path:
                delete_storage_file(staged_path)
        except (OSError, ValueError):
            return
        db.execute(
            update(UploadTask)
            .where(
                UploadTask.id == task_id,
                UploadTask.status == TASK_STATUS_SUCCESS,
                UploadTask.image_id == image.id,
                UploadTask.staged_path == staged_path,
            )
            .values(staged_path=None, staged_file_deleted_at=utcnow())
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - task failures must become durable queue state.
        _handle_task_failure(db, task_id, lease_token, exc)


def retry_upload_task(db: Session, task: UploadTask) -> bool:
    if task.status not in {TASK_STATUS_FAILED, TASK_STATUS_RETRY_WAIT}:
        return False
    if not task.staged_path:
        return False
    try:
        staged_file = resolve_storage_file(task.staged_path)
    except ValueError:
        staged_file = None
    if not staged_file or not staged_file.is_file():
        task.status = TASK_STATUS_FAILED
        task.error_code = "staged_file_missing"
        task.error_message = "上传暂存文件不存在，无法重试"
        task.finished_at = utcnow()
        task.staged_path = None
        task.staged_file_deleted_at = utcnow()
        db.commit()
        return False
    if task.status == TASK_STATUS_FAILED:
        task.attempt_count = 0
        task.max_attempts = get_upload_task_max_attempts(db)
    task.status = TASK_STATUS_QUEUED
    task.next_attempt_at = None
    task.finished_at = None
    task.cancel_requested = False
    task.error_code = None
    task.error_message = None
    _clear_lease(task)
    db.commit()
    _worker_wakeup.set()
    return True


def cancel_upload_task(db: Session, task: UploadTask) -> bool:
    if task.status not in ACTIVE_TASK_STATUSES:
        return False
    if task.status == TASK_STATUS_PROCESSING:
        task.cancel_requested = True
        db.commit()
        return True
    _finish_canceled(db, task, utcnow())
    return True


def delete_upload_task(db: Session, task: UploadTask) -> bool:
    if task.status not in TERMINAL_TASK_STATUSES:
        return False
    _delete_staged_file(task)
    db.delete(task)
    db.commit()
    return True


def recover_stale_upload_tasks(db: Session, now: datetime | None = None) -> dict[str, int]:
    recovered_at = now or utcnow()
    tasks = db.scalars(
        select(UploadTask).where(
            UploadTask.status == TASK_STATUS_PROCESSING,
            or_(UploadTask.lease_expires_at.is_(None), UploadTask.lease_expires_at <= recovered_at),
        )
    ).all()
    recovered = 0
    failed = 0
    canceled = 0
    for task in tasks:
        if task.cancel_requested:
            task.status = TASK_STATUS_CANCELED
            task.error_code = "canceled"
            task.error_message = "任务已取消"
            task.finished_at = recovered_at
            _delete_staged_file(task, recovered_at)
            canceled += 1
        elif not _staged_file_exists(task):
            task.status = TASK_STATUS_FAILED
            task.error_code = "staged_file_missing"
            task.error_message = "服务恢复时未找到上传暂存文件"
            task.finished_at = recovered_at
            task.staged_path = None
            task.staged_file_deleted_at = recovered_at
            failed += 1
        elif task.attempt_count >= task.max_attempts:
            task.status = TASK_STATUS_FAILED
            task.error_code = "worker_interrupted"
            task.error_message = "任务处理期间服务中断，且已达到最大尝试次数"
            task.finished_at = recovered_at
            failed += 1
        else:
            task.status = TASK_STATUS_RETRY_WAIT
            task.next_attempt_at = recovered_at
            task.error_code = "worker_interrupted"
            task.error_message = "任务处理期间服务中断，已自动重新排队"
            task.finished_at = None
            recovered += 1
        _clear_lease(task)

    canceled_queued = db.scalars(
        select(UploadTask).where(
            UploadTask.status.in_((TASK_STATUS_QUEUED, TASK_STATUS_RETRY_WAIT)),
            UploadTask.cancel_requested.is_(True),
        )
    ).all()
    for task in canceled_queued:
        task.status = TASK_STATUS_CANCELED
        task.error_code = "canceled"
        task.error_message = "任务已取消"
        task.finished_at = recovered_at
        task.next_attempt_at = None
        _clear_lease(task)
        _delete_staged_file(task, recovered_at)
        canceled += 1
    db.commit()
    return {"recovered": recovered, "failed": failed, "canceled": canceled}


def cleanup_expired_upload_tasks(db: Session, now: datetime | None = None) -> dict[str, int]:
    cleanup_at = now or utcnow()
    failed_cutoff = cleanup_at - timedelta(days=get_upload_failed_retention_days(db))
    history_cutoff = cleanup_at - timedelta(days=max(1, settings.upload_task_history_retention_days))
    staged_cleaned = 0
    records_deleted = 0

    staged_tasks = db.scalars(
        select(UploadTask).where(
            UploadTask.staged_path.is_not(None),
            or_(
                and_(UploadTask.status == TASK_STATUS_FAILED, UploadTask.finished_at <= failed_cutoff),
                UploadTask.status.in_((TASK_STATUS_SUCCESS, TASK_STATUS_CANCELED)),
            ),
        )
    ).all()
    for task in staged_tasks:
        if _delete_staged_file(task, cleanup_at):
            staged_cleaned += 1

    removable_ids = db.scalars(
        select(UploadTask.id).where(
            UploadTask.status.in_(TERMINAL_TASK_STATUSES),
            UploadTask.finished_at <= history_cutoff,
            UploadTask.staged_path.is_(None),
        )
    ).all()
    if removable_ids:
        records_deleted = db.execute(delete(UploadTask).where(UploadTask.id.in_(removable_ids))).rowcount or 0
    db.commit()
    return {"staged_cleaned": staged_cleaned, "records_deleted": records_deleted}


def upload_queue_stats(db: Session) -> dict[str, int | str]:
    counts = dict(
        db.execute(
            select(UploadTask.status, func.count(UploadTask.id)).group_by(UploadTask.status)
        ).all()
    )
    with _worker_lock:
        alive = sum(1 for thread in _worker_threads.values() if thread.is_alive())
        target = _worker_target_count
    return {
        "queued": int(counts.get(TASK_STATUS_QUEUED, 0)),
        "processing": int(counts.get(TASK_STATUS_PROCESSING, 0)),
        "retry_wait": int(counts.get(TASK_STATUS_RETRY_WAIT, 0)),
        "failed": int(counts.get(TASK_STATUS_FAILED, 0)),
        "worker_alive": alive,
        "worker_target": target,
        "worker_instance": _worker_instance_id,
    }


def run_worker_once(worker_id: str | None = None) -> bool:
    with SessionLocal() as db:
        processed = False
        batch_size = get_upload_claim_batch_size(db)
        for _ in range(batch_size):
            task = claim_next_task(db, worker_id=worker_id)
            if not task:
                return processed
            process_task(db, task)
            processed = True
        return processed


def _run_maintenance_if_due() -> None:
    global _last_maintenance_at
    now = utcnow()
    with _maintenance_lock:
        if _last_maintenance_at and (now - _last_maintenance_at).total_seconds() < MAINTENANCE_INTERVAL_SECONDS:
            return
        _last_maintenance_at = now
    try:
        with SessionLocal() as db:
            recover_stale_upload_tasks(db, now)
            cleanup_expired_upload_tasks(db, now)
    except Exception as exc:  # noqa: BLE001 - maintenance will retry on the next interval.
        logger.error("Upload queue maintenance failed (%s)", type(exc).__name__)


def _worker_should_run(slot: int, generation: int) -> bool:
    with _worker_lock:
        return (
            not _worker_shutdown.is_set()
            and generation == _worker_generation
            and slot < _worker_target_count
        )


def run_worker_loop(slot: int, generation: int) -> None:
    worker_id = f"{_worker_instance_id}-{slot + 1}"
    while _worker_should_run(slot, generation):
        if slot == 0:
            _run_maintenance_if_due()
        try:
            processed = run_worker_once(worker_id=worker_id)
        except Exception as exc:  # noqa: BLE001 - keep worker capacity available after a transient DB failure.
            logger.error("Upload worker iteration failed (%s)", type(exc).__name__)
            processed = False
        if processed:
            continue
        _worker_wakeup.wait(WORKER_POLL_SECONDS)
        _worker_wakeup.clear()


def start_upload_worker() -> None:
    global _worker_generation, _worker_target_count
    with SessionLocal() as db:
        target_count = get_upload_worker_count(db)
    with _worker_lock:
        if _worker_shutdown.is_set():
            _worker_generation += 1
        _worker_shutdown.clear()
        _worker_target_count = target_count
        for key, thread in list(_worker_threads.items()):
            if not thread.is_alive():
                _worker_threads.pop(key, None)
        for slot in range(target_count):
            key = (_worker_generation, slot)
            if key in _worker_threads:
                continue
            thread = Thread(
                target=run_worker_loop,
                args=(slot, _worker_generation),
                name=f"agms-upload-worker-{slot + 1}",
                daemon=True,
            )
            _worker_threads[key] = thread
            thread.start()
    _worker_wakeup.set()


def initialize_upload_queue() -> dict[str, int]:
    global _last_maintenance_at
    now = utcnow()
    with SessionLocal() as db:
        recovery = recover_stale_upload_tasks(db, now)
        cleanup_expired_upload_tasks(db, now)
    _last_maintenance_at = now
    start_upload_worker()
    return recovery


def stop_upload_workers(join_timeout: float = 5.0) -> None:
    global _worker_generation, _worker_target_count
    with _worker_lock:
        _worker_target_count = 0
        _worker_generation += 1
        _worker_shutdown.set()
        threads = list(_worker_threads.values())
    _worker_wakeup.set()
    for thread in threads:
        if thread is not current_thread():
            thread.join(timeout=join_timeout)
    with _worker_lock:
        for key, thread in list(_worker_threads.items()):
            if not thread.is_alive():
                _worker_threads.pop(key, None)
