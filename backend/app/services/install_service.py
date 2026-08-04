import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.config import ROOT_DIR, generate_api_key, generate_auth_secret, settings
from app.database import create_database_engine
from app.models import AppSetting
from app.services.admin_account_service import (
    ADMIN_PASSWORD_CHANGE_REQUIRED_KEY,
    ADMIN_PASSWORD_HASH_KEY,
    ADMIN_USERNAME_KEY,
    hash_password,
)
from app.services.storage_service import ensure_storage_dirs

INSTALL_LOCK_PATH = ROOT_DIR / "installed.lock"
ENV_PATH = ROOT_DIR / ".env"
DEFAULT_SQLITE_PATH = ROOT_DIR / "backend" / "anime_gallery.db"
ALEMBIC_VERSION_LENGTH = 128
LEGACY_ADMIN_PASSWORD_ENV = "AGMS_ADMIN_PASSWORD"
LEGACY_BUILTIN_ADMIN_PASSWORD = "admin123"
INSTALL_TOKEN_ENV = "AGMS_INSTALL_TOKEN"
INSTALLATION_IN_PROGRESS_KEY = "installation.in_progress"
INSTALLATION_COMPLETED_KEY = "installation.completed_at"
_INSTALL_THREAD_LOCK = threading.Lock()


class InstallInProgressError(RuntimeError):
    pass


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
        return _database_is_initialized(engine)
    except Exception:
        return False
    finally:
        engine.dispose()


def _database_is_initialized(engine) -> bool:
    with engine.connect() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("alembic_version") or not inspector.has_table(AppSetting.__tablename__):
            return False
        version = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
        if not version:
            return False
        in_progress = connection.execute(
            select(AppSetting.value).where(AppSetting.key == INSTALLATION_IN_PROGRESS_KEY)
        ).scalar()
        if in_progress:
            return False
        completed = connection.execute(
            select(AppSetting.value).where(AppSetting.key == INSTALLATION_COMPLETED_KEY)
        ).scalar()
        if completed:
            return True
        username = connection.execute(select(AppSetting.value).where(AppSetting.key == ADMIN_USERNAME_KEY)).scalar()
        password_hash = connection.execute(
            select(AppSetting.value).where(AppSetting.key == ADMIN_PASSWORD_HASH_KEY)
        ).scalar()
        return bool(username and password_hash)


def _database_has_migrations(engine) -> bool:
    with engine.connect() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("alembic_version"):
            return False
        return bool(connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar())


def is_installed() -> bool:
    lock = read_install_lock()
    if lock and lock.get("state", "completed") != "pending":
        return True
    return current_database_is_initialized()


def _install_runtime_path(filename: str) -> Path:
    return settings.storage_path / "runtime" / filename


def _write_private_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        if os.name == "posix":
            temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def install_token_state_path() -> Path:
    return _install_runtime_path("install-token.json")


def prepare_install_token(raw_token: str | None = None) -> str | None:
    state_path = install_token_state_path()
    if is_installed():
        state_path.unlink(missing_ok=True)
        os.environ.pop(INSTALL_TOKEN_ENV, None)
        return None
    token = (raw_token or os.environ.get(INSTALL_TOKEN_ENV) or secrets.token_urlsafe(32)).strip()
    if len(token) < 32:
        raise ValueError("Install token must contain at least 32 characters")
    now = int(time.time())
    _write_private_json(
        state_path,
        {
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "created_at": now,
            "expires_at": now + max(300, settings.install_token_ttl_seconds),
        },
    )
    return token


def verify_install_token(token: str | None) -> bool:
    if not token:
        return False
    state_path = install_token_state_path()
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        expires_at = int(state.get("expires_at", 0))
        expected_hash = str(state.get("token_hash", ""))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    if expires_at <= int(time.time()):
        state_path.unlink(missing_ok=True)
        return False
    actual_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return bool(expected_hash and hmac.compare_digest(actual_hash, expected_hash))


def clear_install_token() -> None:
    install_token_state_path().unlink(missing_ok=True)
    os.environ.pop(INSTALL_TOKEN_ENV, None)


