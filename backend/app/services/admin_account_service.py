import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppSetting, Image

ADMIN_USERNAME_KEY = "admin.username"
ADMIN_PASSWORD_HASH_KEY = "admin.password_hash"
ADMIN_AVATAR_IMAGE_ID_KEY = "admin.avatar_image_id"

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 210_000


@dataclass(frozen=True)
class AdminAccount:
    username: str
    avatar_image_id: int | None
    avatar_image: Image | None


def _get_setting(db: Session, key: str) -> str | None:
    setting = db.get(AppSetting, key)
    return setting.value if setting else None


def _set_setting(db: Session, key: str, value: str) -> None:
    setting = db.get(AppSetting, key)
    if setting:
        setting.value = value
        return
    db.add(AppSetting(key=key, value=value))


def _delete_setting(db: Session, key: str) -> None:
    setting = db.get(AppSetting, key)
    if setting:
        db.delete(setting)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return ".".join(
        [
            PASSWORD_SCHEME,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        ]
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return hmac.compare_digest(password, settings.admin_password)
    try:
        scheme, iterations_text, salt_text, digest_text = encoded.split(".", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def get_admin_username(db: Session) -> str:
    return (_get_setting(db, ADMIN_USERNAME_KEY) or settings.admin_username).strip() or settings.admin_username


def get_admin_account(db: Session) -> AdminAccount:
    avatar_image_id_text = _get_setting(db, ADMIN_AVATAR_IMAGE_ID_KEY)
    avatar_image_id: int | None = None
    avatar_image: Image | None = None
    if avatar_image_id_text:
        try:
            avatar_image_id = int(avatar_image_id_text)
        except ValueError:
            avatar_image_id = None
    if avatar_image_id is not None:
        avatar_image = db.get(Image, avatar_image_id)
        if not avatar_image:
            avatar_image_id = None
    return AdminAccount(
        username=get_admin_username(db),
        avatar_image_id=avatar_image_id,
        avatar_image=avatar_image,
    )


def authenticate_admin(db: Session, username: str, password: str) -> AdminAccount | None:
    account = get_admin_account(db)
    password_hash = _get_setting(db, ADMIN_PASSWORD_HASH_KEY)
    if not hmac.compare_digest(username, account.username):
        return None
    if not verify_password(password, password_hash):
        return None
    return account


def update_admin_account(
    db: Session,
    *,
    username: str | None = None,
    password: str | None = None,
    avatar_image_id: int | None = None,
    clear_avatar: bool = False,
) -> AdminAccount:
    if username is not None:
        normalized = username.strip()
        if not normalized:
            raise ValueError("用户名不能为空")
        _set_setting(db, ADMIN_USERNAME_KEY, normalized)
    if password is not None:
        if len(password) < 6:
            raise ValueError("密码至少需要 6 位")
        _set_setting(db, ADMIN_PASSWORD_HASH_KEY, hash_password(password))
    if clear_avatar:
        _delete_setting(db, ADMIN_AVATAR_IMAGE_ID_KEY)
    elif avatar_image_id is not None:
        if not db.get(Image, avatar_image_id):
            raise ValueError(f"Image {avatar_image_id} not found")
        _set_setting(db, ADMIN_AVATAR_IMAGE_ID_KEY, str(avatar_image_id))
    return get_admin_account(db)
