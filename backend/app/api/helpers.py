from fastapi import Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Character, Image, Work

LIKE_ESCAPE = "!"


def contains_like_pattern(value: str) -> str:
    escaped = value.strip().replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


def non_structural_image_conditions():
    return (
        ~select(Work.id).where(Work.cover_image_id == Image.id).correlate(Image).exists(),
        ~select(Work.id).where(Work.backdrop_image_id == Image.id).correlate(Image).exists(),
        ~select(Character.id).where(Character.avatar_image_id == Image.id).correlate(Image).exists(),
    )


def pagination_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
) -> tuple[int, int]:
    return page, page_size


def parse_id_csv(value: str | None) -> list[int] | None:
    if value is None or value.strip() == "":
        return None
    ids: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return ids


def validate_relation_ids(
    db: Session,
    work_ids: list[int] | None,
    character_ids: list[int] | None,
) -> None:
    normalized_work_ids = list(dict.fromkeys(work_ids or []))
    normalized_character_ids = list(dict.fromkeys(character_ids or []))
    if normalized_work_ids:
        found = set(db.scalars(select(Work.id).where(Work.id.in_(normalized_work_ids))).all())
        missing = [work_id for work_id in normalized_work_ids if work_id not in found]
        if missing:
            raise ValueError(f"Works not found: {missing}")
    if normalized_character_ids:
        found = set(db.scalars(select(Character.id).where(Character.id.in_(normalized_character_ids))).all())
        missing = [character_id for character_id in normalized_character_ids if character_id not in found]
        if missing:
            raise ValueError(f"Characters not found: {missing}")
