import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import AppSetting, Image
from app.schemas.settings import AdminSettingsRead, AdminSettingsUpdate, PublicSettingsRead
from app.services.app_setting_service import (
    UPLOAD_CLAIM_BATCH_SIZE_KEY,
    UPLOAD_WORKER_COUNT_KEY,
    get_upload_claim_batch_size,
    get_upload_worker_count,
)
from app.services.admin_account_service import get_admin_account, update_admin_account
from app.services.auth_session_service import clear_admin_session_cookie, rotate_auth_secret
from app.services.upload_task_service import start_upload_worker

router = APIRouter(prefix="/settings", tags=["settings"])

IMAGE_MANAGE_VIEW_MODE_KEY = "admin.image_manage_view_mode"
HOME_SLIDESHOW_IMAGE_IDS_KEY = "public.home_slideshow_image_ids"
HOME_HERO_IMAGE_ID_KEY = "public.home_hero_image_id"
WORKS_HERO_IMAGE_ID_KEY = "public.works_hero_image_id"
CHARACTERS_HERO_IMAGE_ID_KEY = "public.characters_hero_image_id"
RATINGS_HERO_IMAGE_ID_KEY = "public.ratings_hero_image_id"
DEFAULT_IMAGE_MANAGE_VIEW_MODE = "classic"
VALID_IMAGE_MANAGE_VIEW_MODES = {"classic", "waterfall"}
MAX_HOME_SLIDESHOW_IMAGES = 24
PUBLIC_HERO_IMAGE_SETTINGS = {
    "home_hero": HOME_HERO_IMAGE_ID_KEY,
    "works_hero": WORKS_HERO_IMAGE_ID_KEY,
    "characters_hero": CHARACTERS_HERO_IMAGE_ID_KEY,
    "ratings_hero": RATINGS_HERO_IMAGE_ID_KEY,
}


def _normalize_image_manage_view_mode(value: str | None) -> str:
    return value if value in VALID_IMAGE_MANAGE_VIEW_MODES else DEFAULT_IMAGE_MANAGE_VIEW_MODE


def _get_value(db: Session, key: str, default: str) -> str:
    setting = db.get(AppSetting, key)
    return _normalize_image_manage_view_mode(setting.value if setting else default)


def _set_value(db: Session, key: str, value: str) -> None:
    setting = db.get(AppSetting, key)
    if setting:
        setting.value = value
        return
    db.add(AppSetting(key=key, value=value))


def _delete_value(db: Session, key: str) -> None:
    setting = db.get(AppSetting, key)
    if setting:
        db.delete(setting)


def _read_image_setting(db: Session, key: str) -> tuple[int | None, Image | None]:
    setting = db.get(AppSetting, key)
    if not setting:
        return None, None
    try:
        image_id = int(setting.value)
    except ValueError:
        return None, None
    image = db.get(Image, image_id)
    if not image:
        return None, None
    return image_id, image


def _set_image_setting(db: Session, key: str, image_id: int | None) -> None:
    if image_id is None:
        _delete_value(db, key)
        return
    if not db.get(Image, image_id):
        raise HTTPException(status_code=422, detail=f"Image {image_id} not found")
    _set_value(db, key, str(image_id))


def _normalize_image_id_list(image_ids: list[int] | None) -> list[int]:
    result: list[int] = []
    for image_id in image_ids or []:
        value = int(image_id)
        if value < 1:
            raise ValueError("Image id must be greater than 0")
        if value not in result:
            result.append(value)
    if len(result) > MAX_HOME_SLIDESHOW_IMAGES:
        raise ValueError(f"Home slideshow supports at most {MAX_HOME_SLIDESHOW_IMAGES} images")
    return result


def _read_image_list_setting(db: Session, key: str, public_only: bool = False) -> tuple[list[int], list[Image]]:
    setting = db.get(AppSetting, key)
    if not setting:
        return [], []
    try:
        value = json.loads(setting.value)
        image_ids = value if isinstance(value, list) else []
    except json.JSONDecodeError:
        image_ids = [item.strip() for item in setting.value.split(",") if item.strip()]
    try:
        normalized_ids = _normalize_image_id_list([int(image_id) for image_id in image_ids])
    except (TypeError, ValueError):
        return [], []
    if not normalized_ids:
        return [], []
    stmt = select(Image).where(Image.id.in_(normalized_ids))
    if public_only:
        stmt = stmt.where(Image.is_public.is_(True), Image.rating != "hidden")
    images = db.scalars(stmt).all()
    image_by_id = {image.id: image for image in images}
    ordered_images = [image_by_id[image_id] for image_id in normalized_ids if image_id in image_by_id]
    return [image.id for image in ordered_images], ordered_images


