from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import generate_api_key, parse_api_keys, settings
from app.models import ApiKeyPolicy, AppSetting
from app.services.install_service import write_env


API_KEY_SCOPE_DEFINITIONS = (
    ("library:read", "媒体库读取", "读取私有、隐藏图片及受保护的媒体文件。"),
    ("uploads:manage", "图片上传", "上传、预览、重复校验并查看上传任务。"),
    ("library:write", "资料维护", "创建和修改图片元数据、作品、角色与分级。"),
    ("library:delete", "永久删除", "删除图片、作品、角色与分级。"),
    ("system:read", "系统只读", "读取统计、系统健康与 API 文档。"),
    ("settings:manage", "系统设置", "修改后台偏好、管理员资料和登录密钥。"),
    ("updates:read", "更新只读", "检查版本并查看更新任务。"),
    ("updates:run", "执行更新", "创建校验或正式更新任务。"),
    ("api_keys:manage", "API Key 管理", "创建、修改、撤销和重置 API Key。"),
)
ALL_API_KEY_SCOPES = tuple(item[0] for item in API_KEY_SCOPE_DEFINITIONS)
API_KEY_SCOPE_SET = frozenset(ALL_API_KEY_SCOPES)
API_KEY_POLICY_MIGRATION_KEY = "security.api_key_policy_migration_v1"
API_KEY_LAST_USED_WRITE_INTERVAL = timedelta(minutes=5)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def api_key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def normalize_api_key_scopes(scopes: list[str] | tuple[str, ...]) -> list[str]:
    requested = set(scopes)
    unknown = sorted(requested - API_KEY_SCOPE_SET)
    if unknown:
        raise ValueError(f"Unknown API Key scope: {unknown[0]}")
    return [scope for scope in ALL_API_KEY_SCOPES if scope in requested]


def policy_scopes(policy: ApiKeyPolicy) -> list[str]:
    try:
        value = json.loads(policy.scopes_json)
    except (TypeError, json.JSONDecodeError):
        value = []
    return normalize_api_key_scopes(value if isinstance(value, list) else [])


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _set_policy_scopes(policy: ApiKeyPolicy, scopes: list[str] | tuple[str, ...]) -> None:
    policy.scopes_json = json.dumps(normalize_api_key_scopes(scopes), separators=(",", ":"))


def ensure_legacy_api_key_policies(db: Session) -> None:
    for attempt in range(2):
        if db.get(AppSetting, API_KEY_POLICY_MIGRATION_KEY):
            return
        for name, key in parse_api_keys(settings.api_keys):
            key_digest = api_key_hash(key)
            policy = db.scalar(select(ApiKeyPolicy).where(ApiKeyPolicy.key_hash == key_digest))
            if policy is None:
                policy = ApiKeyPolicy(key_hash=key_digest, name=name, scopes_json="[]")
                _set_policy_scopes(policy, ALL_API_KEY_SCOPES)
                db.add(policy)
        db.add(AppSetting(key=API_KEY_POLICY_MIGRATION_KEY, value="completed"))
        try:
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise


def configured_api_key(token: str) -> tuple[str, str] | None:
    for name, key in parse_api_keys(settings.api_keys):
        if hmac.compare_digest(token, key):
            return name, key
    return None


def find_active_api_key_policy(db: Session, token: str) -> ApiKeyPolicy | None:
    configured = configured_api_key(token)
    if configured is None:
        return None
    ensure_legacy_api_key_policies(db)
    policy = db.scalar(select(ApiKeyPolicy).where(ApiKeyPolicy.key_hash == api_key_hash(configured[1])))
    now = _utc_now()
    if policy is None or policy.revoked_at is not None:
        return None
    if policy.expires_at is not None and policy.expires_at <= now:
        return None
    return policy


def record_api_key_use(db: Session, policy: ApiKeyPolicy, ip_address: str | None) -> None:
    now = _utc_now()
    should_write = policy.last_used_at is None or now - policy.last_used_at >= API_KEY_LAST_USED_WRITE_INTERVAL
    if ip_address and policy.last_used_ip != ip_address:
        should_write = True
    if not should_write:
        return
    policy.last_used_at = now
    policy.last_used_ip = (ip_address or "")[:64] or None
    db.commit()


def api_key_scope_catalog() -> list[dict[str, str]]:
    return [{"value": value, "label": label, "description": description} for value, label, description in API_KEY_SCOPE_DEFINITIONS]


def _policy_status(policy: ApiKeyPolicy) -> str:
    if policy.revoked_at is not None:
        return "revoked"
    if policy.expires_at is not None and policy.expires_at <= _utc_now():
        return "expired"
    return "active"


def serialize_api_key(policy: ApiKeyPolicy, key: str) -> dict[str, object]:
    scopes = policy_scopes(policy)
    return {
        "id": policy.id,
        "name": policy.name,
        "key": key,
        "scopes": scopes,
        "full_access": set(scopes) == API_KEY_SCOPE_SET,
        "expires_at": policy.expires_at,
        "last_used_at": policy.last_used_at,
        "last_used_ip": policy.last_used_ip,
        "status": _policy_status(policy),
    }


def list_configured_api_keys(db: Session) -> list[dict[str, object]]:
    ensure_legacy_api_key_policies(db)
    result: list[dict[str, object]] = []
    for _configured_name, key in parse_api_keys(settings.api_keys):
        policy = db.scalar(select(ApiKeyPolicy).where(ApiKeyPolicy.key_hash == api_key_hash(key)))
        if policy is not None and policy.revoked_at is None:
            result.append(serialize_api_key(policy, key))
    return result


