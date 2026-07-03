import ipaddress
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
_MAX_LOGIN_RATE_LIMIT_KEYS = 4096


def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    raw = (value or "").strip().strip('"')
    if not raw:
        return None
    if raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.index("]")]
    elif raw.count(":") == 1 and "." in raw:
        host, port = raw.rsplit(":", 1)
        if port.isdigit():
            raw = host
    try:
        return ipaddress.ip_address(raw)
    except ValueError:
        return None


def _peer_host(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def _peer_can_set_forwarded_headers(request: Request) -> bool:
    peer_ip = _parse_ip(_peer_host(request))
    return bool(peer_ip and (peer_ip.is_loopback or peer_ip.is_private))


def _client_ip(request: Request) -> str:
    peer = _peer_host(request)
    peer_ip = _parse_ip(peer)
    if _peer_can_set_forwarded_headers(request):
        forwarded = request.headers.get("x-forwarded-for", "")
        for raw_part in reversed(forwarded.split(",")):
            forwarded_ip = _parse_ip(raw_part)
            if forwarded_ip:
                return str(forwarded_ip)
        real_ip = _parse_ip(request.headers.get("x-real-ip"))
        if real_ip:
            return str(real_ip)
    return str(peer_ip) if peer_ip else peer


def _normalize_login_username(username: str | None) -> str:
    return (username or "").strip().casefold()


def _login_rate_limit_keys(request: Request, username: str | None) -> list[str]:
    keys = [f"ip:{_client_ip(request)}"]
    normalized_username = _normalize_login_username(username)
    if normalized_username:
        keys.append(f"user:{normalized_username}")
    return keys


def _prune_login_attempts(window_start: int) -> None:
    for key in list(_login_attempts.keys()):
        recent = [ts for ts in _login_attempts[key] if ts >= window_start]
        if recent:
            _login_attempts[key] = recent
        else:
            _login_attempts.pop(key, None)
    if len(_login_attempts) <= _MAX_LOGIN_RATE_LIMIT_KEYS:
        return
    keys_by_latest_attempt = sorted(
        _login_attempts,
        key=lambda key: max(_login_attempts[key]) if _login_attempts[key] else 0,
    )
    for key in keys_by_latest_attempt[: len(_login_attempts) - _MAX_LOGIN_RATE_LIMIT_KEYS]:
        _login_attempts.pop(key, None)


def _enforce_login_rate_limit(request: Request, username: str | None) -> None:
    now = int(time.time())
    window_seconds = max(1, settings.login_rate_limit_window_seconds)
    max_attempts = max(1, settings.login_rate_limit_max_attempts)
    window_start = now - window_seconds
    retry_after = 0
    with _login_attempts_lock:
        _prune_login_attempts(window_start)
        for key in _login_rate_limit_keys(request, username):
            recent = [ts for ts in _login_attempts.get(key, []) if ts >= window_start]
            _login_attempts[key] = recent
            if len(recent) >= max_attempts:
                retry_after = max(retry_after, max(1, window_seconds - (now - min(recent))))
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )


def _record_login_failure(request: Request, username: str | None) -> None:
    now = int(time.time())
    window_start = now - max(1, settings.login_rate_limit_window_seconds)
    with _login_attempts_lock:
        _prune_login_attempts(window_start)
        for key in _login_rate_limit_keys(request, username):
            attempts = _login_attempts.setdefault(key, [])
            attempts.append(now)


def _clear_login_failures(request: Request, username: str | None) -> None:
    with _login_attempts_lock:
        for key in _login_rate_limit_keys(request, username):
            _login_attempts.pop(key, None)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    _enforce_login_rate_limit(request, payload.username)
    account = authenticate_admin(db, payload.username, payload.password)
    if not account:
        _record_login_failure(request, payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    _clear_login_failures(request, payload.username)
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
