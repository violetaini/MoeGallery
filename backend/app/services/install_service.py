import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.config import ROOT_DIR, generate_api_key, generate_auth_secret, is_weak_auth_secret, settings
from app.models import AppSetting
from app.services.admin_account_service import (
    ADMIN_PASSWORD_HASH_KEY,
    ADMIN_USERNAME_KEY,
    hash_password,
)
from app.services.storage_service import ensure_storage_dirs

INSTALL_LOCK_PATH = ROOT_DIR / "installed.lock"
ENV_PATH = ROOT_DIR / ".env"
DEFAULT_SQLITE_PATH = ROOT_DIR / "backend" / "anime_gallery.db"
ALEMBIC_VERSION_LENGTH = 128


def database_url_hash(database_url: str) -> str:
    return hashlib.sha256(database_url.encode("utf-8")).hexdigest()


def read_install_lock() -> dict:
    if not INSTALL_LOCK_PATH.exists():
        return {}
    try:
        return json.loads(INSTALL_LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def has_install_lock() -> bool:
    return INSTALL_LOCK_PATH.exists()


def current_database_is_initialized() -> bool:
    engine = create_database_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            if not inspector.has_table("alembic_version"):
                return False
            version = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
            return bool(version)
    except Exception:
        return False
    finally:
        engine.dispose()


def is_installed() -> bool:
    return has_install_lock() or current_database_is_initialized()


def restart_required() -> bool:
    lock = read_install_lock()
    locked_hash = lock.get("database_url_hash")
    return bool(locked_hash and locked_hash != database_url_hash(settings.database_url))


def build_sqlite_url(sqlite_path: str) -> str:
    db_path = Path(sqlite_path).expanduser() if sqlite_path else DEFAULT_SQLITE_PATH
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


def build_mysql_url(host: str, port: int, database: str, username: str, password: str) -> str:
    return (
        "mysql+pymysql://"
        f"{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{quote_plus(database)}?charset=utf8mb4"
    )


def database_connect_args(database_url: str) -> dict:
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif database_url.startswith(("mysql", "mariadb")):
        connect_args["charset"] = "utf8mb4"
    return connect_args


def create_database_engine(database_url: str):
    return create_engine(
        database_url,
        connect_args=database_connect_args(database_url),
        pool_pre_ping=True,
        future=True,
    )


def test_database_url(database_url: str) -> None:
    engine = create_database_engine(database_url)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def prepare_alembic_version_table(database_url: str) -> None:
    if not database_url.startswith(("mysql", "mariadb")):
        return
    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            inspector = inspect(connection)
            if inspector.has_table("alembic_version"):
                connection.execute(
                    text(
                        "ALTER TABLE alembic_version "
                        f"MODIFY COLUMN version_num VARCHAR({ALEMBIC_VERSION_LENGTH}) NOT NULL"
                    )
                )
            else:
                connection.execute(
                    text(
                        "CREATE TABLE alembic_version ("
                        f"version_num VARCHAR({ALEMBIC_VERSION_LENGTH}) NOT NULL, "
                        "PRIMARY KEY (version_num)"
                        ")"
                    )
                )
    finally:
        engine.dispose()


def run_migrations(database_url: str) -> None:
    prepare_alembic_version_table(database_url)
    config = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT_DIR / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def initialize_admin(database_url: str, username: str, password: str) -> None:
    engine = create_database_engine(database_url)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as db:
        for key, value in {
            ADMIN_USERNAME_KEY: username.strip(),
            ADMIN_PASSWORD_HASH_KEY: hash_password(password),
        }.items():
            setting = db.get(AppSetting, key)
            if setting:
                setting.value = value
            else:
                db.add(AppSetting(key=key, value=value))
        db.commit()


def _serialize_env_value(value: str) -> str:
    if any(char.isspace() for char in value):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_env(updates: dict[str, str]) -> None:
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    consumed: set[str] = set()
    output: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={_serialize_env_value(updates[key])}")
            consumed.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in consumed:
            output.append(f"{key}={_serialize_env_value(value)}")
    ENV_PATH.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    if os.name == "posix":
        try:
            ENV_PATH.chmod(0o600)
        except OSError:
            pass


def write_install_lock(database_type: str, database_url: str) -> None:
    payload = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "database_type": database_type,
        "database_url_hash": database_url_hash(database_url),
    }
    INSTALL_LOCK_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def perform_install(
    *,
    database_type: str,
    database_url: str,
    admin_username: str,
    admin_password: str,
    auth_secret: str | None,
) -> dict:
    test_database_url(database_url)
    run_migrations(database_url)
    initialize_admin(database_url, admin_username, admin_password)
    resolved_auth_secret = auth_secret.strip() if auth_secret else generate_auth_secret()
    if is_weak_auth_secret(resolved_auth_secret):
        raise ValueError("AGMS_AUTH_SECRET is too weak")
    updates = {
        "AGMS_DATABASE_URL": database_url,
        "AGMS_ADMIN_USERNAME": admin_username.strip(),
        "AGMS_ADMIN_PASSWORD": admin_password,
        "AGMS_AUTH_SECRET": resolved_auth_secret,
        "AGMS_API_KEYS": settings.api_keys or f"default:{generate_api_key()}",
    }
    write_env(updates)
    ensure_storage_dirs()
    write_install_lock(database_type, database_url)
    return {
        "installed": True,
        "database_type": database_type,
        "restart_required": database_url_hash(database_url) != database_url_hash(settings.database_url),
    }
