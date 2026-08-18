from __future__ import annotations

import ipaddress
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import AppSetting, CdnWarmTask, Image
from app.services.media_delivery_service import build_media_url
from app.utils.time import utcnow_naive

logger = logging.getLogger(__name__)

CDN_WARM_ENABLED_KEY = "cdn_warm.enabled"
CDN_WARM_BASE_URL_KEY = "cdn_warm.base_url"
CDN_WARM_AUTO_UPLOADS_KEY = "cdn_warm.auto_uploads"

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_RETRY_WAIT = "retry_wait"
TASK_STATUS_SUCCESS = "success"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_SKIPPED = "skipped"
TERMINAL_TASK_STATUSES = (TASK_STATUS_SUCCESS, TASK_STATUS_FAILED, TASK_STATUS_SKIPPED)

SUPPORTED_PROVIDERS = {"esa", "edgeone", "cloudflare"}
CACHE_HIT_STATUSES = {"HIT", "REVALIDATED", "REFRESHHIT"}
CACHE_NOT_CACHEABLE_STATUSES = {"BYPASS", "DYNAMIC", "NONE"}
WARMABLE_VARIANTS = {"thumbnail", "preview"}
MAX_WARM_BYTES = 8 * 1024 * 1024
WORKER_POLL_SECONDS = 2.0
WORKER_TASK_INTERVAL_SECONDS = 0.5
REWARM_SCAN_INTERVAL_SECONDS = 30 * 60
REWARM_LEAD_SECONDS = 5 * 60
MAX_RECENT_TASKS = 16

BROWSER_HEADERS = {
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "DNT": "1",
    "Sec-CH-UA": '"Not_A Brand";v="99", "Google Chrome";v="131", "Chromium";v="131"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None
_worker_shutdown = threading.Event()
_worker_wakeup = threading.Event()
_maintenance_lock = threading.Lock()
_last_rewarm_scan_at: datetime | None = None


@dataclass(frozen=True)
class CdnFetchResult:
    provider: str
    cache_status: str
    response_status: int | None
    response_bytes: int
    error_code: str | None = None
    error_message: str | None = None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def utcnow() -> datetime:
    return utcnow_naive()


def _get_value(db: Session, key: str, default: str = "") -> str:
    setting = db.get(AppSetting, key)
    return setting.value if setting else default


def _set_value(db: Session, key: str, value: str) -> None:
    setting = db.get(AppSetting, key)
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _as_bool(value: str, default: bool = False) -> bool:
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    return default


def normalize_cdn_warm_base_url(value: str | None) -> str:
    normalized = (value or "").strip().rstrip("/")
    if not normalized:
        return ""
    if len(normalized) > 500 or any(char.isspace() for char in normalized):
        raise ValueError("CDN 预热域名格式无效")
    parsed = urllib.parse.urlsplit(normalized)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("CDN 预热必须使用 HTTPS 域名，例如 https://cdn.example.com")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("CDN 预热域名不能包含路径、参数或片段")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".local") or "." not in hostname:
        raise ValueError("CDN 预热不支持 localhost、本地域名或未绑定域名")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("CDN 预热必须使用已绑定的域名，不能使用 127.0.0.1、内网或公网 IP")
    if parsed.port not in {None, 443}:
        raise ValueError("CDN 预热仅支持 HTTPS 默认端口")
    return f"https://{hostname}"


def get_cdn_warm_config(db: Session) -> dict[str, object]:
    raw_base_url = _get_value(db, CDN_WARM_BASE_URL_KEY)
    try:
        base_url = normalize_cdn_warm_base_url(raw_base_url)
        valid = bool(base_url)
        validation_message = ""
    except ValueError as exc:
        base_url = ""
        valid = False
        validation_message = str(exc)
    return {
        "enabled": _as_bool(_get_value(db, CDN_WARM_ENABLED_KEY), False),
        "base_url": base_url,
        "auto_new_uploads": _as_bool(_get_value(db, CDN_WARM_AUTO_UPLOADS_KEY, "true"), True),
        "valid": valid,
        "validation_message": validation_message,
    }


def update_cdn_warm_config(
    db: Session,
    *,
    enabled: bool,
    base_url: str,
    auto_new_uploads: bool,
) -> dict[str, object]:
    normalized = normalize_cdn_warm_base_url(base_url)
    if enabled and not normalized:
        raise ValueError("启用 CDN 预热前必须填写已绑定的 HTTPS CDN 域名")
    _set_value(db, CDN_WARM_ENABLED_KEY, "true" if enabled else "false")
    _set_value(db, CDN_WARM_BASE_URL_KEY, normalized)
    _set_value(db, CDN_WARM_AUTO_UPLOADS_KEY, "true" if auto_new_uploads else "false")
    return get_cdn_warm_config(db)


