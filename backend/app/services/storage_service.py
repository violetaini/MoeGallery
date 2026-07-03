from pathlib import Path, PurePosixPath
from typing import TypedDict
from uuid import uuid4

from app.config import settings
from app.utils.image_process import (
    AVIF_EXTENSION,
    AVIF_MIME_TYPE,
    DYNAMIC_RANGE_HDR,
    ImageInspection,
    WEBP_EXTENSION,
    WEBP_MIME_TYPE,
    save_hdr_avif_image,
    save_webp_derivative,
    save_webp_image,
)


class SavedImageFiles(TypedDict):
    filename: str
    original_filename: str
    file_path: str
    preview_path: str
    thumbnail_path: str
    file_size: int
    mime_type: str
    dynamic_range: str
    bit_depth: int
    color_profile: str | None


def ensure_storage_dirs() -> None:
    for name in ("original", "preview", "thumbnail", "tasks"):
        (settings.storage_path / name).mkdir(parents=True, exist_ok=True)


def normalize_storage_relative_path(relative_path: str) -> str:
    candidate = str(relative_path or "").replace("\\", "/").lstrip("/")
    path = PurePosixPath(candidate)
    if not candidate or path.is_absolute():
        raise ValueError("Invalid storage path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Invalid storage path")
    return path.as_posix()


def resolve_storage_file(relative_path: str) -> Path:
    normalized = normalize_storage_relative_path(relative_path)
    base = settings.storage_path.resolve()
    target = (settings.storage_path / normalized).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("Invalid storage path") from exc
    return target


def safe_original_name(filename: str | None) -> str:
    if not filename:
        return "upload"
    return Path(filename).name.replace("\x00", "")


def save_image_files(
    data: bytes,
    sha256: str,
    original_filename: str | None,
    inspection: ImageInspection,
) -> SavedImageFiles:
    ensure_storage_dirs()
    clean_name = safe_original_name(original_filename)
    unique = f"{sha256[:16]}-{uuid4().hex[:8]}"
    transcode_hdr_to_avif = inspection.format_name == "JXR" and inspection.dynamic_range == DYNAMIC_RANGE_HDR
    preserve_original = inspection.is_animated or inspection.dynamic_range == DYNAMIC_RANGE_HDR
    if transcode_hdr_to_avif:
        original_filename_on_disk = f"{unique}{AVIF_EXTENSION}"
    elif preserve_original:
        original_filename_on_disk = f"{unique}{inspection.extension}"
    else:
        original_filename_on_disk = f"{unique}{WEBP_EXTENSION}"
    preview_filename = f"{unique}.webp"
    thumbnail_filename = f"{unique}.webp"

    original_path = settings.storage_path / "original" / original_filename_on_disk
    preview_path = settings.storage_path / "preview" / preview_filename
    thumbnail_path = settings.storage_path / "thumbnail" / thumbnail_filename

    if transcode_hdr_to_avif:
        save_hdr_avif_image(data, original_path)
        mime_type = AVIF_MIME_TYPE
        file_size = original_path.stat().st_size
    elif preserve_original:
        original_path.write_bytes(data)
        mime_type = inspection.mime_type
        file_size = original_path.stat().st_size
    else:
        save_webp_image(data, original_path)
        mime_type = WEBP_MIME_TYPE
        file_size = original_path.stat().st_size

    save_webp_derivative(data, preview_path, settings.preview_max_size)
    save_webp_derivative(data, thumbnail_path, settings.thumbnail_max_size)

    return {
        "filename": original_filename_on_disk,
        "original_filename": clean_name,
        "file_path": f"original/{original_filename_on_disk}",
        "preview_path": f"preview/{preview_filename}",
        "thumbnail_path": f"thumbnail/{thumbnail_filename}",
        "file_size": file_size,
        "mime_type": mime_type,
        "dynamic_range": inspection.dynamic_range,
        "bit_depth": 10 if transcode_hdr_to_avif else inspection.bit_depth,
        "color_profile": "bt2100-pq" if transcode_hdr_to_avif else inspection.color_profile,
    }


def save_upload_task_file(data: bytes, original_filename: str | None) -> str:
    ensure_storage_dirs()
    suffix = Path(original_filename or "").suffix.lower() or ".bin"
    filename = f"{uuid4().hex}{suffix}"
    path = settings.storage_path / "tasks" / filename
    path.write_bytes(data)
    return f"tasks/{filename}"


def delete_storage_file(relative_path: str | None) -> None:
    if not relative_path:
        return
    try:
        target = resolve_storage_file(relative_path)
    except ValueError:
        return
    if target.exists() and target.is_file():
        target.unlink()
