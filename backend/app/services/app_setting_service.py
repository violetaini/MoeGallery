from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppSetting

UPLOAD_WORKER_COUNT_KEY = "upload.worker_count"
UPLOAD_CLAIM_BATCH_SIZE_KEY = "upload.claim_batch_size"


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
