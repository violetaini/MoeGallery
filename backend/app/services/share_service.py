import secrets
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Image, Share
from app.models.associations import share_images
from app.utils.time import utcnow_naive


MAX_SHARE_TOKEN_LENGTH = 64


def _share_options():
    return (selectinload(Share.images),)


def _new_share_token() -> str:
    return secrets.token_urlsafe(24)


def _default_share_title(images: list[Image]) -> str:
    if len(images) == 1:
        return "图片分享"
    return f"{len(images)} 张图片分享"


def create_share(
    db: Session,
    *,
    image_ids: list[int],
    title: str | None,
    expires_in_hours: int | None = None,
) -> Share:
    images_by_id = {
        image.id: image
        for image in db.scalars(select(Image).where(Image.id.in_(image_ids))).all()
    }
    missing_ids = [image_id for image_id in image_ids if image_id not in images_by_id]
    if missing_ids:
        raise ValueError(f"Images not found: {missing_ids}")

    images = [images_by_id[image_id] for image_id in image_ids]
    for _ in range(5):
        try:
            expires_at = (
                utcnow_naive() + timedelta(hours=expires_in_hours)
                if expires_in_hours is not None
                else None
            )
            share = Share(
                token=_new_share_token(),
                title=title or _default_share_title(images),
                expires_at=expires_at,
            )
            db.add(share)
            db.flush()
            db.execute(
                share_images.insert(),
                [
                    {"share_id": share.id, "image_id": image.id, "sort_order": index}
                    for index, image in enumerate(images)
                ],
            )
            db.commit()
            return db.scalar(select(Share).options(*_share_options()).where(Share.id == share.id))
        except IntegrityError:
            db.rollback()
            continue
        except Exception:
            db.rollback()
            raise
    raise RuntimeError("Unable to create a unique share token")


def get_active_share(db: Session, token: str) -> Share | None:
    if not token or len(token) > MAX_SHARE_TOKEN_LENGTH:
        return None
    return db.scalar(
        select(Share)
        .options(*_share_options())
        .where(
            Share.token == token,
            Share.is_active.is_(True),
            or_(Share.expires_at.is_(None), Share.expires_at > utcnow_naive()),
        )
    )


def get_active_share_image(db: Session, token: str, image_id: int) -> Image | None:
    if not token or len(token) > MAX_SHARE_TOKEN_LENGTH:
        return None
    return db.scalar(
        select(Image)
        .options(selectinload(Image.works), selectinload(Image.characters))
        .join(share_images, share_images.c.image_id == Image.id)
        .join(Share, Share.id == share_images.c.share_id)
        .where(
            Share.token == token,
            Share.is_active.is_(True),
            or_(Share.expires_at.is_(None), Share.expires_at > utcnow_naive()),
            Image.id == image_id,
        )
    )


def share_allows_image(db: Session, token: str | None, image_id: int) -> bool:
    if not token or len(token) > MAX_SHARE_TOKEN_LENGTH:
        return False
    return bool(
        db.scalar(
            select(share_images.c.share_id)
            .join(Share, Share.id == share_images.c.share_id)
            .where(
                Share.token == token,
                Share.is_active.is_(True),
                or_(Share.expires_at.is_(None), Share.expires_at > utcnow_naive()),
                share_images.c.image_id == image_id,
            )
            .limit(1)
        )
    )
