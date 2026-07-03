from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import optional_admin, require_admin
from app.database import get_db
from app.models import Tag
from app.schemas.common import ImageSummary
from app.schemas.tag import TagCreate, TagDetail, TagListResponse, TagRead, TagUpdate

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=TagListResponse)
def list_tags(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    q: str | None = None,
    type: str | None = None,
):
    stmt = select(Tag)
    if type:
        stmt = stmt.where(Tag.type == type)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(or_(Tag.name.ilike(needle), Tag.aliases.ilike(needle)))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.order_by(Tag.type.asc(), Tag.name.asc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: TagCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    tag = Tag(**payload.model_dump())
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.get("/{tag_id}", response_model=TagDetail)
def get_tag(
    tag_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
):
    tag = db.scalar(select(Tag).options(selectinload(Tag.images)).where(Tag.id == tag_id))
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    payload = TagDetail.model_validate(tag)
    if not admin:
        payload.images = [ImageSummary.model_validate(image) for image in tag.images if image.is_public and image.rating != "hidden"]
    return payload


@router.put("/{tag_id}", response_model=TagRead)
def update_tag(
    tag_id: int,
    payload: TagUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tag, key, value)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()
    return None
