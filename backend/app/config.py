import hashlib
import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
AUTH_SECRET_MIN_LENGTH = 32
API_KEY_MIN_LENGTH = 32
WEAK_AUTH_SECRET_VALUES = {
    "change-me-before-deploy",
    "change-this-long-random-secret",
    "change-this-password",
    "admin",
    "admin123",
    "password",
    "secret",
    "test",
}


def generate_auth_secret() -> str:
    return secrets.token_urlsafe(48)


def generate_api_key() -> str:
    return f"agms_{secrets.token_urlsafe(48)}"


def _read_env_value(key: str) -> str | None:
    if not ENV_PATH.exists():
        return None
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_key, value = stripped.split("=", 1)
        if env_key.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def auth_secret_is_configured() -> bool:
    return bool(os.environ.get("AGMS_AUTH_SECRET") or _read_env_value("AGMS_AUTH_SECRET"))


def is_weak_auth_secret(value: str | None) -> bool:
    secret = (value or "").strip()
    if len(secret) < AUTH_SECRET_MIN_LENGTH:
        return True
    if secret.lower() in WEAK_AUTH_SECRET_VALUES:
        return True
    if len(set(secret)) < 8:
        return True
    return False


def parse_api_keys(value: str | None) -> list[tuple[str, str]]:
    if not value:
        return []
    result: list[tuple[str, str]] = []
    raw_items = value.replace("\n", ",").replace(";", ",").split(",")
    for index, raw_item in enumerate(raw_items, start=1):
        item = raw_item.strip()
        if not item:
            continue
        if ":" in item:
            name, key = item.split(":", 1)
            label = name.strip() or f"key-{index}"
            secret = key.strip()
        else:
            label = f"key-{index}"
            secret = item
        result.append((label, secret))
    return result


def is_weak_api_key(value: str | None) -> bool:
    key = (value or "").strip()
    if len(key) < API_KEY_MIN_LENGTH:
        return True
    if key.lower() in WEAK_AUTH_SECRET_VALUES:
        return True
    if len(set(key)) < 8:
        return True
    return False


def auth_secret_fingerprint(value: str) -> str:
    return hashlib.sha256(f"agms-auth-secret-v1:{value}".encode("utf-8")).hexdigest()[:16]


def auth_secret_health(value: str) -> dict:
    configured = auth_secret_is_configured()
    strong = not is_weak_auth_secret(value)
    if not strong:
        message = "AGMS_AUTH_SECRET 过短或仍为占位符，请立即更换"
    elif not configured:
        message = "当前进程使用临时随机密钥，重启后会使已登录会话失效"
    else:
        message = "已配置持久化强密钥"
    return {
        "configured": configured,
        "ephemeral": not configured,
        "strong": strong,
        "message": message,
    }


class Settings(BaseSettings):
    app_name: str = "Anime Gallery Media Server"
    app_version: str = "0.1.5"
    api_prefix: str = "/api"
    database_url: str = f"sqlite:///{(ROOT_DIR / 'backend' / 'anime_gallery.db').as_posix()}"
    storage_path: Path = ROOT_DIR / "storage"
    admin_username: str = "admin"
    admin_password: str = "admin123"
    auth_secret: str = Field(default_factory=generate_auth_secret, min_length=AUTH_SECRET_MIN_LENGTH)
    api_keys: str = ""
    auth_token_ttl_seconds: int = 12 * 60 * 60
    auth_issuer: str = "agms-admin"
    auth_audience: str = "agms-backend"
    cookie_secure: bool = False
    login_rate_limit_window_seconds: int = 300
    login_rate_limit_max_attempts: int = 8
    max_upload_size: int = 100 * 1024 * 1024
    preview_max_size: int = 1600
    thumbnail_max_size: int = 480
    upload_worker_count: int = 12
    upload_claim_batch_size: int = 1
    update_trigger_command: str = ""
    update_service_name: str = "anime-gallery"
    update_health_url: str = "http://127.0.0.1:8000/api/health"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_prefix="AGMS_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_auth_secret(self):
        if is_weak_auth_secret(self.auth_secret):
            raise ValueError(
                f"AGMS_AUTH_SECRET must be a non-placeholder secret with at least {AUTH_SECRET_MIN_LENGTH} characters"
            )
        weak_api_keys = [name for name, key in parse_api_keys(self.api_keys) if is_weak_api_key(key)]
        if weak_api_keys:
            raise ValueError(
                f"AGMS_API_KEYS contains weak keys: {', '.join(weak_api_keys)}; each key must be at least {API_KEY_MIN_LENGTH} characters"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
