from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.api.helpers import parse_id_csv
from app.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models import UploadTask
from app.models import Image
from app.schemas.upload_task import (
    UploadDuplicateCheckRequest,
    UploadDuplicateCheckResponse,
    UploadTaskCreateResponse,
    UploadTaskListResponse,
    UploadTaskRead,
)
from app.services.storage_service import save_upload_task_file
from app.services.upload_task_service import create_upload_task, start_upload_worker, task_options
from app.utils.hash import sha256_bytes
from app.utils.image_process import InvalidImageError, validate_upload_filename

router = APIRouter(prefix="/upload-tasks", tags=["upload-tasks"])


@router.post("", response_model=UploadTaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_upload_tasks(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
    files: Annotated[list[UploadFile], File()],
    work_ids: str | None = Form(None),
    character_ids: str | None = Form(None),
    rating: str = Form("safe"),
    is_public: bool = Form(True),
    source_url: str | None = Form(None),
    artist_name: str | None = Form(None),
    merge_duplicate_relations: bool = Form(False),
):
    if rating not in {"safe", "sensitive", "hidden"}:
        raise HTTPException(status_code=422, detail="rating must be safe, sensitive, or hidden")
    try:
        parsed_work_ids = parse_id_csv(work_ids)
        parsed_character_ids = parse_id_csv(character_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Relation ids must be comma separated integers") from exc

    tasks: list[UploadTask] = []
    for upload in files:
        try:
            validate_upload_filename(upload.filename)
            data = await upload.read()
            if not data:
                raise InvalidImageError("Empty upload")
            if len(data) > settings.max_upload_size:
                raise InvalidImageError("File is larger than configured upload limit")
            staged_path = save_upload_task_file(data, upload.filename)
        except InvalidImageError as exc:
            raise HTTPException(status_code=400, detail=f"{upload.filename}: {exc}") from exc

        task = create_upload_task(
            db,
            staged_path=staged_path,
            original_filename=upload.filename,
            content_type=upload.content_type,
            file_size=len(data),
            rating=rating,
            is_public=is_public,
            source_url=source_url,
            artist_name=artist_name,
            work_ids=parsed_work_ids,
            character_ids=parsed_character_ids,
            merge_duplicate_relations=merge_duplicate_relations,
        )
        tasks.append(task)

    start_upload_worker()
    ids = [task.id for task in tasks]
    refreshed = db.scalars(select(UploadTask).options(*task_options()).where(UploadTask.id.in_(ids))).unique().all()
    return {"items": refreshed}


@router.post("/check-duplicates", response_model=UploadDuplicateCheckResponse)
def check_upload_duplicates(
    payload: UploadDuplicateCheckRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    seen: set[str] = set()
    items = []
    for item in payload.items:
        digest = item.sha256.lower()
        existing = db.scalar(
            select(Image)
            .options(
                selectinload(Image.works),
                selectinload(Image.characters),
                selectinload(Image.tags),
            )
            .where(Image.sha256 == digest)
        )
        duplicate_in_batch = digest in seen
        seen.add(digest)
        items.append(
            {
                "filename": item.filename,
                "sha256": digest,
                "duplicate": existing is not None,
                "duplicate_in_batch": duplicate_in_batch,
                "existing_image": existing,
            }
        )
    return {"items": items}


@router.post("/check-duplicates-files", response_model=UploadDuplicateCheckResponse)
async def check_upload_duplicate_files(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
    files: Annotated[list[UploadFile], File()],
):
    seen: set[str] = set()
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
        existing = db.scalar(
            select(Image)
            .options(
                selectinload(Image.works),
                selectinload(Image.characters),
                selectinload(Image.tags),
            )
            .where(Image.sha256 == digest)
        )
        duplicate_in_batch = digest in seen
        seen.add(digest)
        items.append(
            {
                "filename": upload.filename,
                "sha256": digest,
                "duplicate": existing is not None,
                "duplicate_in_batch": duplicate_in_batch,
                "existing_image": existing,
            }
        )
    return {"items": items}


@router.get("", response_model=UploadTaskListResponse)
def list_upload_tasks(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
    ids: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    stmt = select(UploadTask).options(*task_options()).order_by(desc(UploadTask.created_at)).limit(limit)
    if ids:
        try:
            parsed_ids = parse_id_csv(ids)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="ids must be comma separated integers") from exc
        stmt = select(UploadTask).options(*task_options()).where(UploadTask.id.in_(parsed_ids)).order_by(UploadTask.id)
    items = db.scalars(stmt).unique().all()
    return {"items": items}


@router.get("/{task_id}", response_model=UploadTaskRead)
def get_upload_task(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    task = db.scalar(select(UploadTask).options(*task_options()).where(UploadTask.id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="Upload task not found")
    return task
