import random
from typing import Annotated
from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.helpers import parse_id_csv
from app.auth import optional_admin, require_admin
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
from app.services.storage_service import delete_storage_file, resolve_storage_file
from app.utils.image_process import InvalidImageError, render_webp_preview_bytes, validate_upload_filename

router = APIRouter(prefix="/images", tags=["images"])


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
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    needle = f"%{escaped}%"
    return or_(
        Character.name.ilike(needle, escape="\\"),
        Character.original_name.ilike(needle, escape="\\"),
        Character.aliases.ilike(needle, escape="\\"),
    )


def _random_images_from_stmt(db: Session, stmt, page_size: int, total: int) -> list[Image]:
    if total <= 0:
        return []

    filtered = stmt.order_by(None).subquery()
    id_col = filtered.c.id
    min_id, max_id = db.execute(select(func.min(id_col), func.max(id_col))).one()
    if min_id is None or max_id is None:
        return []

    selected_ids: list[int] = []
    seen_ids: set[int] = set()
    batch_limit = min(max(page_size * 2, 12), 100)
    attempts = min(max(page_size * 6, 24), 120)

    def add_candidates(candidates: list[int]) -> None:
        random.shuffle(candidates)
        for image_id in candidates:
            if image_id in seen_ids:
                continue
            seen_ids.add(image_id)
            selected_ids.append(image_id)
            if len(selected_ids) >= page_size:
                break

    for _ in range(attempts):
        if len(selected_ids) >= page_size:
            break
        pivot = random.randint(int(min_id), int(max_id))
        candidates = db.scalars(
            select(id_col)
            .where(id_col >= pivot)
            .order_by(id_col.asc())
            .limit(batch_limit)
        ).all()
        if not candidates:
            candidates = db.scalars(
                select(id_col)
                .where(id_col < pivot)
                .order_by(id_col.asc())
                .limit(batch_limit)
            ).all()
        add_candidates(candidates)

    if len(selected_ids) < page_size:
        fallback = db.scalars(
            select(id_col)
            .order_by(id_col.asc())
            .offset(random.randint(0, max(total - 1, 0)))
            .limit(batch_limit)
        ).all()
        if len(fallback) < batch_limit:
            fallback.extend(
                db.scalars(
                    select(id_col)
                    .order_by(id_col.asc())
                    .limit(batch_limit - len(fallback))
                ).all()
            )
        add_candidates(fallback)

    if not selected_ids:
        return []
    images = db.scalars(
        select(Image)
        .options(*_image_options())
        .where(Image.id.in_(selected_ids))
    ).unique().all()
    image_by_id = {image.id: image for image in images}
    return [image_by_id[image_id] for image_id in selected_ids if image_id in image_by_id]


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
    candidates = {
        "original": ((image.file_path, "original"),),
        "preview": (
            (image.preview_path, "preview"),
            (image.file_path, "original"),
        ),
        "thumbnail": (
            (image.thumbnail_path, "thumbnail"),
            (image.preview_path, "preview"),
            (image.file_path, "original"),
        ),
    }
    for path, served_variant in candidates[requested_variant]:
        if not path:
            continue
        try:
            target = resolve_storage_file(path)
        except ValueError:
            continue
        if target.is_file():
            return path, served_variant
    raise FileNotFoundError


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

    image_url = f"/storage/{quote(selected_path, safe='/')}"
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
    q: str | None = None,
    sort: str = Query("latest", pattern="^(latest|random|favorites|resolution)$"),
    public_only: bool = True,
    exclude_work_related: bool = False,
    exclude_character_related: bool = False,
    require_work_related: bool = False,
    require_character_related: bool = False,
    exclude_cover_images: bool = False,
    exclude_avatar_images: bool = False,
):
    if not public_only and not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    stmt = select(Image).options(*_image_options()).distinct()
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
    if exclude_cover_images:
        stmt = stmt.where(~select(Work.id).where(Work.cover_image_id == Image.id).exists())
    if exclude_avatar_images:
        stmt = stmt.where(~select(Character.id).where(Character.avatar_image_id == Image.id).exists())
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
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Image.filename.ilike(needle),
                Image.original_filename.ilike(needle),
                Image.artist_name.ilike(needle),
                Image.source_url.ilike(needle),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0

    if sort == "random":
        items = _random_images_from_stmt(db, stmt, page_size, total)
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    elif sort == "favorites":
        stmt = stmt.order_by(desc(Image.favorite_count), desc(Image.created_at))
    elif sort == "resolution":
        stmt = stmt.order_by(desc(Image.width * Image.height), desc(Image.created_at))
    else:
        stmt = stmt.order_by(desc(Image.created_at))

    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/upload", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_images(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
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

    service = ImageService(db)
    results: list[ImageUploadResult] = []
    try:
        parsed_work_ids = parse_id_csv(work_ids)
        parsed_character_ids = parse_id_csv(character_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Relation ids must be comma separated integers") from exc

    for upload in files:
        try:
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
            )
        except (ValueError, InvalidImageError) as exc:
            raise HTTPException(status_code=400, detail=f"{upload.filename}: {exc}") from exc
        results.append(ImageUploadResult(image=image, duplicate=duplicate))

    return {"items": results}


@router.post("/preview")
async def preview_upload_image(
    admin: Annotated[dict, Depends(require_admin)],
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
    admin: Annotated[dict, Depends(require_admin)],
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
        for key, value in data.items():
            setattr(image, key, value)
        service.update_relations(image, work_ids, character_ids)

    db.commit()
    return {"count": len(images)}


@router.delete("/batch", response_model=ImageBatchResult)
def delete_images_batch(
    payload: ImageBatchDelete,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
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
    image = db.scalar(select(Image).options(*_image_options()).where(Image.id == image_id))
    if not image or not image.is_public or image.rating == "hidden":
        raise HTTPException(status_code=404, detail="Image not found")
    image.view_count += 1
    db.commit()
    db.refresh(image)
    return image


@router.post("/{image_id}/favorite", response_model=ImageRead)
def favorite_image(
    image_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    image = db.scalar(select(Image).options(*_image_options()).where(Image.id == image_id))
    if not image or not image.is_public or image.rating == "hidden":
        raise HTTPException(status_code=404, detail="Image not found")
    image.favorite_count += 1
    db.commit()
    db.refresh(image)
    return image


@router.delete("/{image_id}/favorite", response_model=ImageRead)
def unfavorite_image(
    image_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    image = db.scalar(select(Image).options(*_image_options()).where(Image.id == image_id))
    if not image or not image.is_public or image.rating == "hidden":
        raise HTTPException(status_code=404, detail="Image not found")
    image.favorite_count = max(0, image.favorite_count - 1)
    db.commit()
    db.refresh(image)
    return image


@router.put("/{image_id}", response_model=ImageRead)
def update_image(
    image_id: int,
    payload: ImageUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[dict, Depends(require_admin)],
):
    image = db.scalar(select(Image).options(*_image_options()).where(Image.id == image_id))
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    data = payload.model_dump(exclude_unset=True)
    _validate_original_filename_extension(image.original_filename or image.filename, data.get("original_filename"))
    work_ids = data.pop("work_ids", None)
    character_ids = data.pop("character_ids", None)
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
    admin: Annotated[dict, Depends(require_admin)],
):
    image = db.scalar(select(Image).where(Image.id == image_id))
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    ImageService(db).delete_image(image)
    return None
