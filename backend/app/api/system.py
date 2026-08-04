import shutil
import subprocess
from pathlib import Path
from typing import Annotated

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth import require_system_read
from app.config import ROOT_DIR, auth_secret_health, settings
from app.database import database_concurrency_info, engine, get_db
from app.models import Image
from app.services.app_setting_service import (
    get_upload_claim_batch_size,
    get_upload_failed_retention_days,
    get_upload_task_max_attempts,
    get_upload_worker_count,
    get_upload_worker_profile,
)
from app.services.release_service import current_app_version, latest_release_info, parse_semver
from app.services.upload_task_service import upload_queue_stats
from app.utils import image_process

router = APIRouter(prefix="/system", tags=["system"])


def _dir_stats(path: Path) -> dict:
    count = 0
    size = 0
    exists = path.exists()
    if exists:
        for item in path.rglob("*"):
            if item.is_file():
                count += 1
                size += item.stat().st_size
    return {"path": str(path), "exists": exists, "file_count": count, "size_bytes": size}


def _ffmpeg_info() -> dict:
    executable = shutil.which("ffmpeg")
    if not executable:
        return {"available": False, "path": "", "version": "", "avif_encoder": False, "message": "ffmpeg not found"}
    try:
        version = subprocess.run([executable, "-version"], capture_output=True, text=True, timeout=5)
        encoders = subprocess.run([executable, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=8)
        output = f"{encoders.stdout}\n{encoders.stderr}".lower()
        return {
            "available": True,
            "path": executable,
            "version": (version.stdout.splitlines() or [""])[0],
            "avif_encoder": "libaom-av1" in output or "av1" in output,
            "message": "ok",
        }
    except Exception as exc:
        return {"available": False, "path": executable, "version": "", "avif_encoder": False, "message": str(exc)}


def _database_info(db: Session) -> dict:
    url = make_url(settings.database_url)
    safe_url = url.render_as_string(hide_password=True)
    dialect = engine.dialect.name
    info = {
        "url": safe_url,
        "dialect": dialect,
        "driver": engine.dialect.driver,
        "path": "",
        "exists": True,
        "size_bytes": 0,
        "message": "ok",
        "concurrency": database_concurrency_info(db),
    }
    if dialect == "sqlite":
        database_path = url.database or ""
        db_file = Path(database_path) if database_path else None
        info.update(
            {
                "path": database_path,
                "exists": bool(db_file and db_file.exists()),
                "size_bytes": db_file.stat().st_size if db_file and db_file.exists() else 0,
            }
        )
        return info
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        info["exists"] = False
        info["message"] = str(exc)
    return info


def _migration_info(db: Session) -> dict:
    current = ""
    try:
        current = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar() or ""
    except Exception:
        current = ""
    latest_heads: list[str] = []
    try:
        alembic_config = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(ROOT_DIR / "backend" / "alembic"))
        latest_heads = list(ScriptDirectory.from_config(alembic_config).get_heads())
    except Exception:
        latest_heads = []
    up_to_date = bool(current and latest_heads and current in latest_heads)
    return {
        "current": current,
        "latest": latest_heads[0] if len(latest_heads) == 1 else ", ".join(latest_heads),
        "up_to_date": up_to_date,
        "message": "database schema is up to date" if up_to_date else "database schema migration is pending or unknown",
    }


def _application_info(db: Session) -> dict:
    current_version = current_app_version()
    latest_release = latest_release_info(db)
    current_semver = parse_semver(current_version)
    latest_semver = parse_semver(latest_release.get("version") if latest_release.get("available") else "")
    update_available = bool(current_semver and latest_semver and latest_semver > current_semver)
    migration = _migration_info(db)
    return {
        "current_version": current_version,
        "configured_version": settings.app_version,
        "latest_release": latest_release,
        "update_available": update_available,
        "migration": migration,
    }


