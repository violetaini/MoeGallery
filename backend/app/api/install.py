import logging
import threading
import time

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.schemas.install import InstallRequest, InstallResponse, InstallStatus
from app.services.install_service import (
    build_mysql_url,
    build_sqlite_url,
    InstallInProgressError,
    installation_lock,
    is_installed,
    perform_install,
    restart_required,
    verify_install_token,
)
from app.config import settings
from app.utils.request_ip import client_ip

router = APIRouter(prefix="/install", tags=["install"])
logger = logging.getLogger(__name__)
_install_attempts: dict[str, list[int]] = {}
_install_attempts_lock = threading.Lock()
_MAX_INSTALL_RATE_LIMIT_KEYS = 4096


def _prune_install_attempts(window_start: int) -> None:
    for key in list(_install_attempts.keys()):
        recent = [timestamp for timestamp in _install_attempts[key] if timestamp >= window_start]
        if recent:
            _install_attempts[key] = recent
        else:
            _install_attempts.pop(key, None)
    if len(_install_attempts) <= _MAX_INSTALL_RATE_LIMIT_KEYS:
        return
    oldest = sorted(
        _install_attempts,
        key=lambda key: max(_install_attempts[key]) if _install_attempts[key] else 0,
    )
    for key in oldest[: len(_install_attempts) - _MAX_INSTALL_RATE_LIMIT_KEYS]:
        _install_attempts.pop(key, None)


def _enforce_install_rate_limit(request: Request) -> None:
    now = int(time.time())
    window_seconds = max(1, settings.install_rate_limit_window_seconds)
    window_start = now - window_seconds
    key = client_ip(request)
    with _install_attempts_lock:
        _prune_install_attempts(window_start)
        recent = _install_attempts.get(key, [])
        if len(recent) >= max(1, settings.install_rate_limit_max_attempts):
            retry_after = max(1, window_seconds - (now - min(recent)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="安装请求过于频繁，请稍后重试",
                headers={"Retry-After": str(retry_after)},
            )


def _record_install_failure(request: Request) -> None:
    now = int(time.time())
    window_start = now - max(1, settings.install_rate_limit_window_seconds)
    key = client_ip(request)
    with _install_attempts_lock:
        _prune_install_attempts(window_start)
        _install_attempts.setdefault(key, []).append(now)


def _clear_install_failures(request: Request) -> None:
    with _install_attempts_lock:
        _install_attempts.pop(client_ip(request), None)


@router.get("/status", response_model=InstallStatus)
def install_status():
    installed = is_installed()
    return {
        "installed": installed,
        "restart_required": restart_required(),
        "token_required": not installed,
    }


@router.post("", response_model=InstallResponse, status_code=status.HTTP_201_CREATED)
def install(
    payload: InstallRequest,
    request: Request,
    install_token: str | None = Header(default=None, alias="X-Install-Token"),
):
    if is_installed():
        raise HTTPException(status_code=409, detail="Application is already installed")
    if not verify_install_token(install_token):
        _enforce_install_rate_limit(request)
        _record_install_failure(request)
        raise HTTPException(status_code=403, detail="安装授权无效或已过期")
    _clear_install_failures(request)
    try:
        with installation_lock():
            if is_installed():
                raise HTTPException(status_code=409, detail="Application is already installed")
            if not verify_install_token(install_token):
                raise HTTPException(status_code=403, detail="安装授权无效或已过期")
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
            return perform_install(
                database_type=payload.database_type,
                database_url=database_url,
                admin_username=payload.admin_username,
                admin_password=payload.admin_password,
            )
    except InstallInProgressError as exc:
        raise HTTPException(status_code=423, detail="安装正在进行，请勿重复提交") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("First installation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=400, detail="安装失败，请检查数据库配置和服务日志") from exc
