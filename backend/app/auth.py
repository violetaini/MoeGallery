import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import auth_secret_fingerprint, parse_api_keys, settings
from app.database import get_db
from app.models import AdminSession


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
    for name, api_key in parse_api_keys(settings.api_keys):
        if hmac.compare_digest(token, api_key):
            return {
                "sub": settings.admin_username,
                "typ": API_KEY_TOKEN_TYPE,
                "api_key_name": name,
                "auth_type": "api_key",
            }
    return None


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
    if session.expires_at < datetime.utcnow():
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


def require_admin(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    session_cookie: Annotated[str | None, Cookie(alias=ADMIN_SESSION_COOKIE)] = None,
) -> dict:
    if credentials and credentials.scheme.lower() == "bearer":
        api_key_admin = verify_api_key(credentials.credentials)
        if api_key_admin:
            return api_key_admin

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
    session.last_seen_at = datetime.utcnow()
    db.commit()
    return {**data, "session_id": session.id}


def optional_admin(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    session_cookie: Annotated[str | None, Cookie(alias=ADMIN_SESSION_COOKIE)] = None,
) -> dict | None:
    if credentials and credentials.scheme.lower() == "bearer":
        api_key_admin = verify_api_key(credentials.credentials)
        if api_key_admin:
            return api_key_admin

    token = _extract_token(credentials, session_cookie)
    if not token:
        return None
    try:
        data = verify_access_token(token)
        session = db.query(AdminSession).filter(AdminSession.token_hash == session_token_hash(token)).first()
        if not _session_is_active(session):
            return None
        session.last_seen_at = datetime.utcnow()
        db.commit()
        return {**data, "session_id": session.id}
    except HTTPException:
        return None
