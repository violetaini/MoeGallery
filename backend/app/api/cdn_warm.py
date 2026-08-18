from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_settings_manage
from app.database import get_db
from app.models import Image
from app.schemas.cdn_warm import CdnWarmConfigRead, CdnWarmConfigUpdate, CdnWarmProbeRead, CdnWarmSeedResult, CdnWarmStatusRead
from app.services.cdn_warm_service import (
    cdn_warm_stats,
    enqueue_public_images,
    get_cdn_warm_config,
    probe_cdn,
    seed_existing_public_thumbnails,
    start_cdn_warm_worker,
    stop_cdn_warm_worker,
    update_cdn_warm_config,
)

router = APIRouter(prefix="/cdn-warm", tags=["cdn-warm"])


def _is_public_image(image: Image) -> bool:
    return bool(image.is_public and image.rating != "hidden")


@router.get("", response_model=CdnWarmStatusRead)
def read_cdn_warm_status(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_settings_manage)],
):
    return {"config": get_cdn_warm_config(db), **cdn_warm_stats(db)}


@router.put("/config", response_model=CdnWarmConfigRead)
def save_cdn_warm_config(
    payload: CdnWarmConfigUpdate,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_settings_manage)],
):
    try:
        previous_config = get_cdn_warm_config(db)
        config = update_cdn_warm_config(db, **payload.model_dump())
        if config["enabled"]:
            probe = probe_cdn(str(config["base_url"]))
            if not probe["detected"]:
                raise ValueError(str(probe["message"]))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    if config["enabled"]:
        if not previous_config["enabled"]:
            seed_existing_public_thumbnails(db)
            db.commit()
        start_cdn_warm_worker()
    else:
        stop_cdn_warm_worker()
    return config


@router.post("/probe", response_model=CdnWarmProbeRead)
def probe_configured_cdn(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_settings_manage)],
):
    config = get_cdn_warm_config(db)
    if not config["valid"]:
        raise HTTPException(status_code=422, detail=str(config["validation_message"] or "请先配置 HTTPS CDN 域名"))
    try:
        return probe_cdn(str(config["base_url"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/seed-thumbnails", response_model=CdnWarmSeedResult)
def seed_public_thumbnails(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_settings_manage)],
):
    config = get_cdn_warm_config(db)
    if not config["enabled"] or not config["valid"]:
        raise HTTPException(status_code=422, detail="请先启用并验证 CDN 预热域名")
    result = seed_existing_public_thumbnails(db)
    db.commit()
    if result["queued"] or result["retried"]:
        start_cdn_warm_worker()
    return result