@contextmanager
def installation_lock():
    if not _INSTALL_THREAD_LOCK.acquire(blocking=False):
        raise InstallInProgressError("Installation is already in progress")
    lock_file = None
    locked = False
    try:
        lock_path = _install_runtime_path("installing.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a+b")
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise InstallInProgressError("Installation is already in progress") from exc
        yield
    finally:
        if locked and lock_file is not None:
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        if lock_file is not None:
            lock_file.close()
        _INSTALL_THREAD_LOCK.release()


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


def test_database_url(database_url: str) -> None:
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


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
    try:
        with Session() as db:
            for key, value in {
                ADMIN_USERNAME_KEY: username.strip(),
                ADMIN_PASSWORD_HASH_KEY: hash_password(password),
                INSTALLATION_IN_PROGRESS_KEY: datetime.now(timezone.utc).isoformat(),
            }.items():
                setting = db.get(AppSetting, key)
                if setting:
                    setting.value = value
                else:
                    db.add(AppSetting(key=key, value=value))
            password_change_required = db.get(AppSetting, ADMIN_PASSWORD_CHANGE_REQUIRED_KEY)
            if password_change_required:
                db.delete(password_change_required)
            db.commit()
    finally:
        engine.dispose()


def mark_installation_complete(database_url: str) -> None:
    engine = create_database_engine(database_url)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with Session() as db:
            completed_at = datetime.now(timezone.utc).isoformat()
            completed = db.get(AppSetting, INSTALLATION_COMPLETED_KEY)
            if completed:
                completed.value = completed_at
            else:
                db.add(AppSetting(key=INSTALLATION_COMPLETED_KEY, value=completed_at))
            in_progress = db.get(AppSetting, INSTALLATION_IN_PROGRESS_KEY)
            if in_progress:
                db.delete(in_progress)
            db.commit()
    finally:
        engine.dispose()


def _serialize_env_value(value: str) -> str:
    if any(char.isspace() for char in value):
        return json.dumps(value, ensure_ascii=False)
    return value


def _read_env_value(key: str) -> str | None:
    if not ENV_PATH.exists():
        return None
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        env_key, value = line.split("=", 1)
        if env_key.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def _env_contains_key(key: str) -> bool:
    if not ENV_PATH.exists():
        return False
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return any(
        line.split("=", 1)[0].strip() == key
        for line in lines
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    )


