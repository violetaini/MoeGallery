from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.schemas.update import UpdateCheckResponse, UpdateTaskCreate, UpdateTaskListResponse, UpdateTaskRead
from app.services import update_service

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("/check", response_model=UpdateCheckResponse)
def check_updates(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_admin)],
):
    return update_service.check_for_updates(db)


@router.get("/tasks", response_model=UpdateTaskListResponse)
def list_update_tasks(
    _admin: Annotated[dict, Depends(require_admin)],
    limit: int = Query(20, ge=1, le=100),
):
    return {"items": update_service.list_tasks(limit=limit)}


@router.post("/tasks", response_model=UpdateTaskRead, status_code=status.HTTP_202_ACCEPTED)
def create_update_task(
    payload: UpdateTaskCreate,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_admin)],
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
    _admin: Annotated[dict, Depends(require_admin)],
):
    try:
        return update_service.read_task(task_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Update task not found") from exc
