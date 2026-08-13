from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.helpers import LIKE_ESCAPE, contains_like_pattern, non_structural_image_conditions
from app.auth import optional_admin, require_library_delete, require_library_write
from app.database import get_db
from app.models import Character, Image, Work
from app.models.associations import image_works
from app.schemas.work import WorkCreate, WorkDetail, WorkListResponse, WorkRead, WorkUpdate

router = APIRouter(prefix="/works", tags=["works"])


def _work_options():
    return [selectinload(Work.cover_image), selectinload(Work.backdrop_image)]


def _is_public_image(image) -> bool:
    return bool(image and image.is_public and image.rating != "hidden")


def _serialize_work(
    work: Work,
    admin: bool,
    *,
    image_count: int | None = None,
    character_count: int | None = None,
):
    detail = image_count is not None and character_count is not None
    payload = WorkDetail.model_validate(work) if detail else WorkRead.model_validate(work)
    if detail:
        payload.image_count = image_count
        payload.character_count = character_count
    if not admin:
        if not _is_public_image(work.cover_image):
            payload.cover_image = None
        if not _is_public_image(work.backdrop_image):
            payload.backdrop_image = None
    return payload


def _work_image_count(db: Session, work_id: int, admin: bool) -> int:
    stmt = (
        select(func.count())
        .select_from(image_works.join(Image, image_works.c.image_id == Image.id))
        .where(
            image_works.c.work_id == work_id,
            *non_structural_image_conditions(),
        )
    )
    if not admin:
        stmt = stmt.where(Image.is_public.is_(True), Image.rating != "hidden")
    return db.scalar(stmt) or 0


def _work_character_count(db: Session, work_id: int) -> int:
    return db.scalar(select(func.count(Character.id)).where(Character.work_id == work_id)) or 0


def _ensure_image_exists(db: Session, image_id: int | None) -> None:
    if image_id is None:
        return
    if not db.get(Image, image_id):
        raise HTTPException(status_code=422, detail=f"Image {image_id} not found")


@router.get("", response_model=WorkListResponse)
def list_works(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    q: str | None = Query(None, max_length=255),
):
    stmt = select(Work).options(*_work_options())
    if q and q.strip():
        needle = contains_like_pattern(q)
        stmt = stmt.where(
            or_(
                Work.name.ilike(needle, escape=LIKE_ESCAPE),
                Work.original_name.ilike(needle, escape=LIKE_ESCAPE),
                Work.aliases.ilike(needle, escape=LIKE_ESCAPE),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(
        stmt.order_by(Work.sort_order.asc(), Work.name.asc(), Work.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_serialize_work(item, admin=bool(admin)) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", response_model=WorkRead, status_code=status.HTTP_201_CREATED)
def create_work(
    payload: WorkCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_library_write)],
):
    _ensure_image_exists(db, payload.cover_image_id)
    _ensure_image_exists(db, payload.backdrop_image_id)
    work = Work(**payload.model_dump())
    db.add(work)
    db.commit()
    db.refresh(work)
    return work


@router.get("/{work_id}", response_model=WorkDetail)
def get_work(
    work_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
):
    work = db.scalar(select(Work).options(*_work_options()).where(Work.id == work_id))
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    is_admin = bool(admin)
    return _serialize_work(
        work,
        admin=is_admin,
        image_count=_work_image_count(db, work_id, is_admin),
        character_count=_work_character_count(db, work_id),
    )


@router.put("/{work_id}", response_model=WorkRead)
def update_work(
    work_id: int,
    payload: WorkUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_library_write)],
):
    work = db.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    data = payload.model_dump(exclude_unset=True)
    _ensure_image_exists(db, data.get("cover_image_id"))
    _ensure_image_exists(db, data.get("backdrop_image_id"))
    for key, value in data.items():
        setattr(work, key, value)
    db.commit()
    db.refresh(work)
    return work


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work(
    work_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_library_delete)],
):
    work = db.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    db.delete(work)
    db.commit()
    return None
