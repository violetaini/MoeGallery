from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, Image, Tag, Work
from app.schemas.character import CharacterRead
from app.schemas.common import ImageSummary
from app.schemas.search import SearchResponse
from app.schemas.tag import TagRead
from app.schemas.work import WorkRead

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    db: Annotated[Session, Depends(get_db)],
    q: str = Query(min_length=1),
    limit: int = Query(12, ge=1, le=50),
):
    needle = f"%{q.strip()}%"
    images = db.scalars(
        select(Image)
        .where(
            Image.is_public.is_(True),
            Image.rating != "hidden",
            Image.works.any(),
            Image.characters.any(),
            or_(
                Image.filename.ilike(needle),
                Image.original_filename.ilike(needle),
                Image.artist_name.ilike(needle),
                Image.source_url.ilike(needle),
            ),
        )
        .order_by(desc(Image.created_at))
        .limit(limit)
    ).all()
    works = db.scalars(
        select(Work)
        .where(or_(Work.name.ilike(needle), Work.original_name.ilike(needle), Work.aliases.ilike(needle)))
        .order_by(Work.sort_order.asc(), Work.name.asc())
        .limit(limit)
    ).all()
    characters = db.scalars(
        select(Character)
        .where(
            Character.work.has(Work.id.is_not(None)),
            or_(Character.name.ilike(needle), Character.original_name.ilike(needle), Character.aliases.ilike(needle)),
        )
        .order_by(Character.name.asc())
        .limit(limit)
    ).all()
    tags = db.scalars(
        select(Tag)
        .where(or_(Tag.name.ilike(needle), Tag.aliases.ilike(needle)))
        .order_by(Tag.type.asc(), Tag.name.asc())
        .limit(limit)
    ).all()
    work_payloads = []
    for work in works:
        payload = WorkRead.model_validate(work)
        if work.cover_image and (not work.cover_image.is_public or work.cover_image.rating == "hidden"):
            payload.cover_image = None
        work_payloads.append(payload)

    character_payloads = []
    for character in characters:
        payload = CharacterRead.model_validate(character)
        if character.avatar_image and (not character.avatar_image.is_public or character.avatar_image.rating == "hidden"):
            payload.avatar_image = None
        character_payloads.append(payload)

    tag_payloads = [TagRead.model_validate(tag) for tag in tags]
    image_payloads = [ImageSummary.model_validate(image) for image in images]
    return {"images": image_payloads, "works": work_payloads, "characters": character_payloads, "tags": tag_payloads}
