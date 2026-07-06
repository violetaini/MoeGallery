import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from sqlalchemy.orm import Session

from app.config import ROOT_DIR, settings
from app.services.app_setting_service import get_github_release_proxy_url

LATEST_RELEASE_URL = "https://api.github.com/repos/violetaini/MoeGallery/releases/latest"
LATEST_RELEASE_CACHE_SECONDS = 30 * 60
_latest_release_cache: dict[str, dict[str, object]] = {}


def current_app_version() -> str:
    version_file = ROOT_DIR / "VERSION"
    if version_file.exists():
        try:
            version = version_file.read_text(encoding="utf-8").strip()
            if version:
                return version
        except OSError:
            pass
    return settings.app_version


def parse_semver(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", value.strip(), re.IGNORECASE)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def build_latest_release_url(proxy_url: str) -> str:
    proxy_url = proxy_url.strip()
    if not proxy_url:
        return LATEST_RELEASE_URL
    if "{raw_url}" in proxy_url:
        return proxy_url.replace("{raw_url}", LATEST_RELEASE_URL)
    if "{url}" in proxy_url:
        return proxy_url.replace("{url}", urllib.parse.quote(LATEST_RELEASE_URL, safe=""))
    return f"{proxy_url.rstrip('/')}/{LATEST_RELEASE_URL}"


def _asset_summary(asset: dict[str, Any]) -> dict[str, object]:
    return {
        "name": asset.get("name") or "",
        "size": int(asset.get("size") or 0),
        "browser_download_url": asset.get("browser_download_url") or "",
    }


def latest_release_info(db: Session) -> dict:
    now = time.time()
    proxy_url = get_github_release_proxy_url(db)
    request_url = build_latest_release_url(proxy_url)
    cached = _latest_release_cache.get(request_url) or {}
    cached_data = cached.get("data")
    if cached_data and now - float(cached.get("checked_at") or 0) < LATEST_RELEASE_CACHE_SECONDS:
        return dict(cached_data)
    request = urllib.request.Request(
        request_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MoeGallery-system-health",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        data = {
            "available": True,
            "version": payload.get("tag_name") or "",
            "url": payload.get("html_url") or "",
            "assets": [_asset_summary(asset) for asset in payload.get("assets") or []],
            "proxied": bool(proxy_url),
            "checked_at": int(now),
            "message": "ok",
        }
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        data = {
            "available": False,
            "version": "",
            "url": "",
            "assets": [],
            "proxied": bool(proxy_url),
            "checked_at": int(now),
            "message": str(exc),
        }
    _latest_release_cache[request_url] = {"checked_at": now, "data": data}
    return data
