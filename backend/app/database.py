from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


SQLITE_WAL_AUTOCHECKPOINT_PAGES = 1000
MYSQL_RESERVED_CONNECTION_SLOTS = 4


def _database_dialect_name(database_url: str) -> str:
    return make_url(database_url).get_backend_name()


def _is_file_sqlite_database(database_url: str) -> bool:
    url = make_url(database_url)
    return url.get_backend_name() == "sqlite" and bool(url.database and url.database != ":memory:")


def _install_sqlite_pragmas(engine: Engine, database_url: str) -> None:
    is_file_database = _is_file_sqlite_database(database_url)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
            if is_file_database:
                cursor.execute("PRAGMA journal_mode=WAL").fetchone()
                cursor.execute(f"PRAGMA synchronous={settings.sqlite_synchronous}")
                cursor.execute(f"PRAGMA wal_autocheckpoint={SQLITE_WAL_AUTOCHECKPOINT_PAGES}")
        finally:
            cursor.close()


def create_database_engine(database_url: str) -> Engine:
    dialect = _database_dialect_name(database_url)
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {"future": True}
    if dialect == "sqlite":
        connect_args["check_same_thread"] = False
    elif dialect in {"mysql", "mariadb"}:
        connect_args.update(
            {
                "charset": "utf8mb4",
                "connect_timeout": settings.mysql_connect_timeout_seconds,
                "read_timeout": settings.mysql_read_timeout_seconds,
                "write_timeout": settings.mysql_write_timeout_seconds,
            }
        )
        engine_kwargs.update(
            {
                "pool_pre_ping": True,
                "pool_recycle": settings.mysql_pool_recycle_seconds,
                "pool_size": settings.mysql_pool_size,
                "max_overflow": settings.mysql_max_overflow,
                "pool_timeout": settings.mysql_pool_timeout_seconds,
                "pool_use_lifo": True,
            }
        )

    engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)
    if dialect == "sqlite":
        _install_sqlite_pragmas(engine, database_url)
    return engine


def _pool_stats() -> dict[str, int | None]:
    pool = engine.pool
    def value(name: str) -> int | None:
        method = getattr(pool, name, None)
        if not callable(method):
            return None
        try:
            return int(method())
        except Exception:
            return None

    return {
        "size": value("size"),
        "checked_in": value("checkedin"),
        "checked_out": value("checkedout"),
        "overflow": value("overflow"),
    }


def database_concurrency_info(db: Session | None = None) -> dict[str, object]:
    dialect = engine.dialect.name
    info: dict[str, object] = {
        "dialect": dialect,
        "pool": _pool_stats(),
        "restart_required_for_pool_changes": dialect in {"mysql", "mariadb"},
    }
    if dialect == "sqlite":
        pragma_values: dict[str, object] = {}
        if db is not None:
            try:
                pragma_values = {
                    "journal_mode": str(db.connection().exec_driver_sql("PRAGMA journal_mode").scalar() or "").lower(),
                    "busy_timeout_ms": int(db.connection().exec_driver_sql("PRAGMA busy_timeout").scalar() or 0),
                    "synchronous": int(db.connection().exec_driver_sql("PRAGMA synchronous").scalar() or 0),
                }
            except Exception:
                pragma_values = {}
        info.update(
            {
                "profile": "sqlite_wal",
                "busy_timeout_ms": pragma_values.get("busy_timeout_ms", settings.sqlite_busy_timeout_ms),
                "journal_mode": pragma_values.get("journal_mode", "unknown"),
                "synchronous": pragma_values.get("synchronous", settings.sqlite_synchronous.lower()),
                "wal_autocheckpoint_pages": SQLITE_WAL_AUTOCHECKPOINT_PAGES,
                "worker_limit": settings.sqlite_upload_worker_limit,
            }
        )
    elif dialect in {"mysql", "mariadb"}:
        capacity = settings.mysql_pool_size + settings.mysql_max_overflow
        info.update(
            {
                "profile": "mysql_pool",
                "pool_size": settings.mysql_pool_size,
                "max_overflow": settings.mysql_max_overflow,
                "pool_capacity": capacity,
                "pool_timeout_seconds": settings.mysql_pool_timeout_seconds,
                "pool_recycle_seconds": settings.mysql_pool_recycle_seconds,
                "worker_limit": max(1, capacity - MYSQL_RESERVED_CONNECTION_SLOTS),
            }
        )
    else:
        info.update({"profile": "generic", "worker_limit": 96})
    return info


engine = create_database_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
