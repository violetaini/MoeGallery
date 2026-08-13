from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_system_read
from app.config import settings
from app.database import get_db
from app.models import Character, Image, Work
from app.schemas.search import StatsResponse
from app.services.storage_stats_service import media_storage_stats

router = APIRouter(tags=["stats"])


def _storage_total_size() -> int:
    return sum(int(item["size_bytes"]) for item in media_storage_stats(settings.storage_path).values())


@router.get("/stats", response_model=StatsResponse)
def stats(db: Annotated[Session, Depends(get_db)], admin: Annotated[dict, Depends(require_system_read)]):
    image_count = db.scalar(select(func.count(Image.id))) or 0
    public_image_count = db.scalar(select(func.count(Image.id)).where(Image.is_public.is_(True))) or 0
    return {
        "image_count": image_count,
        "public_image_count": public_image_count,
        "work_count": db.scalar(select(func.count(Work.id))) or 0,
        "character_count": db.scalar(select(func.count(Character.id))) or 0,
        "total_file_size": _storage_total_size(),
    }
