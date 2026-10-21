"""Optional SSO adapter; browser passwords and OIDC tokens never pass this API."""
import json
import ipaddress
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException, Request
from starlette.responses import RedirectResponse


def enabled() -> bool:
    mode = os.environ.get("AGMS_AUTH_MODE", "local")
    if mode not in ("local", "sso"):
        raise RuntimeError("Invalid authentication mode")
    return mode == "sso"


def call(operation: str, request: Request) -> dict:
    base = os.environ.get("AGMS_SSO_AGENT_URL", "http://127.0.0.1:9788")
    key = os.environ.get("AGMS_SSO_AGENT_KEY", "")
    endpoint = urllib.parse.urlsplit(base)
    if endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or endpoint.path not in ("", "/") or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or len(key) < 32:
        raise HTTPException(503, "SSO configuration unavailable")
    peer = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(peer)
        if address.is_loopback and request.headers.get("x-real-ip"):
            address = ipaddress.ip_address(request.headers["x-real-ip"])
    except ValueError:
        raise HTTPException(403, "Invalid client address") from None
    body = json.dumps({"ip": str(address), "cookie": request.headers.get("cookie", ""), "method": request.method,
                       "origin": request.headers.get("origin", ""), "csrf": request.headers.get("x-csrf-token", ""),
                       "query": request.url.query}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/moegallery/" + operation, data=body,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=12) as response:
            raw = response.read(16385)
            if len(raw) > 16384:
                raise ValueError("oversized response")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("invalid response")
            return result
    except urllib.error.HTTPError as exc:
        code = exc.code if exc.code in (400, 401, 403, 404, 405, 429, 503) else 503
        raise HTTPException(code, "SSO authentication required" if code == 401 else "SSO request rejected") from None
    except (OSError, ValueError):
        raise HTTPException(503, "SSO temporarily unavailable") from None


def validate(request: Request) -> dict:
    result = call("validate", request)
    return {"sub": result["username"], "sso_subject": result["subject"], "auth_type": "sso", "roles": result["roles"]}


def browser_response(result: dict) -> RedirectResponse:
    response = RedirectResponse(result["location"], status_code=302, headers={"Cache-Control": "no-store"})
    for cookie in result.get("cookies", []):
        response.headers.append("set-cookie", cookie)
    return response
