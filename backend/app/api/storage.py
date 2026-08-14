from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import authenticate_optional_request
from app.database import get_db
from app.models import Image
from app.services.media_delivery_service import (
    MediaVariant,
    accel_redirect_uri,
    media_etag,
    media_type_for_variant,
    private_media_cache_control,
    public_media_cache_control,
    resolve_media_variant,
)
from app.services.storage_service import normalize_storage_relative_path, resolve_storage_file
from app.services.share_service import share_allows_image
from app.utils.image_process import WEBP_MIME_TYPE

router = APIRouter(tags=["storage"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail="File not found",
        headers={"Cache-Control": "private, no-store, max-age=0"},
    )


def _find_image_by_path(db: Session, relative_path: str) -> Image | None:
    return db.scalar(
        select(Image).where(
            or_(
                Image.file_path == relative_path,
                Image.preview_path == relative_path,
                Image.thumbnail_path == relative_path,
            )
        )
    )


def _etag_matches(request: Request, etag: str) -> bool:
    candidates = request.headers.get("if-none-match", "")
    return any(
        candidate.strip() == "*" or candidate.strip().removeprefix("W/") == etag
        for candidate in candidates.split(",")
    )


def _deliver_media(
    *,
    request: Request,
    image: Image,
    relative_path: str,
    requested_variant: MediaVariant,
    served_variant: MediaVariant,
    media_type: str,
    db: Session,
    share_token: str | None = None,
) -> Response:
    is_public_image = image.is_public and image.rating != "hidden"
    is_shared_image = share_allows_image(db, share_token, image.id)
    if not is_public_image and not is_shared_image:
        admin = authenticate_optional_request(request, db, "library:read")
        if not admin:
            raise _not_found()
    try:
        target = resolve_storage_file(relative_path)
    except ValueError as exc:
        raise _not_found() from exc
    if not target.is_file():
        raise _not_found()

    cache_control = public_media_cache_control() if is_public_image and not is_shared_image else private_media_cache_control()
    etag = media_etag(image, requested_variant, relative_path, target)
    headers = {
        "Cache-Control": cache_control,
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
        "X-AGMS-Media-Variant": served_variant,
    }
    if is_public_image or is_shared_image:
        headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    if _etag_matches(request, etag):
        return Response(status_code=304, headers=headers)

    internal_uri = accel_redirect_uri(relative_path)
    if internal_uri:
        headers["X-Accel-Redirect"] = internal_uri
        return Response(status_code=200, media_type=media_type, headers=headers)
    return FileResponse(target, media_type=media_type, headers=headers)


@router.head("/media/{image_id}/{variant}/{media_version}", include_in_schema=False)
@router.get("/media/{image_id}/{variant}/{media_version}")
def get_media_file(
    image_id: int,
    variant: MediaVariant,
    media_version: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    share_token: str | None = Query(default=None, alias="share", max_length=64),
):
    image = db.get(Image, image_id)
    if not image or max(1, int(image.media_version or 1)) != media_version:
        raise _not_found()
    try:
        relative_path, served_variant = resolve_media_variant(image, variant)
    except ValueError as exc:
        raise _not_found() from exc
    return _deliver_media(
        request=request,
        image=image,
        relative_path=relative_path,
        requested_variant=variant,
        served_variant=served_variant,
        media_type=media_type_for_variant(image, served_variant),
        db=db,
        share_token=share_token,
    )


@router.head("/storage/{relative_path:path}", include_in_schema=False)
@router.get("/storage/{relative_path:path}")
def get_storage_file(
    relative_path: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        normalized = normalize_storage_relative_path(relative_path)
    except ValueError as exc:
        raise _not_found() from exc
    image = _find_image_by_path(db, normalized)
    if not image:
        raise _not_found()
    if normalized == image.file_path:
        served_variant: MediaVariant = "original"
        media_type = image.mime_type
    elif normalized == image.preview_path:
        served_variant = "preview"
        media_type = WEBP_MIME_TYPE
    else:
        served_variant = "thumbnail"
        media_type = WEBP_MIME_TYPE
    return _deliver_media(
        request=request,
        image=image,
        relative_path=normalized,
        requested_variant=served_variant,
        served_variant=served_variant,
        media_type=media_type,
        db=db,
    )
