import random
from typing import Annotated
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import case, desc, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.api.helpers import (
    LIKE_ESCAPE,
    contains_like_pattern,
    non_structural_image_conditions,
    parse_id_csv,
    validate_relation_ids,
)
from app.auth import (
    optional_admin,
    require_library_delete,
    require_library_write,
    require_uploads_manage,
)
from app.config import settings
from app.database import get_db
from app.models import Character, Image, Work
from app.schemas.image import (
    ImageBatchDelete,
    ImageBatchResult,
    ImageBatchUpdate,
    ImageListResponse,
    ImageRead,
    RandomImageResponse,
    ImageUpdate,
    ImageUploadResponse,
    ImageUploadResult,
)
from app.services.image_service import ImageService
from app.services.app_setting_service import get_random_api_defaults
from app.services.media_delivery_service import build_media_url, resolve_media_variant, rotate_media_version
from app.services.storage_service import delete_storage_file, resolve_storage_file
from app.utils.hash import sha256_bytes
from app.utils.image_process import InvalidImageError, inspect_image, render_webp_preview_bytes, validate_upload_filename
from app.utils.urls import normalize_http_url

router = APIRouter(prefix="/images", tags=["images"])
RANDOM_SORT_MODULUS = 2_147_483_647


def _filename_extension(filename: str | None) -> str:
    suffix = PurePath(filename or "").suffix
    return suffix.lower()


def _validate_original_filename_extension(current: str | None, next_value: str | None) -> None:
    if next_value is None:
        return
    current_extension = _filename_extension(current)
    next_extension = _filename_extension(next_value)
    if current_extension and next_extension != current_extension:
        raise HTTPException(status_code=400, detail=f"文件后缀必须保持为 {current_extension}")
    if not current_extension and next_extension:
        raise HTTPException(status_code=400, detail="原文件没有后缀，不能新增后缀")


def _image_options():
    return (
        selectinload(Image.works),
        selectinload(Image.characters),
        selectinload(Image.tags),
    )


def _character_name_filter(value: str):
    needle = contains_like_pattern(value)
    return or_(
        Character.name.ilike(needle, escape=LIKE_ESCAPE),
        Character.original_name.ilike(needle, escape=LIKE_ESCAPE),
        Character.aliases.ilike(needle, escape=LIKE_ESCAPE),
    )


def _random_sort_expression(seed: int):
    multiplier = ((seed * 1_103_515_245 + 12_345) % (RANDOM_SORT_MODULUS - 1)) + 1
    offset = (seed * 1_013_904_223 + 1_013_904_223) % RANDOM_SORT_MODULUS
    return (Image.id * multiplier + offset) % RANDOM_SORT_MODULUS


def _random_image_candidates(db: Session, stmt, limit: int = 32) -> list[Image]:
    max_id = db.scalar(select(func.max(Image.id)))
    if max_id is None:
        return []

    pivot = random.randint(1, int(max_id))
    candidates = db.scalars(
        stmt.where(Image.id >= pivot).order_by(Image.id.asc()).limit(limit)
    ).unique().all()
    if len(candidates) < limit:
        candidates.extend(
            db.scalars(
                stmt.where(Image.id < pivot).order_by(Image.id.asc()).limit(limit - len(candidates))
            ).unique().all()
        )
    random.shuffle(candidates)
    return candidates


def _detect_random_api_device(request: Request, requested_device: str) -> str:
    if requested_device != "auto":
        return requested_device

    client_hint = request.headers.get("sec-ch-ua-mobile", "").strip()
    if client_hint == "?1":
        return "mobile"
    if client_hint == "?0":
        return "pc"

    user_agent = request.headers.get("user-agent", "").lower()
    mobile_markers = (
        "android",
        "iphone",
        "ipad",
        "ipod",
        "mobile",
        "windows phone",
        "opera mini",
        "opera mobi",
    )
    return "mobile" if any(marker in user_agent for marker in mobile_markers) else "pc"


def _random_image_asset(image: Image, requested_variant: str) -> tuple[str, str]:
    try:
        path, served_variant = resolve_media_variant(image, requested_variant)
        target = resolve_storage_file(path)
    except ValueError as exc:
        raise FileNotFoundError from exc
    if not target.is_file():
        raise FileNotFoundError
    return path, served_variant


def _rotate_media_version_if_access_changes(image: Image, data: dict) -> None:
    if any(key in data and getattr(image, key) != data[key] for key in ("rating", "is_public")):
        rotate_media_version(image)


