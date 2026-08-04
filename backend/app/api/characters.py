from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import optional_admin, require_library_delete, require_library_write
from app.database import get_db
from app.models import Character, Image
from app.models.associations import image_characters
from app.schemas.character import CharacterCreate, CharacterDetail, CharacterListResponse, CharacterRead, CharacterUpdate

router = APIRouter(prefix="/characters", tags=["characters"])


def _character_options():
    return [selectinload(Character.work), selectinload(Character.avatar_image)]


def _is_public_image(image) -> bool:
    return bool(image and image.is_public and image.rating != "hidden")


def _serialize_character(character: Character, admin: bool, *, image_count: int | None = None):
    detail = image_count is not None
    payload = CharacterDetail.model_validate(character) if detail else CharacterRead.model_validate(character)
    if detail:
        payload.image_count = image_count
    if not admin:
        if not _is_public_image(character.avatar_image):
            payload.avatar_image = None
    return payload


def _character_image_count(db: Session, character_id: int, admin: bool) -> int:
    if admin:
        stmt = select(func.count()).select_from(image_characters).where(
            image_characters.c.character_id == character_id
        )
    else:
        stmt = (
            select(func.count())
            .select_from(image_characters.join(Image, image_characters.c.image_id == Image.id))
            .where(
                image_characters.c.character_id == character_id,
                Image.is_public.is_(True),
                Image.rating != "hidden",
            )
        )
    return db.scalar(stmt) or 0


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
    admin: Annotated[dict, Depends(require_library_write)],
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
    character = db.scalar(select(Character).options(*_character_options()).where(Character.id == character_id))
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    is_admin = bool(admin)
    return _serialize_character(
        character,
        admin=is_admin,
        image_count=_character_image_count(db, character_id, is_admin),
    )


@router.put("/{character_id}", response_model=CharacterRead)
def update_character(
    character_id: int,
    payload: CharacterUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_library_write)],
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
    admin: Annotated[dict, Depends(require_library_delete)],
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete(character)
    db.commit()
    return None