def seed_existing_public_thumbnails(db: Session) -> dict[str, int]:
    images = db.scalars(
        select(Image).where(Image.is_public.is_(True), Image.rating != "hidden").order_by(Image.id)
    ).all()
    return enqueue_public_images(db, images, variant="thumbnail", force_retry=True)


def _header_value(headers, name: str) -> str:
    if isinstance(headers, dict):
        wanted = name.lower()
        for key, value in headers.items():
            if str(key).lower() == wanted:
                return str(value or "")
    getter = getattr(headers, "get", None)
    value = getter(name, "") if callable(getter) else ""
    return str(value or "")


def detect_cdn_provider(headers) -> tuple[str, str]:
    server = _header_value(headers, "server").lower()
    if _header_value(headers, "x-site-cache-status") or _header_value(headers, "x-swift-cachetime") or server == "esa":
        return "esa", _header_value(headers, "x-site-cache-status").upper() or "UNKNOWN"
    if _header_value(headers, "eo-cache-status") or "tencentedgeone" in server:
        return "edgeone", _header_value(headers, "eo-cache-status").upper() or "UNKNOWN"
    if _header_value(headers, "cf-cache-status") or _header_value(headers, "cf-ray"):
        return "cloudflare", _header_value(headers, "cf-cache-status").upper() or "UNKNOWN"
    return "direct", "DIRECT"


def _browser_headers(base_url: str) -> dict[str, str]:
    headers = dict(BROWSER_HEADERS)
    headers["Referer"] = f"{base_url}/"
    return headers


