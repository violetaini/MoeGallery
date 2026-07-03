from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import optional_admin, require_admin
from app.database import get_db
from app.models import Character, Image, Work
from app.schemas.common import ImageSummary
from app.schemas.work import WorkCreate, WorkDetail, WorkListResponse, WorkRead, WorkUpdate

router = APIRouter(prefix="/works", tags=["works"])


def _work_options(detail: bool = False):
    options = [selectinload(Work.cover_image), selectinload(Work.backdrop_image)]
    if detail:
        options.extend(
            [
                selectinload(Work.characters).selectinload(Character.avatar_image),
                selectinload(Work.characters).selectinload(Character.work),
                selectinload(Work.images),
            ]
        )
    return options


def _is_public_image(image) -> bool:
    return bool(image and image.is_public and image.rating != "hidden")


def _serialize_work(work: Work, admin: bool, detail: bool = False):
    payload = WorkDetail.model_validate(work) if detail else WorkRead.model_validate(work)
    if not admin:
        if not _is_public_image(work.cover_image):
            payload.cover_image = None
        if not _is_public_image(work.backdrop_image):
            payload.backdrop_image = None
        if detail:
            payload.images = [ImageSummary.model_validate(image) for image in work.images if _is_public_image(image)]
            characters_by_id = {character.id: character for character in work.characters}
            for character_payload in payload.characters:
                character = characters_by_id.get(character_payload.id)
                if not character or not _is_public_image(character.avatar_image):
                    character_payload.avatar_image = None
    return payload


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
    q: str | None = None,
):
    stmt = select(Work).options(*_work_options())
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(or_(Work.name.ilike(needle), Work.original_name.ilike(needle), Work.aliases.ilike(needle)))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(
        stmt.order_by(Work.sort_order.asc(), Work.name.asc()).offset((page - 1) * page_size).limit(page_size)
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
    admin: Annotated[dict, Depends(require_admin)],
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
    work = db.scalar(select(Work).options(*_work_options(detail=True)).where(Work.id == work_id))
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    return _serialize_work(work, admin=bool(admin), detail=True)


@router.put("/{work_id}", response_model=WorkRead)
def update_work(
    work_id: int,
    payload: WorkUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
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
    admin: Annotated[dict, Depends(require_admin)],
):
    work = db.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    db.delete(work)
    db.commit()
    return None