def _update_public_image_counter(db: Session, image_id: int, values: dict) -> Image:
    result = db.execute(
        update(Image)
        .where(Image.id == image_id, Image.is_public.is_(True), Image.rating != "hidden")
        .values(values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=404, detail="Image not found")
    db.commit()
    image = db.scalar(select(Image).options(*_image_options()).where(Image.id == image_id))
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


@router.get(
    "/random",
    response_model=RandomImageResponse,
    responses={
        307: {"description": "重定向到随机选中的原图、预览图或缩略图。"},
        404: {"description": "没有符合筛选条件且文件可用的公开图片。"},
    },
)
def random_image(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    work_id: int | None = Query(None, ge=1),
    character_id: int | None = Query(None, ge=1),
    character: str | None = Query(None, min_length=1, max_length=255),
    rating: str | None = Query(None, pattern="^(safe|sensitive|any)$"),
    orientation: str | None = Query(None, pattern="^(landscape|portrait|square|any)$"),
    device: str = Query("auto", pattern="^(auto|pc|mobile)$"),
    variant: str | None = Query(None, pattern="^(original|preview|thumbnail)$"),
    response_type: str = Query("redirect", alias="response", pattern="^(redirect|json)$"),
):
    defaults = get_random_api_defaults(db)
    resolved_device = _detect_random_api_device(request, device)
    orientation_default = "mobile_orientation" if resolved_device == "mobile" else "desktop_orientation"
    applied_orientation = orientation or defaults[orientation_default]
    applied_rating = rating or defaults["rating"]
    requested_variant = variant or defaults["variant"]

    stmt = select(Image).options(*_image_options()).where(
        Image.is_public.is_(True),
        Image.rating.in_(("safe", "sensitive")),
        *non_structural_image_conditions(),
    )
    if work_id is not None:
        stmt = stmt.where(Image.works.any(Work.id == work_id))
    if character_id is not None:
        stmt = stmt.where(Image.characters.any(Character.id == character_id))
    if character and character.strip():
        stmt = stmt.where(Image.characters.any(_character_name_filter(character)))
    if applied_rating != "any":
        stmt = stmt.where(Image.rating == applied_rating)
    if applied_orientation != "any":
        stmt = stmt.where(Image.orientation == applied_orientation)

    selected_image = None
    selected_path = None
    served_variant = None
    checked_ids: set[int] = set()
    for _ in range(3):
        for candidate in _random_image_candidates(db, stmt):
            if candidate.id in checked_ids:
                continue
            checked_ids.add(candidate.id)
            try:
                selected_path, served_variant = _random_image_asset(candidate, requested_variant)
            except FileNotFoundError:
                continue
            selected_image = candidate
            break
        if selected_image:
            break

    if not selected_image or not selected_path or not served_variant:
        raise HTTPException(status_code=404, detail="No public image matches the random image filters")

    image_url = build_media_url(selected_image, served_variant)
    headers = {
        "Cache-Control": "no-store, max-age=0",
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Pragma": "no-cache",
        "Vary": "User-Agent, Sec-CH-UA-Mobile",
    }
    if response_type == "redirect":
        return RedirectResponse(url=image_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers=headers)

    for name, value in headers.items():
        response.headers[name] = value
    return {
        "image": selected_image,
        "image_url": image_url,
        "requested_variant": requested_variant,
        "served_variant": served_variant,
        "resolved_device": resolved_device,
        "applied_orientation": applied_orientation,
        "applied_rating": applied_rating,
    }


@router.get("", response_model=ImageListResponse)
def list_images(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    work_id: int | None = None,
    character_id: int | None = None,
    character: str | None = Query(None, min_length=1, max_length=255),
    rating: str | None = Query(None, pattern="^(safe|sensitive|hidden)$"),
    orientation: str | None = Query(None, pattern="^(landscape|portrait|square)$"),
    q: str | None = Query(None, max_length=255),
    sort: str = Query("latest", pattern="^(latest|random|favorites|resolution)$"),
    random_seed: int | None = Query(None, ge=1, le=RANDOM_SORT_MODULUS - 1),
    public_only: bool = True,
    exclude_work_related: bool = False,
    exclude_character_related: bool = False,
    require_work_related: bool = False,
    require_character_related: bool = False,
    exclude_cover_images: bool = False,
    exclude_backdrop_images: bool = False,
    exclude_avatar_images: bool = False,
):
    if not public_only and not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    stmt = select(Image).options(*_image_options())
    if public_only:
        stmt = stmt.where(Image.is_public.is_(True), Image.rating != "hidden")
    if exclude_work_related:
        stmt = stmt.where(~Image.works.any())
    if exclude_character_related:
        stmt = stmt.where(~Image.characters.any())
    if require_work_related:
        stmt = stmt.where(Image.works.any())
    if require_character_related:
        stmt = stmt.where(Image.characters.any())
    if exclude_cover_images or exclude_backdrop_images or exclude_avatar_images:
        cover_condition, backdrop_condition, avatar_condition = non_structural_image_conditions()
        if exclude_cover_images:
            stmt = stmt.where(cover_condition)
        if exclude_backdrop_images:
            stmt = stmt.where(backdrop_condition)
        if exclude_avatar_images:
            stmt = stmt.where(avatar_condition)
    if work_id:
        stmt = stmt.join(Image.works).where(Work.id == work_id)
    if character_id:
        stmt = stmt.join(Image.characters).where(Character.id == character_id)
    if character and character.strip():
        stmt = stmt.where(Image.characters.any(_character_name_filter(character)))
    if rating:
        stmt = stmt.where(Image.rating == rating)
    if orientation:
        stmt = stmt.where(Image.orientation == orientation)
    if q and q.strip():
        needle = contains_like_pattern(q)
        stmt = stmt.where(
            or_(
                Image.filename.ilike(needle, escape=LIKE_ESCAPE),
                Image.original_filename.ilike(needle, escape=LIKE_ESCAPE),
                Image.artist_name.ilike(needle, escape=LIKE_ESCAPE),
                Image.source_url.ilike(needle, escape=LIKE_ESCAPE),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0

    if sort == "random":
        random_seed = random_seed or random.randint(1, RANDOM_SORT_MODULUS - 1)
        stmt = stmt.order_by(_random_sort_expression(random_seed).asc(), Image.id.asc())
    elif sort == "favorites":
        stmt = stmt.order_by(desc(Image.favorite_count), desc(Image.created_at), desc(Image.id))
    elif sort == "resolution":
        stmt = stmt.order_by(desc(Image.width * Image.height), desc(Image.created_at), desc(Image.id))
    else:
        stmt = stmt.order_by(desc(Image.created_at), desc(Image.id))

    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "random_seed": random_seed if sort == "random" else None,
    }


@router.post("/upload", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_images(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_uploads_manage)],
    files: Annotated[list[UploadFile], File()],
    work_ids: str | None = Form(None),
    character_ids: str | None = Form(None),
    rating: str = Form("safe"),
    is_public: bool = Form(True),
    source_url: str | None = Form(None),
    artist_name: str | None = Form(None),
    merge_duplicate_relations: bool = Form(False),
):
    if rating not in {"safe", "sensitive", "hidden"}:
        raise HTTPException(status_code=422, detail="rating must be safe, sensitive, or hidden")

    try:
        source_url = normalize_http_url(source_url)
        parsed_work_ids = parse_id_csv(work_ids)
        parsed_character_ids = parse_id_csv(character_ids)
        validate_relation_ids(db, parsed_work_ids, parsed_character_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    prepared: list[dict] = []
    for upload in files:
        try:
            validate_upload_filename(upload.filename)
            data = await upload.read()
            if not data:
                raise InvalidImageError("Empty upload")
            if len(data) > settings.max_upload_size:
                raise InvalidImageError("File is larger than configured upload limit")
            prepared.append(
                {
                    "upload": upload,
                    "sha256": sha256_bytes(data),
                    "inspection": inspect_image(data),
                }
            )
            await upload.seek(0)
        except (ValueError, InvalidImageError) as exc:
            raise HTTPException(status_code=400, detail=f"{upload.filename}: {exc}") from exc

    service = ImageService(db)
    created_paths: list[str | None] = []
    uploaded: list[tuple[Image, bool]] = []
    try:
        for item in prepared:
            upload = item["upload"]
            data = await upload.read()
            image, duplicate = service.create_from_bytes(
                data=data,
                original_filename=upload.filename,
                content_type=upload.content_type,
                rating=rating,
                is_public=is_public,
                source_url=source_url,
                artist_name=artist_name,
                work_ids=parsed_work_ids,
                character_ids=parsed_character_ids,
                merge_duplicate_relations=merge_duplicate_relations,
                precomputed_sha256=item["sha256"],
                precomputed_inspection=item["inspection"],
                commit=False,
            )
            uploaded.append((image, duplicate))
            if not duplicate:
                created_paths.extend((image.file_path, image.preview_path, image.thumbnail_path))
        db.commit()
    except (ValueError, InvalidImageError) as exc:
        db.rollback()
        for path in created_paths:
            delete_storage_file(path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        for path in created_paths:
            delete_storage_file(path)
        raise HTTPException(status_code=500, detail="批量上传失败，本批图片未提交") from exc

    results = [ImageUploadResult(image=image, duplicate=duplicate) for image, duplicate in uploaded]
    return {"items": results}


@router.post("/preview")
async def preview_upload_image(
    admin: Annotated[dict, Depends(require_uploads_manage)],
    file: Annotated[UploadFile, File()],
):
    try:
        validate_upload_filename(file.filename)
        data = await file.read()
        preview = render_webp_preview_bytes(data, max_size=960)
    except (ValueError, InvalidImageError) as exc:
        raise HTTPException(status_code=400, detail=f"{file.filename}: {exc}") from exc
    return Response(content=preview, media_type="image/webp")


@router.put("/batch", response_model=ImageBatchResult)
def update_images_batch(
    payload: ImageBatchUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_library_write)],
):
    image_ids = list(dict.fromkeys(payload.image_ids))
    images = db.scalars(select(Image).options(*_image_options()).where(Image.id.in_(image_ids))).unique().all()
    if len(images) != len(image_ids):
        found_ids = {image.id for image in images}
        missing_ids = [image_id for image_id in image_ids if image_id not in found_ids]
        raise HTTPException(status_code=404, detail=f"Images not found: {missing_ids}")

    data = payload.update.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="At least one field is required")

    work_ids = data.pop("work_ids", None)
    character_ids = data.pop("character_ids", None)
    service = ImageService(db)
    for image in images:
        _rotate_media_version_if_access_changes(image, data)
        for key, value in data.items():
            setattr(image, key, value)
        service.update_relations(image, work_ids, character_ids)

    db.commit()
    return {"count": len(images)}


