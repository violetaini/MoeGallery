from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Image
from app.services.image_service import image_orientation
from app.services.storage_service import normalize_storage_relative_path, requires_sdr_preview, resolve_storage_file
from app.utils.image_process import InvalidImageError, inspect_image


@dataclass
class PreviewCleanupSummary:
    checked: int = 0
    candidates: int = 0
    retained_hdr: int = 0
    retained_unverified: int = 0
    removed: int = 0
    missing: int = 0
    unsafe: int = 0
    failed: int = 0


def _is_preview_path(relative_path: str) -> bool:
    try:
        return normalize_storage_relative_path(relative_path).startswith("preview/")
    except ValueError:
        return False


def _refresh_image_inspection(image: Image, inspection) -> None:
    image.is_animated = inspection.is_animated
    image.dynamic_range = inspection.dynamic_range
    image.bit_depth = inspection.bit_depth
    image.color_profile = inspection.color_profile
    image.width = inspection.width
    image.height = inspection.height
    image.orientation = image_orientation(inspection.width, inspection.height)


def prune_redundant_previews(db: Session, apply: bool = False) -> PreviewCleanupSummary:
    """Remove legacy SDR/animated preview derivatives after verifying each source file.

    Preview variants are retained for HDR images because SDR displays need the
    WebP fallback. Source inspection is deliberately repeated here so stale
    metadata can never cause an HDR preview to be deleted.
    """
    summary = PreviewCleanupSummary()
    images = db.scalars(
        select(Image).where(Image.preview_path.is_not(None)).order_by(Image.id)
    ).all()

    for image in images:
        preview_path = str(image.preview_path or "")
        summary.checked += 1
        if not preview_path:
            continue
        if not _is_preview_path(preview_path):
            summary.unsafe += 1
            print(f"SKIP unsafe preview path image_id={image.id} preview_path={preview_path}")
            continue

        try:
            source = resolve_storage_file(image.file_path)
            inspection = inspect_image(source.read_bytes())
        except (InvalidImageError, OSError, ValueError) as exc:
            summary.retained_unverified += 1
            print(f"SKIP unverified image_id={image.id} file_path={image.file_path}: {exc}")
            continue

        if requires_sdr_preview(inspection.dynamic_range):
            summary.retained_hdr += 1
            if apply:
                _refresh_image_inspection(image, inspection)
                db.commit()
            continue

        summary.candidates += 1
        if not apply:
            continue

        try:
            target = resolve_storage_file(preview_path)
            exists = target.is_file()
            image.preview_path = None
            _refresh_image_inspection(image, inspection)
            db.commit()
        except Exception as exc:
            db.rollback()
            summary.failed += 1
            print(f"FAILED database update image_id={image.id} preview_path={preview_path}: {exc}")
            continue

        if not exists:
            summary.missing += 1
            continue

        try:
            target.unlink()
            summary.removed += 1
        except OSError as exc:
            summary.failed += 1
            print(f"FAILED file removal image_id={image.id} preview_path={preview_path}: {exc}")
            try:
                image.preview_path = preview_path
                db.commit()
            except Exception as restore_exc:
                db.rollback()
                print(f"FAILED metadata restore image_id={image.id}: {restore_exc}")

    return summary