def _set_image_list_setting(db: Session, key: str, image_ids: list[int] | None) -> None:
    normalized_ids = _normalize_image_id_list(image_ids)
    if not normalized_ids:
        _delete_value(db, key)
        return
    existing_ids = set(db.scalars(select(Image.id).where(Image.id.in_(normalized_ids))).all())
    missing_ids = [image_id for image_id in normalized_ids if image_id not in existing_ids]
    if missing_ids:
        raise HTTPException(status_code=422, detail=f"Image {missing_ids[0]} not found")
    _set_value(db, key, json.dumps(normalized_ids, separators=(",", ":")))


def _read_public_settings(db: Session) -> dict[str, object]:
    result: dict[str, object] = {}
    for prefix, key in PUBLIC_HERO_IMAGE_SETTINGS.items():
        image_id, image = _read_image_setting(db, key)
        result[f"{prefix}_image_id"] = image_id
        result[f"{prefix}_image"] = image
    slideshow_image_ids, slideshow_images = _read_image_list_setting(
        db,
        HOME_SLIDESHOW_IMAGE_IDS_KEY,
        public_only=True,
    )
    result["home_slideshow_image_ids"] = slideshow_image_ids
    result["home_slideshow_images"] = slideshow_images
    return result


def _read_settings(db: Session) -> dict[str, object]:
    account = get_admin_account(db)
    slideshow_image_ids, slideshow_images = _read_image_list_setting(db, HOME_SLIDESHOW_IMAGE_IDS_KEY)
    return {
        "image_manage_view_mode": _get_value(
            db,
            IMAGE_MANAGE_VIEW_MODE_KEY,
            DEFAULT_IMAGE_MANAGE_VIEW_MODE,
        ),
        "upload_worker_count": get_upload_worker_count(db),
        "upload_claim_batch_size": get_upload_claim_batch_size(db),
        "admin_username": account.username,
        "admin_avatar_image_id": account.avatar_image_id,
        "admin_avatar_image": account.avatar_image,
        **_read_public_settings(db),
        "home_slideshow_image_ids": slideshow_image_ids,
        "home_slideshow_images": slideshow_images,
    }


@router.get("", response_model=AdminSettingsRead)
def read_settings(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_admin)],
):
    return _read_settings(db)


@router.get("/public", response_model=PublicSettingsRead)
def read_public_settings(
    db: Annotated[Session, Depends(get_db)],
):
    return _read_public_settings(db)


@router.put("", response_model=AdminSettingsRead)
def update_settings(
    payload: AdminSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_admin)],
):
    data = payload.model_dump(exclude_unset=True)
    if data.get("image_manage_view_mode") is not None:
        _set_value(db, IMAGE_MANAGE_VIEW_MODE_KEY, data["image_manage_view_mode"])
    if data.get("upload_worker_count") is not None:
        _set_value(db, UPLOAD_WORKER_COUNT_KEY, str(data["upload_worker_count"]))
    if data.get("upload_claim_batch_size") is not None:
        _set_value(db, UPLOAD_CLAIM_BATCH_SIZE_KEY, str(data["upload_claim_batch_size"]))
    try:
        if "home_slideshow_image_ids" in data:
            _set_image_list_setting(db, HOME_SLIDESHOW_IMAGE_IDS_KEY, data.get("home_slideshow_image_ids"))
        for prefix, key in PUBLIC_HERO_IMAGE_SETTINGS.items():
            id_field = f"{prefix}_image_id"
            clear_field = f"clear_{prefix}_image"
            if id_field in data or data.get(clear_field):
                _set_image_setting(
                    db,
                    key,
                    None if data.get(clear_field) else data.get(id_field),
                )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if (
        data.get("admin_username") is not None
        or data.get("admin_password") is not None
        or data.get("admin_avatar_image_id") is not None
        or data.get("clear_admin_avatar")
    ):
        try:
            update_admin_account(
                db,
                username=data.get("admin_username"),
                password=data.get("admin_password"),
                avatar_image_id=data.get("admin_avatar_image_id"),
                clear_avatar=bool(data.get("clear_admin_avatar")),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    if data.get("upload_worker_count") is not None or data.get("upload_claim_batch_size") is not None:
        start_upload_worker()
    return _read_settings(db)


@router.post("/auth-secret/rotate")
def rotate_admin_auth_secret(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_admin)],
):
    result = rotate_auth_secret(db)
    db.commit()
    clear_admin_session_cookie(response)
    return result
