import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.helpers import parse_id_csv, validate_relation_ids
from app.auth import require_uploads_manage
from app.config import settings
from app.database import get_db
from app.models import Character, Image, UploadTask, Work
from app.schemas.upload_task import (
    UploadDuplicateCheckRequest,
    UploadDuplicateCheckRequestItem,
    UploadDuplicateCheckResponse,
    UploadTaskBatchActionRequest,
    UploadTaskBatchActionResponse,
    UploadTaskCreateResponse,
    UploadTaskListResponse,
    UploadTaskRead,
)
from app.services.storage_service import delete_storage_file, save_upload_task_file
from app.services.upload_task_service import (
    TASK_STATUS_CANCELED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PROCESSING,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RETRY_WAIT,
    TASK_STATUS_SUCCESS,
    UploadTaskDraft,
    cancel_upload_task,
    create_upload_task_batch,
    delete_upload_task,
    retry_upload_task,
    start_upload_worker,
    task_options,
)
from app.utils.hash import sha256_bytes
from app.utils.image_process import InvalidImageError, inspect_image, validate_upload_filename
from app.utils.urls import normalize_http_url

router = APIRouter(prefix="/upload-tasks", tags=["upload-tasks"])
logger = logging.getLogger(__name__)
DUPLICATE_QUERY_CHUNK_SIZE = 500


def _chunks(values: list[str], size: int = DUPLICATE_QUERY_CHUNK_SIZE):
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _existing_sha256s(db: Session, digests: list[str]) -> set[str]:
    unique = list(dict.fromkeys(digests))
    existing: set[str] = set()
    for chunk in _chunks(unique):
        existing.update(db.scalars(select(Image.sha256).where(Image.sha256.in_(chunk))).all())
    return existing


def _queued_sha256s(db: Session, digests: list[str]) -> set[str]:
    unique = list(dict.fromkeys(digests))
    queued: set[str] = set()
    for chunk in _chunks(unique):
        queued.update(
            db.scalars(
                select(UploadTask.sha256).where(
                    UploadTask.sha256.in_(chunk),
                    UploadTask.status.in_((TASK_STATUS_QUEUED, TASK_STATUS_PROCESSING, TASK_STATUS_RETRY_WAIT)),
                )
            ).all()
        )
    return queued


def _existing_images_by_sha256(db: Session, digests: list[str]) -> dict[str, Image]:
    unique = list(dict.fromkeys(digests))
    existing: dict[str, Image] = {}
    for chunk in _chunks(unique):
        images = db.scalars(
            select(Image)
            .options(
                selectinload(Image.works),
                selectinload(Image.characters),
                selectinload(Image.tags),
            )
            .where(Image.sha256.in_(chunk))
        ).unique().all()
        existing.update({image.sha256: image for image in images})
    return existing


def _duplicate_check_items(
    items,
    existing_by_sha256: dict[str, Image],
    queued_sha256s: set[str],
) -> list[dict]:
    seen: set[str] = set()
    result = []
    for item in items:
        digest = item.sha256.lower()
        result.append(
            {
                "filename": item.filename,
                "sha256": digest,
                "duplicate": digest in existing_by_sha256,
                "duplicate_in_queue": digest in queued_sha256s,
                "duplicate_in_batch": digest in seen,
                "existing_image": existing_by_sha256.get(digest),
            }
        )
        seen.add(digest)
    return result


def _cleanup_staged_files(paths: list[str]) -> None:
    for path in paths:
        try:
            delete_storage_file(path)
        except OSError:
            logger.warning("Failed to remove staged upload file")