def _write_env_atomic(lines: list[str]) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env-", dir=ENV_PATH.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write("\n".join(lines).rstrip() + "\n")
            output.flush()
            os.fsync(output.fileno())
        if os.name == "posix":
            temporary_path.chmod(0o600)
        os.replace(temporary_path, ENV_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_env(updates: dict[str, str], *, remove_keys: set[str] | None = None) -> None:
    removed = remove_keys or set()
    if removed.intersection(updates):
        raise ValueError("An environment key cannot be updated and removed at the same time")
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    consumed: set[str] = set()
    output: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in removed:
            continue
        if key in updates:
            output.append(f"{key}={_serialize_env_value(updates[key])}")
            consumed.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in consumed:
            output.append(f"{key}={_serialize_env_value(value)}")
    _write_env_atomic(output)


def remove_env_keys(keys: set[str]) -> None:
    if ENV_PATH.exists() and any(_env_contains_key(key) for key in keys):
        write_env({}, remove_keys=keys)


def migrate_legacy_admin_password(database_url: str | None = None) -> str:
    legacy_in_process = LEGACY_ADMIN_PASSWORD_ENV in os.environ
    legacy_in_file = _env_contains_key(LEGACY_ADMIN_PASSWORD_ENV)
    legacy_password = os.environ.get(LEGACY_ADMIN_PASSWORD_ENV)
    if legacy_password is None:
        legacy_password = _read_env_value(LEGACY_ADMIN_PASSWORD_ENV)

    engine = create_database_engine(database_url or settings.database_url)
    try:
        if not inspect(engine).has_table(AppSetting.__tablename__):
            return "database-not-initialized"
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        with Session() as db:
            password_setting = db.get(AppSetting, ADMIN_PASSWORD_HASH_KEY)
            if not password_setting or not password_setting.value:
                if not legacy_password:
                    if not _database_has_migrations(engine):
                        return "password-hash-missing"
                    legacy_password = LEGACY_BUILTIN_ADMIN_PASSWORD
                    password_change_required = db.get(AppSetting, ADMIN_PASSWORD_CHANGE_REQUIRED_KEY)
                    if password_change_required:
                        password_change_required.value = "1"
                    else:
                        db.add(AppSetting(key=ADMIN_PASSWORD_CHANGE_REQUIRED_KEY, value="1"))
                    result = "legacy-default-hash-migrated"
                else:
                    result = "password-hash-migrated"
                password_hash = hash_password(legacy_password)
                if password_setting:
                    password_setting.value = password_hash
                else:
                    db.add(AppSetting(key=ADMIN_PASSWORD_HASH_KEY, value=password_hash))
                username_setting = db.get(AppSetting, ADMIN_USERNAME_KEY)
                if not username_setting:
                    legacy_username = (
                        os.environ.get("AGMS_ADMIN_USERNAME")
                        or _read_env_value("AGMS_ADMIN_USERNAME")
                        or settings.admin_username
                    ).strip()
                    db.add(AppSetting(key=ADMIN_USERNAME_KEY, value=legacy_username or "admin"))
                db.commit()
            else:
                result = "password-hash-present"

        if legacy_in_file:
            remove_env_keys({LEGACY_ADMIN_PASSWORD_ENV})
        if legacy_in_process:
            os.environ.pop(LEGACY_ADMIN_PASSWORD_ENV, None)
        return result
    finally:
        engine.dispose()


def write_install_lock(database_type: str, database_url: str, *, state: str = "completed") -> None:
    if state not in {"pending", "completed"}:
        raise ValueError("Invalid installation lock state")
    payload = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "database_type": database_type,
        "database_url_hash": database_url_hash(database_url),
        "state": state,
    }
    _write_private_json(INSTALL_LOCK_PATH, payload)


def request_managed_restart() -> bool:
    if os.environ.get("AGMS_LAUNCHER_MANAGED") != "1":
        return False
    request_path = settings.storage_path / "runtime" / "restart.request"
    try:
        _write_private_json(
            request_path,
            {
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "not_before": time.time() + 3,
                "reason": "first-install",
            },
        )
    except OSError:
        return False
    return True


def perform_install(
    *,
    database_type: str,
    database_url: str,
    admin_username: str,
    admin_password: str,
) -> dict:
    test_database_url(database_url)
    target_engine = create_database_engine(database_url)
    try:
        if _database_is_initialized(target_engine):
            raise ValueError("Target database is already initialized")
    finally:
        target_engine.dispose()
    run_migrations(database_url)
    initialize_admin(database_url, admin_username, admin_password)
    resolved_auth_secret = generate_auth_secret()
    updates = {
        "AGMS_DATABASE_URL": database_url,
        "AGMS_ADMIN_USERNAME": admin_username.strip(),
        "AGMS_AUTH_SECRET": resolved_auth_secret,
        "AGMS_API_KEYS": settings.api_keys or f"default:{generate_api_key()}",
    }
    write_env(updates, remove_keys={LEGACY_ADMIN_PASSWORD_ENV})
    os.environ.pop(LEGACY_ADMIN_PASSWORD_ENV, None)
    ensure_storage_dirs()
    write_install_lock(database_type, database_url, state="pending")
    try:
        mark_installation_complete(database_url)
    except Exception:
        INSTALL_LOCK_PATH.unlink(missing_ok=True)
        raise
    write_install_lock(database_type, database_url, state="completed")
    clear_install_token()
    # The current process has already loaded its database, session secret and
    # API keys. A restart is required even when SQLite keeps the same URL.
    restart_needed = True
    request_managed_restart()
    return {
        "installed": True,
        "database_type": database_type,
        "restart_required": restart_needed,
    }
