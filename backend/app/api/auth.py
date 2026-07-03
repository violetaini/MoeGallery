import threading
import time
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import ADMIN_SESSION_COOKIE, require_admin
from app.config import settings
from app.database import get_db
from app.schemas.auth import AuthUser, LoginRequest, LoginResponse
from app.services.admin_account_service import authenticate_admin, get_admin_account
from app.services.auth_session_service import (
    clear_admin_session_cookie,
    create_admin_session,
    revoke_session,
    set_admin_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_login_attempts: dict[str, list[int]] = {}
_login_attempts_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_login_rate_limit(request: Request) -> None:
    now = int(time.time())
    window_start = now - settings.login_rate_limit_window_seconds
    ip = _client_ip(request)
    with _login_attempts_lock:
        recent = [ts for ts in _login_attempts.get(ip, []) if ts >= window_start]
        _login_attempts[ip] = recent
        if len(recent) >= settings.login_rate_limit_max_attempts:
            raise HTTPException(status_code=429, detail="Too many login attempts")


def _record_login_failure(request: Request) -> None:
    ip = _client_ip(request)
    with _login_attempts_lock:
        attempts = _login_attempts.setdefault(ip, [])
        attempts.append(int(time.time()))


def _clear_login_failures(request: Request) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(_client_ip(request), None)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    _enforce_login_rate_limit(request)
    account = authenticate_admin(db, payload.username, payload.password)
    if not account:
        _record_login_failure(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    _clear_login_failures(request)
    token, _session = create_admin_session(
        db,
        username=account.username,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    db.commit()
    set_admin_session_cookie(response, token)
    return {
        "access_token": "",
        "expires_in": settings.auth_token_ttl_seconds,
        "username": account.username,
        "avatar_image_id": account.avatar_image_id,
        "avatar_image": account.avatar_image,
    }


@router.post("/logout")
def logout(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    session_cookie: Annotated[str | None, Cookie(alias=ADMIN_SESSION_COOKIE)] = None,
):
    revoke_session(db, token=session_cookie)
    db.commit()
    clear_admin_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=AuthUser)
def me(
    admin: Annotated[dict, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    account = get_admin_account(db)
    return {
        "username": account.username if admin.get("auth_type") == "api_key" else admin["sub"],
        "avatar_image_id": account.avatar_image_id,
        "avatar_image": account.avatar_image,
    }
