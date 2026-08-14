from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_library_write
from app.database import get_db
from app.models import Share
from app.schemas.share import ShareCreate, ShareImageDetail, ShareListResponse, SharePublicRead, ShareRead, ShareUpdate
from app.services.share_service import create_share, get_active_share, get_active_share_image
from app.utils.time import utcnow_naive


router = APIRouter(prefix="/shares", tags=["shares"])


def _share_options():
    return (selectinload(Share.images),)


@router.post("", response_model=ShareRead, status_code=status.HTTP_201_CREATED)
def create_share_link(
    payload: ShareCreate,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_library_write)],
):
    try:
        share = create_share(
            db,
            image_ids=payload.image_ids,
            title=payload.title,
            expires_in_hours=payload.expires_in_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return share


@router.get("", response_model=ShareListResponse)
def list_shares(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_library_write)],
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    stmt = select(Share).options(*_share_options())
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(
        stmt.order_by(desc(Share.created_at), desc(Share.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{token}", response_model=SharePublicRead)
def get_public_share(
    token: str,
    db: Annotated[Session, Depends(get_db)],
):
    share = get_active_share(db, token)
    if not share or not share.images:
        raise HTTPException(status_code=404, detail="分享不存在或已撤销")
    return {
        "token": share.token,
        "title": share.title,
        "image_count": len(share.images),
        "images": share.images,
    }


@router.get("/{token}/images/{image_id}", response_model=ShareImageDetail)
def get_public_share_image(
    token: str,
    image_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    image = get_active_share_image(db, token, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="分享图片不存在或已撤销")
    return image


@router.patch("/{share_id}", response_model=ShareRead)
def update_share(
    share_id: int,
    payload: ShareUpdate,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_library_write)],
):
    share = db.get(Share, share_id)
    if not share or not share.is_active:
        raise HTTPException(status_code=404, detail="分享不存在或已撤销")

    updates = payload.model_dump(exclude_unset=True)
    if "title" in updates:
        if not updates["title"]:
            raise HTTPException(status_code=422, detail="分享标题不能为空")
        share.title = updates["title"]
    if "expires_in_hours" in updates:
        hours = updates["expires_in_hours"]
        share.expires_at = utcnow_naive() + timedelta(hours=hours) if hours else None

    db.commit()
    return db.scalar(select(Share).options(*_share_options()).where(Share.id == share.id))


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(
    share_id: int,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[dict, Depends(require_library_write)],
):
    share = db.get(Share, share_id)
    if not share or not share.is_active:
        raise HTTPException(status_code=404, detail="分享不存在或已撤销")
    share.is_active = False
    db.commit()
    return None