@router.get("/health")
def system_health(
    admin: Annotated[dict, Depends(require_system_read)],
    db: Annotated[Session, Depends(get_db)],
):
    database_info = _database_info(db)
    application_info = _application_info(db)
    ffmpeg = _ffmpeg_info()
    imagecodecs_available = image_process.imagecodecs is not None
    jpegxr_available = bool(
        imagecodecs_available and getattr(image_process.imagecodecs, "jpegxr_check", None)
    )
    original_stats = _dir_stats(settings.storage_path / "original")
    preview_stats = _dir_stats(settings.storage_path / "preview")
    thumbnail_stats = _dir_stats(settings.storage_path / "thumbnail")
    image_count = db.scalar(select(func.count(Image.id))) or 0
    hdr_image_count = db.scalar(
        select(func.count(Image.id)).where(Image.dynamic_range == image_process.DYNAMIC_RANGE_HDR)
    ) or 0
    preview_reference_count = db.scalar(
        select(func.count(Image.id)).where(Image.preview_path.is_not(None))
    ) or 0
    legacy_preview_reference_count = db.scalar(
        select(func.count(Image.id)).where(
            Image.preview_path.is_not(None),
            Image.dynamic_range != image_process.DYNAMIC_RANGE_HDR,
        )
    ) or 0
    missing_hdr_preview_reference_count = db.scalar(
        select(func.count(Image.id)).where(
            Image.dynamic_range == image_process.DYNAMIC_RANGE_HDR,
            Image.preview_path.is_(None),
        )
    ) or 0
    expected_preview_count = hdr_image_count
    legacy_preview_file_count = max(0, preview_stats["file_count"] - expected_preview_count)
    cleanup_required = bool(legacy_preview_reference_count or legacy_preview_file_count)
    derivative_counts_match = (
        original_stats["file_count"] == image_count
        and thumbnail_stats["file_count"] == image_count
        and preview_stats["file_count"] == expected_preview_count
        and preview_reference_count == expected_preview_count
        and missing_hdr_preview_reference_count == 0
    )
    if derivative_counts_match:
        consistency_message = "required original, thumbnail, and HDR preview variants are complete"
    elif cleanup_required and not missing_hdr_preview_reference_count:
        consistency_message = "legacy SDR or animated preview files are pending cleanup"
    else:
        consistency_message = "required image variant counts differ from image records"
    worker_profile = get_upload_worker_profile(db)
    return {
        "application": application_info,
        "database": {
            **database_info,
        },
        "storage": {
            "root": str(settings.storage_path),
            "original": original_stats,
            "preview": preview_stats,
            "thumbnail": thumbnail_stats,
            "consistency": {
                "image_records": image_count,
                "hdr_image_records": hdr_image_count,
                "expected": {
                    "original": image_count,
                    "preview": expected_preview_count,
                    "thumbnail": image_count,
                },
                "preview_references": preview_reference_count,
                "missing_hdr_preview_references": missing_hdr_preview_reference_count,
                "legacy_preview_references": legacy_preview_reference_count,
                "legacy_preview_files": legacy_preview_file_count,
                "cleanup_required": cleanup_required,
                "preview_policy": "HDR images require SDR previews; SDR static and animated images use original plus thumbnail.",
                "derivative_counts_match": derivative_counts_match,
                "message": consistency_message,
            },
        },
        "upload_queue": {
            "worker_count": get_upload_worker_count(db),
            "worker_requested": worker_profile["requested"],
            "worker_limit": worker_profile["limit"],
            "database_profile": worker_profile["profile"],
            "claim_batch_size": get_upload_claim_batch_size(db),
            "max_attempts": get_upload_task_max_attempts(db),
            "failed_retention_days": get_upload_failed_retention_days(db),
            **upload_queue_stats(db),
        },
        "media_delivery": {
            "route": "/media/{image_id}/{variant}/{media_version}",
            "mode": "nginx_internal_redirect" if settings.media_accel_redirect_prefix else "application_file_response",
            "accel_redirect_enabled": bool(settings.media_accel_redirect_prefix),
            "accel_redirect_prefix": settings.media_accel_redirect_prefix,
            "public_browser_cache_seconds": settings.media_public_browser_cache_seconds,
            "public_shared_cache_seconds": settings.media_public_shared_cache_seconds,
            "private_cache_control": "private, no-store, max-age=0",
        },
        "security": {
            "auth_secret": auth_secret_health(settings.auth_secret),
        },
        "capabilities": {
            "ffmpeg": ffmpeg,
            "jxr_decode": {
                "available": jpegxr_available,
                "message": "imagecodecs jpegxr support available" if jpegxr_available else "imagecodecs jpegxr support missing",
            },
            "hdr_avif_metadata_patch": {
                "available": all(
                    hasattr(image_process, name)
                    for name in ("_patch_avif_hdr_boxes", "_build_mdcv_box", "_build_clli_box")
                ),
                "message": "mdcv/clli patch functions available",
            },
        },
    }
