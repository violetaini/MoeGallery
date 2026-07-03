from datetime import datetime, timedelta

from fastapi import Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth import ADMIN_CSRF_COOKIE, ADMIN_SESSION_COOKIE, create_access_token, session_token_hash
from app.config import generate_auth_secret, settings
from app.models import AdminSession
from app.services.install_service import write_env


def create_admin_session(
    db: Session,
    *,
    username: str,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[str, AdminSession]:
    token = create_access_token(username)
    now = datetime.utcnow()
    session = AdminSession(
        token_hash=session_token_hash(token),
        username=username,
        user_agent=(user_agent or "")[:500] or None,
        ip_address=(ip_address or "")[:64] or None,
        expires_at=now + timedelta(seconds=settings.auth_token_ttl_seconds),
        last_seen_at=now,
    )
    db.add(session)
    db.flush()
    return token, session


def set_admin_session_cookie(response: Response, token: str) -> None:
    csrf_token = token.split(".", 1)[0][-32:]
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=ADMIN_CSRF_COOKIE,
        value=csrf_token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_admin_session_cookie(response: Response) -> None:
    response.delete_cookie(key=ADMIN_SESSION_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")
    response.delete_cookie(key=ADMIN_CSRF_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")


def revoke_session(db: Session, token: str | None = None, session_id: int | None = None) -> int:
    now = datetime.utcnow()
    query = db.query(AdminSession).filter(AdminSession.revoked_at.is_(None))
    if token:
        query = query.filter(AdminSession.token_hash == session_token_hash(token))
    elif session_id:
        query = query.filter(AdminSession.id == session_id)
    else:
        return 0
    count = 0
    for session in query.all():
        session.revoked_at = now
        count += 1
    return count


def revoke_all_sessions(db: Session) -> int:
    now = datetime.utcnow()
    result = db.execute(
        update(AdminSession)
        .where(AdminSession.revoked_at.is_(None))
        .values(revoked_at=now, updated_at=now)
    )
    return int(result.rowcount or 0)


def rotate_auth_secret(db: Session) -> dict:
    new_secret = generate_auth_secret()
    write_env({"AGMS_AUTH_SECRET": new_secret})
    settings.auth_secret = new_secret
    revoked_count = revoke_all_sessions(db)
    return {"rotated": True, "revoked_sessions": revoked_count}
