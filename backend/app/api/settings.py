import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_api_keys_manage, require_settings_manage
from app.database import get_db
from app.models import AppSetting, Image
from app.schemas.settings import (
    AdminSettingsRead,
    AdminSettingsUpdate,
    ApiKeyCreate,
    ApiKeyRead,
    ApiKeyUpdate,
    PublicSettingsRead,
)
from app.services.app_setting_service import (
    GITHUB_RELEASE_PROXY_URL_KEY,
    RANDOM_API_DEFAULT_RATING_KEY,
    RANDOM_API_DEFAULT_VARIANT_KEY,
    RANDOM_API_DESKTOP_ORIENTATION_KEY,
    RANDOM_API_MOBILE_ORIENTATION_KEY,
    UPLOAD_CLAIM_BATCH_SIZE_KEY,
    UPLOAD_TASK_FAILED_RETENTION_DAYS_KEY,
    UPLOAD_TASK_MAX_ATTEMPTS_KEY,
    UPLOAD_WORKER_COUNT_KEY,
    get_github_release_proxy_url,
    get_random_api_defaults,
    get_upload_claim_batch_size,
    get_upload_failed_retention_days,
    get_upload_task_max_attempts,
    get_upload_worker_count,
    get_upload_worker_profile,
    upload_worker_limit_for_dialect,
    normalize_github_release_proxy_url,
)
from app.services.admin_account_service import get_admin_account, update_admin_account
from app.services.auth_session_service import clear_admin_session_cookie, rotate_auth_secret
from app.services.cdn_warm_service import enqueue_home_images, start_cdn_warm_worker
from app.services.api_key_service import (
    api_key_scope_catalog,
    create_api_key,
    list_configured_api_keys,
    reset_api_keys,
    revoke_api_key,
    rotate_api_key,
    update_api_key_policy,
)
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
MAX_HOME_SLIDESHOW_IMAGES = 48
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
    return setting.value if setting else default


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


def _is_public_image(image: Image) -> bool:
    return bool(image.is_public and image.rating != "hidden")


def _read_image_setting(
    db: Session,
    key: str,
    *,
    public_only: bool = False,
) -> tuple[int | None, Image | None]:
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
    if public_only and not _is_public_image(image):
        return None, None
    return image_id, image


def _set_image_setting(
    db: Session,
    key: str,
    image_id: int | None,
    *,
    public_only: bool = False,
) -> None:
    if image_id is None:
        _delete_value(db, key)
        return
    image = db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=422, detail=f"Image {image_id} not found")
    if public_only and not _is_public_image(image):
        raise HTTPException(status_code=422, detail=f"Image {image_id} is not available to the public")
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


def _set_image_list_setting(
    db: Session,
    key: str,
    image_ids: list[int] | None,
    *,
    public_only: bool = False,
) -> None:
    normalized_ids = _normalize_image_id_list(image_ids)
    if not normalized_ids:
        _delete_value(db, key)
        return
    images = db.scalars(select(Image).where(Image.id.in_(normalized_ids))).all()
    image_by_id = {image.id: image for image in images}
    existing_ids = set(image_by_id)
    missing_ids = [image_id for image_id in normalized_ids if image_id not in existing_ids]
    if missing_ids:
        raise HTTPException(status_code=422, detail=f"Image {missing_ids[0]} not found")
    if public_only:
        unavailable_ids = [image_id for image_id in normalized_ids if not _is_public_image(image_by_id[image_id])]
        if unavailable_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Image {unavailable_ids[0]} is not available to the public",
            )
    _set_value(db, key, json.dumps(normalized_ids, separators=(",", ":")))


def _read_hero_settings(db: Session, *, public_only: bool) -> dict[str, object]:
    result: dict[str, object] = {}
    for prefix, key in PUBLIC_HERO_IMAGE_SETTINGS.items():
        image_id, image = _read_image_setting(db, key, public_only=public_only)
        result[f"{prefix}_image_id"] = image_id
        result[f"{prefix}_image"] = image
    return result


def _read_public_settings(db: Session) -> dict[str, object]:
    result = _read_hero_settings(db, public_only=True)
    slideshow_image_ids, slideshow_images = _read_image_list_setting(
        db,
        HOME_SLIDESHOW_IMAGE_IDS_KEY,
        public_only=True,
    )
    result["home_slideshow_image_ids"] = slideshow_image_ids
    result["home_slideshow_images"] = slideshow_images
    return result


