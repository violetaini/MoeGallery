import hashlib
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from app.config import settings
from app.models import Image
from app.services.storage_service import normalize_storage_relative_path
from app.utils.image_process import WEBP_MIME_TYPE

MediaVariant = Literal["original", "preview", "thumbnail"]
MEDIA_VARIANTS: tuple[MediaVariant, ...] = ("original", "preview", "thumbnail")


def rotate_media_version(image: Image) -> int:
    """Make every public media URL for an image point at a fresh immutable version."""
    image.media_version = max(1, int(image.media_version or 1)) + 1
    return image.media_version


def build_media_url(image: Image, variant: MediaVariant) -> str:
    version = max(1, int(image.media_version or 1))
    return f"/media/{image.id}/{variant}/{version}"


def resolve_media_variant(image: Image, variant: MediaVariant) -> tuple[str, MediaVariant]:
    candidates: dict[MediaVariant, tuple[tuple[str | None, MediaVariant], ...]] = {
        "original": ((image.file_path, "original"),),
        "preview": (
            (image.preview_path, "preview"),
            (image.file_path, "original"),
            (image.thumbnail_path, "thumbnail"),
        ),
        "thumbnail": (
            (image.thumbnail_path, "thumbnail"),
            (image.preview_path, "preview"),
            (image.file_path, "original"),
        ),
    }
    for path, served_variant in candidates[variant]:
        if path:
            return normalize_storage_relative_path(path), served_variant
    raise ValueError("Image variant is unavailable")


def media_type_for_variant(image: Image, served_variant: MediaVariant) -> str:
    return image.mime_type if served_variant == "original" else WEBP_MIME_TYPE


def media_etag(
    image: Image,
    requested_variant: MediaVariant,
    relative_path: str,
    target: Path,
) -> str:
    stat = target.stat()
    source = ":".join(
        (
            str(image.id),
            str(max(1, int(image.media_version or 1))),
            requested_variant,
            relative_path,
            str(stat.st_size),
            str(stat.st_mtime_ns),
        )
    )
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]
    return f'"{digest}"'


def public_media_cache_control() -> str:
    browser_seconds = max(0, settings.media_public_browser_cache_seconds)
    shared_seconds = max(0, settings.media_public_shared_cache_seconds)
    return f"public, max-age={browser_seconds}, s-maxage={shared_seconds}, must-revalidate"


def private_media_cache_control() -> str:
    return "private, no-store, max-age=0"


def accel_redirect_uri(relative_path: str) -> str | None:
    prefix = settings.media_accel_redirect_prefix.strip().rstrip("/")
    if not prefix:
        return None
    return f"{prefix}/{quote(relative_path, safe='/')}"
