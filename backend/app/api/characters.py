from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import optional_admin, require_admin
from app.database import get_db
from app.models import Character, Image
from app.schemas.character import CharacterCreate, CharacterDetail, CharacterListResponse, CharacterRead, CharacterUpdate
from app.schemas.common import ImageSummary

router = APIRouter(prefix="/characters", tags=["characters"])


def _character_options(detail: bool = False):
    options = [selectinload(Character.work), selectinload(Character.avatar_image)]
    if detail:
        options.append(selectinload(Character.images))
    return options


def _is_public_image(image) -> bool:
    return bool(image and image.is_public and image.rating != "hidden")


def _serialize_character(character: Character, admin: bool, detail: bool = False):
    payload = CharacterDetail.model_validate(character) if detail else CharacterRead.model_validate(character)
    if not admin:
        if not _is_public_image(character.avatar_image):
            payload.avatar_image = None
        if detail:
            payload.images = [ImageSummary.model_validate(image) for image in character.images if _is_public_image(image)]
    return payload


def _ensure_image_exists(db: Session, image_id: int | None) -> None:
    if image_id is None:
        return
    if not db.get(Image, image_id):
        raise HTTPException(status_code=422, detail=f"Image {image_id} not found")


@router.get("", response_model=CharacterListResponse)
def list_characters(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    work_id: int | None = None,
    q: str | None = None,
):
    stmt = select(Character).options(*_character_options())
    if work_id:
        stmt = stmt.where(Character.work_id == work_id)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Character.name.ilike(needle), Character.original_name.ilike(needle), Character.aliases.ilike(needle))
        )
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.order_by(Character.name.asc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_serialize_character(item, admin=bool(admin)) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", response_model=CharacterRead, status_code=status.HTTP_201_CREATED)
def create_character(
    payload: CharacterCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    _ensure_image_exists(db, payload.avatar_image_id)
    character = Character(**payload.model_dump())
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


@router.get("/{character_id}", response_model=CharacterDetail)
def get_character(
    character_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
):
    character = db.scalar(select(Character).options(*_character_options(detail=True)).where(Character.id == character_id))
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return _serialize_character(character, admin=bool(admin), detail=True)


@router.put("/{character_id}", response_model=CharacterRead)
def update_character(
    character_id: int,
    payload: CharacterUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    data = payload.model_dump(exclude_unset=True)
    _ensure_image_exists(db, data.get("avatar_image_id"))
    for key, value in data.items():
        setattr(character, key, value)
    db.commit()
    db.refresh(character)
    return character


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(
    character_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete(character)
    db.commit()
    return None