def _read_settings(db: Session, *, include_api_keys: bool = True) -> dict[str, object]:
    account = get_admin_account(db)
    slideshow_image_ids, slideshow_images = _read_image_list_setting(db, HOME_SLIDESHOW_IMAGE_IDS_KEY)
    random_api_defaults = get_random_api_defaults(db)
    worker_profile = get_upload_worker_profile(db)
    return {
        "image_manage_view_mode": _normalize_image_manage_view_mode(
            _get_value(
                db,
                IMAGE_MANAGE_VIEW_MODE_KEY,
                DEFAULT_IMAGE_MANAGE_VIEW_MODE,
            )
        ),
        "random_api_desktop_orientation": random_api_defaults["desktop_orientation"],
        "random_api_mobile_orientation": random_api_defaults["mobile_orientation"],
        "random_api_default_rating": random_api_defaults["rating"],
        "random_api_default_variant": random_api_defaults["variant"],
        "github_proxy_url": get_github_release_proxy_url(db),
        "upload_worker_count": get_upload_worker_count(db),
        "upload_worker_limit": worker_profile["limit"],
        "database_concurrency_profile": worker_profile["profile"],
        "upload_claim_batch_size": get_upload_claim_batch_size(db),
        "upload_task_max_attempts": get_upload_task_max_attempts(db),
        "upload_failed_retention_days": get_upload_failed_retention_days(db),
        "admin_username": account.username,
        "admin_nickname": account.nickname,
        "admin_avatar_image_id": account.avatar_image_id,
        "admin_avatar_image": account.avatar_image,
        "admin_password_change_required": account.password_change_required,
        "operations_api_keys": list_configured_api_keys(db) if include_api_keys else [],
        "api_key_scopes": api_key_scope_catalog(),
        **_read_hero_settings(db, public_only=False),
        "home_slideshow_image_ids": slideshow_image_ids,
        "home_slideshow_images": slideshow_images,
    }


@router.get("", response_model=AdminSettingsRead)
def read_settings(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_settings_manage)],
):
    include_api_keys = admin.get("auth_type") != "api_key" or "api_keys:manage" in admin.get("api_key_scopes", [])
    return _read_settings(db, include_api_keys=include_api_keys)


@router.get("/public", response_model=PublicSettingsRead)
def read_public_settings(
    db: Annotated[Session, Depends(get_db)],
):
    return _read_public_settings(db)


