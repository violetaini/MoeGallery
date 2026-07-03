from fastapi import APIRouter, HTTPException, status

from app.schemas.install import InstallRequest, InstallResponse, InstallStatus
from app.services.install_service import (
    build_mysql_url,
    build_sqlite_url,
    current_database_is_initialized,
    has_install_lock,
    is_installed,
    perform_install,
    restart_required,
)

router = APIRouter(prefix="/install", tags=["install"])


@router.get("/status", response_model=InstallStatus)
def install_status():
    lock_exists = has_install_lock()
    database_initialized = current_database_is_initialized()
    return {
        "installed": lock_exists or database_initialized,
        "lock_exists": lock_exists,
        "database_initialized": database_initialized,
        "restart_required": restart_required(),
    }


@router.post("", response_model=InstallResponse, status_code=status.HTTP_201_CREATED)
def install(payload: InstallRequest):
    if is_installed():
        raise HTTPException(status_code=409, detail="Application is already installed")
    if payload.database_type == "sqlite":
        database_url = build_sqlite_url(payload.sqlite_path or "")
    else:
        database_url = build_mysql_url(
            payload.mysql_host or "",
            payload.mysql_port,
            payload.mysql_database or "",
            payload.mysql_username or "",
            payload.mysql_password or "",
        )
    try:
        return perform_install(
            database_type=payload.database_type,
            database_url=database_url,
            admin_username=payload.admin_username,
            admin_password=payload.admin_password,
            auth_secret=payload.auth_secret,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Install failed: {exc}") from exc
