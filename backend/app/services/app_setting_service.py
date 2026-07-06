from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppSetting

UPLOAD_WORKER_COUNT_KEY = "upload.worker_count"
UPLOAD_CLAIM_BATCH_SIZE_KEY = "upload.claim_batch_size"
GITHUB_RELEASE_PROXY_URL_KEY = "system.github_release_proxy_url"


def get_int_setting(db: Session, key: str, default: int, minimum: int, maximum: int) -> int:
    setting = db.get(AppSetting, key)
    try:
        value = int(setting.value) if setting else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def get_upload_worker_count(db: Session) -> int:
    return get_int_setting(db, UPLOAD_WORKER_COUNT_KEY, settings.upload_worker_count, 1, 96)


def get_upload_claim_batch_size(db: Session) -> int:
    return get_int_setting(db, UPLOAD_CLAIM_BATCH_SIZE_KEY, settings.upload_claim_batch_size, 1, 100)


def normalize_github_release_proxy_url(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    if len(normalized) > 500:
        raise ValueError("GitHub proxy URL must be no longer than 500 characters")
    if any(char.isspace() for char in normalized):
        raise ValueError("GitHub proxy URL must not contain whitespace")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("GitHub proxy URL must be a valid http(s) URL")
    return normalized


def get_github_release_proxy_url(db: Session) -> str:
    setting = db.get(AppSetting, GITHUB_RELEASE_PROXY_URL_KEY)
    try:
        return normalize_github_release_proxy_url(setting.value if setting else "")
    except ValueError:
        return ""