@router.put("", response_model=AdminSettingsRead)
def update_settings(
    payload: AdminSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_settings_manage)],
):
    data = payload.model_dump(exclude_unset=True)
    if data.get("image_manage_view_mode") is not None:
        _set_value(db, IMAGE_MANAGE_VIEW_MODE_KEY, data["image_manage_view_mode"])
    random_api_setting_fields = {
        "random_api_desktop_orientation": RANDOM_API_DESKTOP_ORIENTATION_KEY,
        "random_api_mobile_orientation": RANDOM_API_MOBILE_ORIENTATION_KEY,
        "random_api_default_rating": RANDOM_API_DEFAULT_RATING_KEY,
        "random_api_default_variant": RANDOM_API_DEFAULT_VARIANT_KEY,
    }
    for field, key in random_api_setting_fields.items():
        if data.get(field) is not None:
            _set_value(db, key, data[field])
    if data.get("upload_worker_count") is not None:
        worker_limit = upload_worker_limit_for_dialect(db.get_bind().dialect.name)
        if data["upload_worker_count"] > worker_limit:
            raise HTTPException(
                status_code=422,
                detail=f"当前数据库模式的处理 worker 上限为 {worker_limit}",
            )
        _set_value(db, UPLOAD_WORKER_COUNT_KEY, str(data["upload_worker_count"]))
    if data.get("upload_claim_batch_size") is not None:
        _set_value(db, UPLOAD_CLAIM_BATCH_SIZE_KEY, str(data["upload_claim_batch_size"]))
    if data.get("upload_task_max_attempts") is not None:
        _set_value(db, UPLOAD_TASK_MAX_ATTEMPTS_KEY, str(data["upload_task_max_attempts"]))
    if data.get("upload_failed_retention_days") is not None:
        _set_value(db, UPLOAD_TASK_FAILED_RETENTION_DAYS_KEY, str(data["upload_failed_retention_days"]))
    if data.get("github_proxy_url") is not None:
        try:
            github_proxy_url = normalize_github_release_proxy_url(data["github_proxy_url"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if github_proxy_url:
            _set_value(db, GITHUB_RELEASE_PROXY_URL_KEY, github_proxy_url)
        else:
            _delete_value(db, GITHUB_RELEASE_PROXY_URL_KEY)
    try:
        if "home_slideshow_image_ids" in data:
            _set_image_list_setting(
                db,
                HOME_SLIDESHOW_IMAGE_IDS_KEY,
                data.get("home_slideshow_image_ids"),
                public_only=True,
            )
        for prefix, key in PUBLIC_HERO_IMAGE_SETTINGS.items():
            id_field = f"{prefix}_image_id"
            clear_field = f"clear_{prefix}_image"
            if id_field in data or data.get(clear_field):
                _set_image_setting(
                    db,
                    key,
                    None if data.get(clear_field) else data.get(id_field),
                    public_only=True,
                )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if (
        data.get("admin_username") is not None
        or data.get("admin_nickname") is not None
        or data.get("admin_password") is not None
        or data.get("admin_avatar_image_id") is not None
        or data.get("clear_admin_avatar")
    ):
        try:
            update_admin_account(
                db,
                username=data.get("admin_username"),
                nickname=data.get("admin_nickname"),
                password=data.get("admin_password"),
                avatar_image_id=data.get("admin_avatar_image_id"),
                clear_avatar=bool(data.get("clear_admin_avatar")),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    warm_queued = 0
    try:
        if "home_slideshow_image_ids" in data:
            _ids, images = _read_image_list_setting(db, HOME_SLIDESHOW_IMAGE_IDS_KEY, public_only=True)
            warm_queued += enqueue_home_images(db, images)
        for prefix, key in PUBLIC_HERO_IMAGE_SETTINGS.items():
            id_field = f"{prefix}_image_id"
            if id_field in data:
                _image_id, image = _read_image_setting(db, key, public_only=True)
                if image:
                    warm_queued += enqueue_home_images(db, [image])
        db.commit()
    except Exception:
        db.rollback()
    if warm_queued:
        start_cdn_warm_worker()
    if data.get("upload_worker_count") is not None or data.get("upload_claim_batch_size") is not None:
        start_upload_worker()
    include_api_keys = admin.get("auth_type") != "api_key" or "api_keys:manage" in admin.get("api_key_scopes", [])
    return _read_settings(db, include_api_keys=include_api_keys)


@router.post("/auth-secret/rotate")
def rotate_admin_auth_secret(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_settings_manage)],
):
    result = rotate_auth_secret(db)
    db.commit()
    clear_admin_session_cookie(response)
    return result


@router.post("/api-keys/reset", response_model=AdminSettingsRead)
def reset_operations_api_keys(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_api_keys_manage)],
):
    reset_api_keys(db)
    return _read_settings(db)


@router.get("/api-keys", response_model=list[ApiKeyRead])
def read_operations_api_keys(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_api_keys_manage)],
):
    return list_configured_api_keys(db)


@router.post("/api-keys", response_model=ApiKeyRead, status_code=status.HTTP_201_CREATED)
def add_operations_api_key(
    payload: ApiKeyCreate,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_api_keys_manage)],
):
    try:
        return create_api_key(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/api-keys/{key_id}", response_model=ApiKeyRead)
def edit_operations_api_key(
    key_id: int,
    payload: ApiKeyUpdate,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_api_keys_manage)],
):
    try:
        result = update_api_key_policy(db, key_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="API Key not found")
    return result


@router.post("/api-keys/{key_id}/rotate", response_model=ApiKeyRead)
def rotate_operations_api_key(
    key_id: int,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_api_keys_manage)],
):
    result = rotate_api_key(db, key_id)
    if result is None:
        raise HTTPException(status_code=404, detail="API Key not found")
    return result


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_operations_api_key(
    key_id: int,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_api_keys_manage)],
):
    if not revoke_api_key(db, key_id):
        raise HTTPException(status_code=404, detail="API Key not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
