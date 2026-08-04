from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import settings
from app.database import MYSQL_RESERVED_CONNECTION_SLOTS
from app.models import AppSetting

UPLOAD_WORKER_COUNT_KEY = "upload.worker_count"
UPLOAD_CLAIM_BATCH_SIZE_KEY = "upload.claim_batch_size"
UPLOAD_TASK_MAX_ATTEMPTS_KEY = "upload.task_max_attempts"
UPLOAD_TASK_FAILED_RETENTION_DAYS_KEY = "upload.failed_retention_days"
GITHUB_RELEASE_PROXY_URL_KEY = "system.github_release_proxy_url"
RANDOM_API_DESKTOP_ORIENTATION_KEY = "random_api.desktop_orientation"
RANDOM_API_MOBILE_ORIENTATION_KEY = "random_api.mobile_orientation"
RANDOM_API_DEFAULT_RATING_KEY = "random_api.default_rating"
RANDOM_API_DEFAULT_VARIANT_KEY = "random_api.default_variant"

DEFAULT_RANDOM_API_DESKTOP_ORIENTATION = "landscape"
DEFAULT_RANDOM_API_MOBILE_ORIENTATION = "portrait"
DEFAULT_RANDOM_API_RATING = "safe"
DEFAULT_RANDOM_API_VARIANT = "preview"

VALID_RANDOM_API_ORIENTATIONS = {"landscape", "portrait", "square", "any"}
VALID_RANDOM_API_RATINGS = {"safe", "sensitive", "any"}
VALID_RANDOM_API_VARIANTS = {"original", "preview", "thumbnail"}


def get_int_setting(db: Session, key: str, default: int, minimum: int, maximum: int) -> int:
    setting = db.get(AppSetting, key)
    try:
        value = int(setting.value) if setting else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def get_upload_worker_requested_count(db: Session) -> int:
    return get_int_setting(db, UPLOAD_WORKER_COUNT_KEY, settings.upload_worker_count, 1, 96)


def upload_worker_limit_for_dialect(dialect: str) -> int:
    if dialect == "sqlite":
        return settings.sqlite_upload_worker_limit
    if dialect in {"mysql", "mariadb"}:
        pool_capacity = settings.mysql_pool_size + settings.mysql_max_overflow
        return max(1, min(96, pool_capacity - MYSQL_RESERVED_CONNECTION_SLOTS))
    return 96


def get_upload_worker_profile(db: Session) -> dict[str, int | str]:
    dialect = db.get_bind().dialect.name
    requested = get_upload_worker_requested_count(db)
    limit = upload_worker_limit_for_dialect(dialect)
    return {
        "dialect": dialect,
        "profile": "sqlite_conservative" if dialect == "sqlite" else "mysql_high_throughput" if dialect in {"mysql", "mariadb"} else "generic",
        "requested": requested,
        "effective": min(requested, limit),
        "limit": limit,
    }


def get_upload_worker_count(db: Session) -> int:
    return int(get_upload_worker_profile(db)["effective"])


def get_upload_claim_batch_size(db: Session) -> int:
    return get_int_setting(db, UPLOAD_CLAIM_BATCH_SIZE_KEY, settings.upload_claim_batch_size, 1, 100)


def get_upload_task_max_attempts(db: Session) -> int:
    return get_int_setting(db, UPLOAD_TASK_MAX_ATTEMPTS_KEY, settings.upload_task_max_attempts, 1, 10)


def get_upload_failed_retention_days(db: Session) -> int:
    return get_int_setting(
        db,
        UPLOAD_TASK_FAILED_RETENTION_DAYS_KEY,
        settings.upload_task_failed_retention_days,
        1,
        90,
    )


def get_choice_setting(db: Session, key: str, default: str, choices: set[str]) -> str:
    setting = db.get(AppSetting, key)
    value = setting.value if setting else default
    return value if value in choices else default


def get_random_api_defaults(db: Session) -> dict[str, str]:
    return {
        "desktop_orientation": get_choice_setting(
            db,
            RANDOM_API_DESKTOP_ORIENTATION_KEY,
            DEFAULT_RANDOM_API_DESKTOP_ORIENTATION,
            VALID_RANDOM_API_ORIENTATIONS,
        ),
        "mobile_orientation": get_choice_setting(
            db,
            RANDOM_API_MOBILE_ORIENTATION_KEY,
            DEFAULT_RANDOM_API_MOBILE_ORIENTATION,
            VALID_RANDOM_API_ORIENTATIONS,
        ),
        "rating": get_choice_setting(
            db,
            RANDOM_API_DEFAULT_RATING_KEY,
            DEFAULT_RANDOM_API_RATING,
            VALID_RANDOM_API_RATINGS,
        ),
        "variant": get_choice_setting(
            db,
            RANDOM_API_DEFAULT_VARIANT_KEY,
            DEFAULT_RANDOM_API_VARIANT,
            VALID_RANDOM_API_VARIANTS,
        ),
    }


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