@router.post("", response_model=UploadTaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_upload_tasks(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
    files: Annotated[list[UploadFile], File()],
    work_ids: str | None = Form(None),
    character_ids: str | None = Form(None),
    rating: str = Form("safe"),
    is_public: bool = Form(True),
    source_url: str | None = Form(None),
    artist_name: str | None = Form(None),
    merge_duplicate_relations: bool = Form(False),
):
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")
    if rating not in {"safe", "sensitive", "hidden"}:
        raise HTTPException(status_code=422, detail="rating must be safe, sensitive, or hidden")
    try:
        source_url = normalize_http_url(source_url)
        parsed_work_ids = parse_id_csv(work_ids)
        parsed_character_ids = parse_id_csv(character_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        validate_relation_ids(db, parsed_work_ids, parsed_character_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    staged_paths: list[str] = []
    prepared: list[dict] = []
    current_filename = "upload"
    try:
        for upload in files:
            current_filename = upload.filename or "upload"
            validate_upload_filename(upload.filename)
            data = await upload.read()
            if not data:
                raise InvalidImageError("Empty upload")
            if len(data) > settings.max_upload_size:
                raise InvalidImageError("File is larger than configured upload limit")
            inspection = inspect_image(data)
            digest = sha256_bytes(data)
            staged_path = save_upload_task_file(data, upload.filename)
            staged_paths.append(staged_path)
            prepared.append(
                {
                    "staged_path": staged_path,
                    "original_filename": upload.filename,
                    "content_type": upload.content_type,
                    "file_size": len(data),
                    "sha256": digest,
                    "inspection": inspection,
                }
            )
    except (InvalidImageError, ValueError) as exc:
        _cleanup_staged_files(staged_paths)
        raise HTTPException(status_code=400, detail=f"{current_filename}: {exc}") from exc
    except OSError as exc:
        _cleanup_staged_files(staged_paths)
        logger.error("Upload staging failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="上传文件暂存失败") from exc

    try:
        digests = [item["sha256"] for item in prepared]
        existing_hashes = _existing_sha256s(db, digests)
        queued_hashes = _queued_sha256s(db, digests)
        seen: set[str] = set()
        drafts = []
        for item in prepared:
            digest = item["sha256"]
            drafts.append(
                UploadTaskDraft(
                    **item,
                    preflight_duplicate=digest in existing_hashes or digest in queued_hashes or digest in seen,
                    rating=rating,
                    is_public=is_public,
                    source_url=source_url,
                    artist_name=artist_name,
                    work_ids=parsed_work_ids,
                    character_ids=parsed_character_ids,
                    merge_duplicate_relations=merge_duplicate_relations,
                )
            )
            seen.add(digest)
        tasks = create_upload_task_batch(db, drafts)
    except Exception as exc:
        db.rollback()
        _cleanup_staged_files(staged_paths)
        logger.error("Upload task batch creation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="批量上传任务创建失败，本批文件未提交") from exc

    try:
        start_upload_worker()
    except Exception as exc:  # The committed queue remains visible and can be resumed later.
        logger.error("Upload worker start failed after batch commit (%s)", type(exc).__name__)
    ids = [task.id for task in tasks]
    refreshed = db.scalars(
        select(UploadTask)
        .options(*task_options())
        .where(UploadTask.id.in_(ids))
        .order_by(UploadTask.id)
    ).unique().all()
    return {"items": refreshed}


@router.post("/check-duplicates", response_model=UploadDuplicateCheckResponse)
def check_upload_duplicates(
    payload: UploadDuplicateCheckRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
):
    digests = [item.sha256.lower() for item in payload.items]
    existing = _existing_images_by_sha256(db, digests)
    queued = _queued_sha256s(db, digests)
    return {"items": _duplicate_check_items(payload.items, existing, queued)}


@router.post("/check-duplicates-files", response_model=UploadDuplicateCheckResponse)
async def check_upload_duplicate_files(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
    files: Annotated[list[UploadFile], File()],
):
    items = []
    for upload in files:
        try:
            validate_upload_filename(upload.filename)
            data = await upload.read()
            if not data:
                raise InvalidImageError("Empty upload")
            if len(data) > settings.max_upload_size:
                raise InvalidImageError("File is larger than configured upload limit")
        except InvalidImageError as exc:
            raise HTTPException(status_code=400, detail=f"{upload.filename}: {exc}") from exc

        digest = sha256_bytes(data)
        items.append(
            UploadDuplicateCheckRequestItem(
                filename=upload.filename,
                sha256=digest,
            )
        )
    digests = [item.sha256 for item in items]
    existing = _existing_images_by_sha256(db, digests)
    queued = _queued_sha256s(db, digests)
    return {"items": _duplicate_check_items(items, existing, queued)}


@router.get("", response_model=UploadTaskListResponse)
def list_upload_tasks(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
    ids: str | None = Query(None),
    task_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    valid_statuses = {
        TASK_STATUS_QUEUED,
        TASK_STATUS_PROCESSING,
        TASK_STATUS_RETRY_WAIT,
        TASK_STATUS_SUCCESS,
        TASK_STATUS_FAILED,
        TASK_STATUS_CANCELED,
    }
    if task_status and task_status not in valid_statuses:
        raise HTTPException(status_code=422, detail="Unknown upload task status")
    filters = []
    if task_status:
        filters.append(UploadTask.status == task_status)
    if ids:
        try:
            parsed_ids = parse_id_csv(ids)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="ids must be comma separated integers") from exc
        filters.append(UploadTask.id.in_(parsed_ids))
    count_stmt = select(func.count(UploadTask.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = db.scalar(count_stmt) or 0
    stmt = select(UploadTask).options(*task_options())
    if filters:
        stmt = stmt.where(*filters)
    if ids:
        stmt = stmt.order_by(UploadTask.id)
    else:
        stmt = stmt.order_by(desc(UploadTask.created_at), desc(UploadTask.id)).offset((page - 1) * page_size).limit(page_size)
    items = db.scalars(stmt).unique().all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _get_task_or_404(db: Session, task_id: int) -> UploadTask:
    task = db.scalar(select(UploadTask).options(*task_options()).where(UploadTask.id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="Upload task not found")
    return task


@router.post("/{task_id}/retry", response_model=UploadTaskRead)
def retry_task(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
):
    task = _get_task_or_404(db, task_id)
    if not retry_upload_task(db, task):
        raise HTTPException(status_code=409, detail="当前任务状态或暂存文件不允许重试")
    start_upload_worker()
    return _get_task_or_404(db, task_id)


@router.post("/{task_id}/cancel", response_model=UploadTaskRead)
def cancel_task(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
):
    task = _get_task_or_404(db, task_id)
    if not cancel_upload_task(db, task):
        raise HTTPException(status_code=409, detail="当前任务已经结束，无法取消")
    return _get_task_or_404(db, task_id)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_task(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
):
    task = _get_task_or_404(db, task_id)
    if not delete_upload_task(db, task):
        raise HTTPException(status_code=409, detail="只能删除已完成、失败或已取消的任务记录")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batch/actions", response_model=UploadTaskBatchActionResponse)
def batch_task_action(
    payload: UploadTaskBatchActionRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
):
    affected = 0
    skipped = 0
    for task_id in dict.fromkeys(payload.ids):
        task = db.get(UploadTask, task_id)
        if not task:
            skipped += 1
            continue
        if payload.action == "retry":
            changed = retry_upload_task(db, task)
        elif payload.action == "cancel":
            changed = cancel_upload_task(db, task)
        else:
            changed = delete_upload_task(db, task)
        if changed:
            affected += 1
        else:
            skipped += 1
    if payload.action == "retry" and affected:
        start_upload_worker()
    return {"affected": affected, "skipped": skipped}


@router.get("/{task_id}", response_model=UploadTaskRead)
def get_upload_task(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
):
    return _get_task_or_404(db, task_id)