@router.delete("/batch", response_model=ImageBatchResult)
def delete_images_batch(
    payload: ImageBatchDelete,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_library_delete)],
):
    image_ids = list(dict.fromkeys(payload.image_ids))
    images = db.scalars(select(Image).where(Image.id.in_(image_ids))).unique().all()
    if len(images) != len(image_ids):
        found_ids = {image.id for image in images}
        missing_ids = [image_id for image_id in image_ids if image_id not in found_ids]
        raise HTTPException(status_code=404, detail=f"Images not found: {missing_ids}")

    paths = []
    for image in images:
        paths.extend([image.file_path, image.preview_path, image.thumbnail_path])
        db.delete(image)

    db.commit()
    for path in paths:
        delete_storage_file(path)

    return {"count": len(images)}


@router.get("/{image_id}", response_model=ImageRead)
def get_image(
    image_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict | None, Depends(optional_admin)],
):
    image = db.scalar(select(Image).options(*_image_options()).where(Image.id == image_id))
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if not admin and (not image.is_public or image.rating == "hidden"):
        raise HTTPException(status_code=404, detail="Image not found")
    return image


@router.post("/{image_id}/view", response_model=ImageRead)
def track_image_view(
    image_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    return _update_public_image_counter(
        db,
        image_id,
        {Image.view_count: Image.view_count + 1},
    )


@router.post("/{image_id}/favorite", response_model=ImageRead)
def favorite_image(
    image_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    return _update_public_image_counter(
        db,
        image_id,
        {Image.favorite_count: Image.favorite_count + 1},
    )


@router.delete("/{image_id}/favorite", response_model=ImageRead)
def unfavorite_image(
    image_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    return _update_public_image_counter(
        db,
        image_id,
        {
            Image.favorite_count: case(
                (Image.favorite_count > 0, Image.favorite_count - 1),
                else_=0,
            )
        },
    )


@router.put("/{image_id}", response_model=ImageRead)
def update_image(
    image_id: int,
    payload: ImageUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_library_write)],
):
    image = db.scalar(select(Image).options(*_image_options()).where(Image.id == image_id))
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    data = payload.model_dump(exclude_unset=True)
    _validate_original_filename_extension(image.original_filename or image.filename, data.get("original_filename"))
    work_ids = data.pop("work_ids", None)
    character_ids = data.pop("character_ids", None)
    _rotate_media_version_if_access_changes(image, data)
    for key, value in data.items():
        setattr(image, key, value)
    ImageService(db).update_relations(image, work_ids, character_ids)
    db.commit()
    db.refresh(image)
    return image


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    image_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_library_delete)],
):
    image = db.scalar(select(Image).where(Image.id == image_id))
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    ImageService(db).delete_image(image)
    return None