def _write_configured_api_keys(items: list[tuple[str, str]]) -> None:
    value = ",".join(f"{name}:{key}" for name, key in items)
    write_env({"AGMS_API_KEYS": value})
    settings.api_keys = value


def _validate_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("API Key name is required")
    if any(char in normalized for char in ":,;\r\n"):
        raise ValueError("API Key name cannot contain colon, comma, semicolon, or line breaks")
    return normalized


def _validate_expiration(expires_at: datetime | None) -> datetime | None:
    normalized = _utc_naive(expires_at)
    if normalized is not None and normalized <= _utc_now():
        raise ValueError("API Key expiration must be in the future")
    return normalized


def create_api_key(
    db: Session,
    *,
    name: str,
    scopes: list[str],
    expires_at: datetime | None,
) -> dict[str, object]:
    ensure_legacy_api_key_policies(db)
    key = generate_api_key()
    policy = ApiKeyPolicy(
        key_hash=api_key_hash(key),
        name=_validate_name(name),
        scopes_json="[]",
        expires_at=_validate_expiration(expires_at),
    )
    _set_policy_scopes(policy, scopes)
    db.add(policy)
    db.flush()
    old_items = parse_api_keys(settings.api_keys)
    try:
        _write_configured_api_keys([*old_items, (policy.name, key)])
        db.commit()
    except Exception:
        db.rollback()
        _write_configured_api_keys(old_items)
        raise
    db.refresh(policy)
    return serialize_api_key(policy, key)


def update_api_key_policy(
    db: Session,
    policy_id: int,
    *,
    name: str,
    scopes: list[str],
    expires_at: datetime | None,
) -> dict[str, object] | None:
    ensure_legacy_api_key_policies(db)
    policy = db.get(ApiKeyPolicy, policy_id)
    if policy is None or policy.revoked_at is not None:
        return None
    configured = next(
        ((configured_name, key) for configured_name, key in parse_api_keys(settings.api_keys) if api_key_hash(key) == policy.key_hash),
        None,
    )
    if configured is None:
        return None
    policy.name = _validate_name(name)
    policy.expires_at = _validate_expiration(expires_at)
    _set_policy_scopes(policy, scopes)
    old_items = parse_api_keys(settings.api_keys)
    next_items = [(policy.name if api_key_hash(key) == policy.key_hash else item_name, key) for item_name, key in old_items]
    try:
        _write_configured_api_keys(next_items)
        db.commit()
    except Exception:
        db.rollback()
        _write_configured_api_keys(old_items)
        raise
    db.refresh(policy)
    return serialize_api_key(policy, configured[1])


def rotate_api_key(db: Session, policy_id: int) -> dict[str, object] | None:
    ensure_legacy_api_key_policies(db)
    policy = db.get(ApiKeyPolicy, policy_id)
    if policy is None or policy.revoked_at is not None:
        return None
    old_items = parse_api_keys(settings.api_keys)
    configured = next(
        ((configured_name, key) for configured_name, key in old_items if api_key_hash(key) == policy.key_hash),
        None,
    )
    if configured is None:
        return None

    new_key = generate_api_key()
    old_key_hash = policy.key_hash
    policy.key_hash = api_key_hash(new_key)
    policy.last_used_at = None
    policy.last_used_ip = None
    next_items = [
        (policy.name, new_key) if api_key_hash(key) == old_key_hash else (item_name, key)
        for item_name, key in old_items
    ]
    try:
        _write_configured_api_keys(next_items)
        db.commit()
    except Exception:
        db.rollback()
        _write_configured_api_keys(old_items)
        raise
    db.refresh(policy)
    return serialize_api_key(policy, new_key)


def revoke_api_key(db: Session, policy_id: int) -> bool:
    ensure_legacy_api_key_policies(db)
    policy = db.get(ApiKeyPolicy, policy_id)
    if policy is None or policy.revoked_at is not None:
        return False
    old_items = parse_api_keys(settings.api_keys)
    next_items = [(name, key) for name, key in old_items if api_key_hash(key) != policy.key_hash]
    if len(next_items) == len(old_items):
        return False
    policy.revoked_at = _utc_now()
    try:
        _write_configured_api_keys(next_items)
        db.commit()
    except Exception:
        db.rollback()
        _write_configured_api_keys(old_items)
        raise
    return True


def reset_api_keys(db: Session) -> list[dict[str, object]]:
    ensure_legacy_api_key_policies(db)
    old_items = parse_api_keys(settings.api_keys)
    old_policies = db.scalars(select(ApiKeyPolicy).where(ApiKeyPolicy.revoked_at.is_(None))).all()
    now = _utc_now()
    for policy in old_policies:
        policy.revoked_at = now
    key = generate_api_key()
    policy = ApiKeyPolicy(key_hash=api_key_hash(key), name="default", scopes_json="[]")
    _set_policy_scopes(policy, ALL_API_KEY_SCOPES)
    db.add(policy)
    db.flush()
    try:
        _write_configured_api_keys([("default", key)])
        db.commit()
    except Exception:
        db.rollback()
        _write_configured_api_keys(old_items)
        raise
    db.refresh(policy)
    return [serialize_api_key(policy, key)]
