from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models import Character, Image, Work
from app.schemas.search import StatsResponse

router = APIRouter(tags=["stats"])


def _storage_total_size() -> int:
    total = 0
    for name in ("original", "preview", "thumbnail"):
        directory = settings.storage_path / name
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    return total


@router.get("/stats", response_model=StatsResponse)
def stats(db: Annotated[Session, Depends(get_db)], admin: Annotated[dict, Depends(require_admin)]):
    image_count = db.scalar(select(func.count(Image.id))) or 0
    public_image_count = db.scalar(select(func.count(Image.id)).where(Image.is_public.is_(True))) or 0
    return {
        "image_count": image_count,
        "public_image_count": public_image_count,
        "work_count": db.scalar(select(func.count(Work.id))) or 0,
        "character_count": db.scalar(select(func.count(Character.id))) or 0,
        "total_file_size": _storage_total_size(),
    }
