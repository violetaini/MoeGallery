from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import optional_admin
from app.database import get_db
from app.models import Image
from app.services.storage_service import normalize_storage_relative_path, resolve_storage_file
from app.utils.image_process import WEBP_MIME_TYPE

router = APIRouter(prefix="/storage", tags=["storage"])


def _find_image_by_path(db: Session, relative_path: str) -> Image | None:
    return (
        db.query(Image)
        .filter(
            (Image.file_path == relative_path)
            | (Image.preview_path == relative_path)
            | (Image.thumbnail_path == relative_path)
        )
        .first()
    )
@router.get("/{relative_path:path}")
def get_storage_file(
    relative_path: str,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
):
    try:
        normalized = normalize_storage_relative_path(relative_path)
        target = resolve_storage_file(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    image = _find_image_by_path(db, normalized)
    if not image:
        raise HTTPException(status_code=404, detail="File not found")

    is_public_image = image.is_public and image.rating != "hidden"
    if not admin and not is_public_image:
        raise HTTPException(status_code=404, detail="File not found")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = image.mime_type if normalized == image.file_path else WEBP_MIME_TYPE
    return FileResponse(target, media_type=media_type)
