from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_updates_read, require_updates_run
from app.database import get_db
from app.schemas.update import UpdateCheckResponse, UpdateTaskCreate, UpdateTaskListResponse, UpdateTaskRead
from app.services import update_service

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("/check", response_model=UpdateCheckResponse)
def check_updates(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_updates_read)],
):
    return update_service.check_for_updates(db)


@router.get("/tasks", response_model=UpdateTaskListResponse)
def list_update_tasks(
    _admin: Annotated[dict, Depends(require_updates_read)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=100, deprecated=True),
):
    if limit is not None:
        page_size = limit
    items, total, has_running_task = update_service.list_task_page(page=page, page_size=page_size)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_running_task": has_running_task,
    }


@router.post("/tasks", response_model=UpdateTaskRead, status_code=status.HTTP_202_ACCEPTED)
def create_update_task(
    payload: UpdateTaskCreate,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_updates_run)],
):
    try:
        return update_service.create_update_task(
            db,
            version=payload.version,
            dry_run=payload.dry_run,
            force=payload.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"启动更新任务失败：{exc}") from exc


@router.get("/tasks/{task_id}", response_model=UpdateTaskRead)
def get_update_task(
    task_id: str,
    _admin: Annotated[dict, Depends(require_updates_read)],
):
    try:
        return update_service.read_task(task_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Update task not found") from exc