def browser_fetch(url: str, *, base_url: str, method: str = "GET", max_bytes: int = MAX_WARM_BYTES) -> CdnFetchResult:
    request = urllib.request.Request(url, headers=_browser_headers(base_url), method=method)
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        response = opener.open(request, timeout=25)
    except urllib.error.HTTPError as exc:
        provider, cache_status = detect_cdn_provider(exc.headers)
        return CdnFetchResult(provider, cache_status, exc.code, 0, "http_error", f"HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return CdnFetchResult("unknown", "UNKNOWN", None, 0, "network_error", str(exc.reason)[:500])
    except OSError as exc:
        return CdnFetchResult("unknown", "UNKNOWN", None, 0, "network_error", str(exc)[:500])

    with response:
        provider, cache_status = detect_cdn_provider(response.headers)
        status = int(getattr(response, "status", response.getcode()))
        if method.upper() == "HEAD":
            return CdnFetchResult(provider, cache_status, status, 0)
        try:
            declared_size = int(_header_value(response.headers, "content-length") or 0)
        except ValueError:
            declared_size = 0
        if declared_size > max_bytes:
            return CdnFetchResult(provider, cache_status, status, 0, "payload_too_large", "资源超过预热大小上限")
        received = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            received += len(chunk)
            if received > max_bytes:
                return CdnFetchResult(provider, cache_status, status, received, "payload_too_large", "资源超过预热大小上限")
        return CdnFetchResult(provider, cache_status, status, received)


def probe_cdn(base_url: str) -> dict[str, object]:
    normalized = normalize_cdn_warm_base_url(base_url)
    result = browser_fetch(f"{normalized}/favicon.ico", base_url=normalized, max_bytes=512 * 1024)
    detected = result.provider in SUPPORTED_PROVIDERS
    return {
        "base_url": normalized,
        "provider": result.provider,
        "cache_status": result.cache_status,
        "response_status": result.response_status,
        "detected": detected,
        "message": "已识别 CDN" if detected else "未识别 ESA、EdgeOne 或 Cloudflare；该地址可能直连源站或未绑定 CDN",
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


def _is_public_image(image: Image | None) -> bool:
    return bool(image and image.is_public and image.rating != "hidden")


def _target_url(base_url: str, image: Image, variant: str) -> str:
    route = build_media_url(image, variant)  # Versioned URL is the CDN cache key.
    return urllib.parse.urljoin(f"{base_url}/", route.lstrip("/"))


def enqueue_image_for_warm(
    db: Session,
    image: Image,
    *,
    variant: str = "thumbnail",
    force_retry: bool = False,
) -> tuple[CdnWarmTask | None, str]:
    if variant not in WARMABLE_VARIANTS:
        raise ValueError("CDN 预热仅支持缩略图或预览图")
    config = get_cdn_warm_config(db)
    if not config["enabled"]:
        return None, "disabled"
    if not config["valid"]:
        return None, "invalid_base_url"
    if not _is_public_image(image):
        return None, "not_public"
    version = max(1, int(image.media_version or 1))
    task = db.scalar(
        select(CdnWarmTask).where(
            CdnWarmTask.image_id == image.id,
            CdnWarmTask.variant == variant,
            CdnWarmTask.media_version == version,
        )
    )
    if task:
        if force_retry and task.status in {TASK_STATUS_FAILED, TASK_STATUS_SKIPPED}:
            task.status = TASK_STATUS_QUEUED
            task.attempt_count = 0
            task.next_attempt_at = None
            task.finished_at = None
            task.error_code = None
            task.error_message = None
            task.provider = "unknown"
            task.cache_status = None
            return task, "retried"
        return task, "existing"
    task = CdnWarmTask(
        image_id=image.id,
        variant=variant,
        media_version=version,
        target_url=_target_url(str(config["base_url"]), image, variant),
        status=TASK_STATUS_QUEUED,
    )
    db.add(task)
    return task, "queued"


def enqueue_public_images(
    db: Session,
    images: list[Image],
    *,
    variant: str = "thumbnail",
    force_retry: bool = False,
) -> dict[str, int]:
    result = {"queued": 0, "existing": 0, "retried": 0, "skipped": 0}
    for image in images:
        _task, outcome = enqueue_image_for_warm(db, image, variant=variant, force_retry=force_retry)
        if outcome in result:
            result[outcome] += 1
        else:
            result["skipped"] += 1
    return result


def enqueue_new_public_image(db: Session, image: Image) -> bool:
    config = get_cdn_warm_config(db)
    if not config["auto_new_uploads"]:
        return False
    _task, outcome = enqueue_image_for_warm(db, image, variant="thumbnail")
    return outcome in {"queued", "retried"}


def enqueue_home_images(db: Session, images: list[Image]) -> int:
    queued = 0
    for image in images:
        _task, outcome = enqueue_image_for_warm(db, image, variant="preview")
        if outcome in {"queued", "retried"}:
            queued += 1
    return queued


def _eligible_condition(now: datetime):
    return or_(
        CdnWarmTask.status == TASK_STATUS_QUEUED,
        and_(
            CdnWarmTask.status == TASK_STATUS_RETRY_WAIT,
            or_(CdnWarmTask.next_attempt_at.is_(None), CdnWarmTask.next_attempt_at <= now),
        ),
    )


def _claim_next_task(db: Session) -> int | None:
    now = utcnow()
    task = db.scalar(
        select(CdnWarmTask)
        .where(_eligible_condition(now), CdnWarmTask.attempt_count < CdnWarmTask.max_attempts)
        .order_by(CdnWarmTask.next_attempt_at, CdnWarmTask.created_at, CdnWarmTask.id)
        .limit(1)
    )
    if not task:
        return None
    task.status = TASK_STATUS_PROCESSING
    task.attempt_count += 1
    task.next_attempt_at = None
    task.started_at = now
    task.finished_at = None
    task.error_code = None
    task.error_message = None
    db.commit()
    return task.id


def _retry_delay(attempt_count: int) -> int:
    return min(300, 15 * max(1, attempt_count))


def requeue_expired_cdn_warm_tasks(db: Session, now: datetime | None = None) -> int:
    current = now or utcnow()
    shared_cache_seconds = max(60, int(settings.media_public_shared_cache_seconds))
    due_before = current - timedelta(seconds=max(0, shared_cache_seconds - REWARM_LEAD_SECONDS))
    updated = db.execute(
        update(CdnWarmTask)
        .where(
            CdnWarmTask.status == TASK_STATUS_SUCCESS,
            CdnWarmTask.variant.in_(WARMABLE_VARIANTS),
            CdnWarmTask.finished_at.is_not(None),
            CdnWarmTask.finished_at <= due_before,
        )
        .values(
            status=TASK_STATUS_QUEUED,
            attempt_count=0,
            next_attempt_at=None,
            started_at=None,
            finished_at=None,
            error_code=None,
            error_message=None,
        )
    ).rowcount or 0
    if updated:
        db.commit()
    return int(updated)


def _complete_task(db: Session, task: CdnWarmTask, result: CdnFetchResult, *, status: str, error_code: str | None = None, error_message: str | None = None) -> None:
    task.status = status
    task.provider = result.provider
    task.cache_status = result.cache_status
    task.response_status = result.response_status
    task.response_bytes = result.response_bytes
    task.error_code = error_code or result.error_code
    task.error_message = (error_message or result.error_message or "")[:1000] or None
    task.finished_at = utcnow()
    task.next_attempt_at = None
    db.commit()


def _process_task(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(CdnWarmTask, task_id)
        if not task or task.status != TASK_STATUS_PROCESSING:
            return
        image = db.get(Image, task.image_id)
        config = get_cdn_warm_config(db)
        if not config["enabled"] or not config["valid"]:
            _complete_task(db, task, CdnFetchResult("unknown", "SKIPPED", None, 0), status=TASK_STATUS_SKIPPED, error_code="warm_disabled", error_message="CDN 预热未启用或域名配置无效")
            return
        if not _is_public_image(image) or max(1, int(image.media_version or 1)) != task.media_version:
            _complete_task(db, task, CdnFetchResult("unknown", "SKIPPED", None, 0), status=TASK_STATUS_SKIPPED, error_code="media_changed", error_message="图片已变更、隐藏或不再公开")
            return

        result = browser_fetch(task.target_url, base_url=str(config["base_url"]))
        if result.error_code:
            retryable = result.error_code == "network_error" or (result.response_status or 0) >= 500
            if retryable and task.attempt_count < task.max_attempts:
                task.status = TASK_STATUS_RETRY_WAIT
                task.provider = result.provider
                task.cache_status = result.cache_status
                task.response_status = result.response_status
                task.response_bytes = result.response_bytes
                task.error_code = result.error_code
                task.error_message = (result.error_message or "预热请求失败")[:1000]
                task.next_attempt_at = utcnow() + timedelta(seconds=_retry_delay(task.attempt_count))
                task.finished_at = None
                db.commit()
                _worker_wakeup.set()
            else:
                _complete_task(db, task, result, status=TASK_STATUS_FAILED)
            return
        if result.provider not in SUPPORTED_PROVIDERS:
            _complete_task(db, task, result, status=TASK_STATUS_SKIPPED, error_code="cdn_not_detected", error_message="未识别 ESA、EdgeOne 或 Cloudflare，已跳过直连源站")
            return
        verification = browser_fetch(task.target_url, base_url=str(config["base_url"]), method="HEAD", max_bytes=0)
        final_result = CdnFetchResult(
            verification.provider if verification.provider in SUPPORTED_PROVIDERS else result.provider,
            verification.cache_status if verification.cache_status not in {"UNKNOWN", "DIRECT"} else result.cache_status,
            verification.response_status or result.response_status,
            result.response_bytes,
            verification.error_code,
            verification.error_message,
        )
        if final_result.cache_status in CACHE_NOT_CACHEABLE_STATUSES:
            _complete_task(db, task, final_result, status=TASK_STATUS_FAILED, error_code="cdn_not_cacheable", error_message="CDN 返回不可缓存状态，请检查 CDN 缓存规则")
            return
        _complete_task(db, task, final_result, status=TASK_STATUS_SUCCESS)


def run_cdn_warm_once() -> bool:
    with SessionLocal() as db:
        config = get_cdn_warm_config(db)
        if not config["enabled"] or not config["valid"]:
            return False
        _run_rewarm_maintenance_if_due(db)
        task_id = _claim_next_task(db)
    if not task_id:
        return False
    _process_task(task_id)
    return True


def _recover_processing_tasks() -> None:
    with SessionLocal() as db:
        tasks = db.scalars(select(CdnWarmTask).where(CdnWarmTask.status == TASK_STATUS_PROCESSING)).all()
        if not tasks:
            return
        for task in tasks:
            if task.attempt_count >= task.max_attempts:
                task.status = TASK_STATUS_FAILED
                task.finished_at = utcnow()
                task.error_code = "worker_interrupted"
                task.error_message = "服务重启时预热任务中断且已达到最大尝试次数"
            else:
                task.status = TASK_STATUS_RETRY_WAIT
                task.next_attempt_at = utcnow()
                task.error_code = "worker_interrupted"
                task.error_message = "服务重启时预热任务中断，已自动重试"
        db.commit()


def _run_rewarm_maintenance_if_due(db: Session) -> None:
    global _last_rewarm_scan_at
    now = utcnow()
    with _maintenance_lock:
        if _last_rewarm_scan_at and (now - _last_rewarm_scan_at).total_seconds() < REWARM_SCAN_INTERVAL_SECONDS:
            return
        _last_rewarm_scan_at = now
    if requeue_expired_cdn_warm_tasks(db, now):
        _worker_wakeup.set()


def _worker_loop() -> None:
    while not _worker_shutdown.is_set():
        try:
            if run_cdn_warm_once():
                if _worker_shutdown.wait(WORKER_TASK_INTERVAL_SECONDS):
                    return
                continue
        except Exception as exc:  # noqa: BLE001 - keep future tasks available after an unexpected failure.
            logger.error("CDN warm worker iteration failed (%s)", type(exc).__name__)
        _worker_wakeup.wait(WORKER_POLL_SECONDS)
        _worker_wakeup.clear()


def start_cdn_warm_worker() -> None:
    global _worker_thread
    with SessionLocal() as db:
        config = get_cdn_warm_config(db)
    if not config["enabled"] or not config["valid"]:
        return
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            _worker_wakeup.set()
            return
        _worker_shutdown.clear()
        _worker_thread = threading.Thread(target=_worker_loop, name="agms-cdn-warm", daemon=True)
        _worker_thread.start()
        _worker_wakeup.set()


def initialize_cdn_warm_queue() -> None:
    _recover_processing_tasks()
    start_cdn_warm_worker()


def stop_cdn_warm_worker(join_timeout: float = 1.0) -> None:
    global _worker_thread
    with _worker_lock:
        _worker_shutdown.set()
        _worker_wakeup.set()
        thread = _worker_thread
        _worker_thread = None
    if thread and thread is not threading.current_thread():
        thread.join(timeout=join_timeout)


def cdn_warm_stats(db: Session) -> dict[str, object]:
    counts = dict(db.execute(select(CdnWarmTask.status, func.count(CdnWarmTask.id)).group_by(CdnWarmTask.status)).all())
    recent = db.scalars(select(CdnWarmTask).order_by(CdnWarmTask.updated_at.desc(), CdnWarmTask.id.desc()).limit(MAX_RECENT_TASKS)).all()
    current = utcnow()
    shared_cache_seconds = max(60, int(settings.media_public_shared_cache_seconds))
    fresh_after = current - timedelta(seconds=max(0, shared_cache_seconds - REWARM_LEAD_SECONDS))
    public_image_conditions = (Image.is_public.is_(True), Image.rating != "hidden")
    coverage_total = int(db.scalar(select(func.count(Image.id)).where(*public_image_conditions)) or 0)
    coverage_fresh = int(
        db.scalar(
            select(func.count(CdnWarmTask.id))
            .join(Image, Image.id == CdnWarmTask.image_id)
            .where(
                *public_image_conditions,
                CdnWarmTask.variant == "thumbnail",
                CdnWarmTask.status == TASK_STATUS_SUCCESS,
                CdnWarmTask.media_version == Image.media_version,
                CdnWarmTask.finished_at.is_not(None),
                CdnWarmTask.finished_at >= fresh_after,
            )
        )
        or 0
    )
    with _worker_lock:
        worker_alive = bool(_worker_thread and _worker_thread.is_alive())
    return {
        "queued": int(counts.get(TASK_STATUS_QUEUED, 0)),
        "processing": int(counts.get(TASK_STATUS_PROCESSING, 0)),
        "retry_wait": int(counts.get(TASK_STATUS_RETRY_WAIT, 0)),
        "success": int(counts.get(TASK_STATUS_SUCCESS, 0)),
        "failed": int(counts.get(TASK_STATUS_FAILED, 0)),
        "skipped": int(counts.get(TASK_STATUS_SKIPPED, 0)),
        "worker_alive": worker_alive,
        "coverage_total": coverage_total,
        "coverage_fresh": coverage_fresh,
        "coverage_percentage": round((coverage_fresh * 100) / coverage_total, 1) if coverage_total else 100,
        "rewarm_after_seconds": shared_cache_seconds,
        "recent_tasks": [
            {
                "id": task.id,
                "image_id": task.image_id,
                "variant": task.variant,
                "media_version": task.media_version,
                "status": task.status,
                "provider": task.provider,
                "cache_status": task.cache_status or "",
                "response_status": task.response_status,
                "response_bytes": task.response_bytes,
                "attempt_count": task.attempt_count,
                "error_code": task.error_code or "",
                "error_message": task.error_message or "",
                "updated_at": task.updated_at,
            }
            for task in recent
        ],
    }
