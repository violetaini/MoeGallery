import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import auth_secret_fingerprint, settings
from app.database import get_db
from app.models import AdminSession
from app.services.api_key_service import (
    ALL_API_KEY_SCOPES,
    configured_api_key,
    find_active_api_key_policy,
    policy_scopes,
    record_api_key_use,
)
from app.utils.request_ip import client_ip
from app.utils.time import utcnow_naive


security = HTTPBearer(auto_error=False)
AUTH_TOKEN_TYPE = "agms-admin-access"
MAX_BEARER_TOKEN_LENGTH = 4096
ADMIN_SESSION_COOKIE = "agms_admin_session"
ADMIN_CSRF_COOKIE = "agms_admin_csrf"
API_KEY_TOKEN_TYPE = "agms-operations-api-key"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: str) -> str:
    digest = hmac.new(settings.auth_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def _secret_version() -> str:
    return auth_secret_fingerprint(settings.auth_secret)


def _invalid_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_api_key(token: str) -> dict | None:
    if not token or len(token) > MAX_BEARER_TOKEN_LENGTH:
        return None
    matched = configured_api_key(token)
    if matched is None:
        return None
    return {
        "sub": settings.admin_username,
        "typ": API_KEY_TOKEN_TYPE,
        "api_key_name": matched[0],
        "auth_type": "api_key",
    }


def create_access_token(username: str) -> str:
    now = int(time.time())
    payload = _b64encode(
        json.dumps(
            {
                "sub": username,
                "typ": AUTH_TOKEN_TYPE,
                "jti": secrets.token_urlsafe(18),
                "sv": _secret_version(),
                "iat": now,
                "nbf": now,
                "exp": now + settings.auth_token_ttl_seconds,
                "iss": settings.auth_issuer,
                "aud": settings.auth_audience,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload}.{_sign(payload)}"


def verify_access_token(token: str) -> dict:
    try:
        if len(token) > MAX_BEARER_TOKEN_LENGTH:
            raise ValueError("Token too long")
        parts = token.split(".")
        if len(parts) != 2:
            raise ValueError("Malformed token")
        payload, signature = parts
        expected = _sign(payload)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Bad signature")
        data = json.loads(_b64decode(payload))
        if not isinstance(data, dict):
            raise ValueError("Bad payload")
        now = int(time.time())
        if data.get("typ") != AUTH_TOKEN_TYPE:
            raise ValueError("Bad token type")
        if data.get("sv") != _secret_version():
            raise ValueError("Bad secret version")
        if data.get("iss") != settings.auth_issuer:
            raise ValueError("Bad issuer")
        if data.get("aud") != settings.auth_audience:
            raise ValueError("Bad audience")
        if int(data.get("nbf", 0)) > now:
            raise ValueError("Not yet valid")
        if int(data.get("iat", 0)) > now + 60:
            raise ValueError("Issued in the future")
        if int(data.get("exp", 0)) < now:
            raise ValueError("Expired token")
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        raise _invalid_token()
    return data


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_is_active(session: AdminSession | None) -> bool:
    if not session:
        return False
    if session.revoked_at is not None:
        return False
    if session.expires_at < utcnow_naive():
        return False
    return True


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    session_cookie: str | None,
) -> str | None:
    if session_cookie:
        return session_cookie
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return None


def _api_key_admin(
    db: Session,
    token: str,
    required_scopes: tuple[str, ...],
    ip_address: str | None,
) -> dict:
    policy = find_active_api_key_policy(db, token)
    if policy is None:
        raise _invalid_token()
    scopes = policy_scopes(policy)
    missing = [scope for scope in required_scopes if scope not in scopes]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API Key lacks required permission: {missing[0]}",
        )
    record_api_key_use(db, policy, ip_address)
    return {
        "sub": settings.admin_username,
        "typ": API_KEY_TOKEN_TYPE,
        "api_key_id": policy.id,
        "api_key_name": policy.name,
        "api_key_scopes": scopes,
        "auth_type": "api_key",
    }


def _require_admin(
    required_scopes: tuple[str, ...],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    session_cookie: Annotated[str | None, Cookie(alias=ADMIN_SESSION_COOKIE)] = None,
) -> dict:
    if credentials and credentials.scheme.lower() == "bearer":
        if verify_api_key(credentials.credentials):
            return _api_key_admin(
                db,
                credentials.credentials,
                required_scopes,
                client_ip(request),
            )

    token = _extract_token(credentials, session_cookie)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    data = verify_access_token(token)
    session = db.query(AdminSession).filter(AdminSession.token_hash == session_token_hash(token)).first()
    if not _session_is_active(session):
        raise _invalid_token()
    session.last_seen_at = utcnow_naive()
    db.commit()
    return {**data, "session_id": session.id}


def require_api_scopes(*required_scopes: str):
    scopes = tuple(required_scopes)

    def dependency(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
        session_cookie: Annotated[str | None, Cookie(alias=ADMIN_SESSION_COOKIE)] = None,
    ) -> dict:
        return _require_admin(scopes, request, db, credentials, session_cookie)

    dependency.__name__ = "require_api_scopes_" + ("_".join(scope.replace(":", "_") for scope in scopes) or "authenticated")
    return dependency


def optional_api_scopes(*required_scopes: str):
    scopes = tuple(required_scopes)

    def dependency(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
        session_cookie: Annotated[str | None, Cookie(alias=ADMIN_SESSION_COOKIE)] = None,
    ) -> dict | None:
        return _optional_admin(scopes, request, db, credentials, session_cookie)

    dependency.__name__ = "optional_api_scopes_" + ("_".join(scope.replace(":", "_") for scope in scopes) or "authenticated")
    return dependency


def authenticate_optional_request(
    request: Request,
    db: Session,
    *required_scopes: str,
) -> dict | None:
    credentials = None
    authorization = request.headers.get("authorization", "").strip()
    if authorization:
        scheme, separator, token = authorization.partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not separator or not token:
            raise _invalid_token()
        credentials = HTTPAuthorizationCredentials(scheme=scheme, credentials=token)
    return _optional_admin(
        tuple(required_scopes),
        request,
        db,
        credentials,
        request.cookies.get(ADMIN_SESSION_COOKIE),
    )


def _optional_admin(
    required_scopes: tuple[str, ...],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    session_cookie: Annotated[str | None, Cookie(alias=ADMIN_SESSION_COOKIE)] = None,
) -> dict | None:
    if credentials and credentials.scheme.lower() == "bearer":
        if verify_api_key(credentials.credentials):
            return _api_key_admin(
                db,
                credentials.credentials,
                required_scopes,
                client_ip(request),
            )
        data = verify_access_token(credentials.credentials)
        session = (
            db.query(AdminSession)
            .filter(AdminSession.token_hash == session_token_hash(credentials.credentials))
            .first()
        )
        if not _session_is_active(session):
            raise _invalid_token()
        session.last_seen_at = utcnow_naive()
        db.commit()
        return {**data, "session_id": session.id}

    token = session_cookie
    if not token:
        return None
    try:
        data = verify_access_token(token)
        session = db.query(AdminSession).filter(AdminSession.token_hash == session_token_hash(token)).first()
        if not _session_is_active(session):
            return None
        session.last_seen_at = utcnow_naive()
        db.commit()
        return {**data, "session_id": session.id}
    except HTTPException:
        return None


require_authenticated_admin = require_api_scopes()
require_library_read = require_api_scopes("library:read")
require_uploads_manage = require_api_scopes("uploads:manage")
require_library_write = require_api_scopes("library:write")
require_library_delete = require_api_scopes("library:delete")
require_system_read = require_api_scopes("system:read")
require_settings_manage = require_api_scopes("settings:manage")
require_updates_read = require_api_scopes("updates:read")
require_updates_run = require_api_scopes("updates:run")
require_api_keys_manage = require_api_scopes("api_keys:manage")
optional_admin = optional_api_scopes("library:read")

# Conservative fallback for any protected route that has not been assigned a narrower scope.
require_admin = require_api_scopes(*ALL_API_KEY_SCOPES)
