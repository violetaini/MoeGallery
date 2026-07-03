import shutil
import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from app.auth import require_admin
from app.config import auth_secret_health, settings
from app.database import engine, get_db
from app.models import Image
from app.services.app_setting_service import get_upload_claim_batch_size, get_upload_worker_count
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


@router.get("/health")
def system_health(
    admin: Annotated[dict, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    database_info = _database_info(db)
    ffmpeg = _ffmpeg_info()
    imagecodecs_available = image_process.imagecodecs is not None
    jpegxr_available = bool(
        imagecodecs_available and getattr(image_process.imagecodecs, "jpegxr_check", None)
    )
    original_stats = _dir_stats(settings.storage_path / "original")
    preview_stats = _dir_stats(settings.storage_path / "preview")
    thumbnail_stats = _dir_stats(settings.storage_path / "thumbnail")
    image_count = db.scalar(select(func.count(Image.id))) or 0
    derivative_counts_match = (
        original_stats["file_count"] == preview_stats["file_count"] == thumbnail_stats["file_count"] == image_count
    )
    return {
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
                "derivative_counts_match": derivative_counts_match,
                "message": "original/preview/thumbnail counts match image records"
                if derivative_counts_match
                else "storage directory counts differ from image records",
            },
        },
        "upload_queue": {
            "worker_count": get_upload_worker_count(db),
            "claim_batch_size": get_upload_claim_batch_size(db),
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
