from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, JSONResponse

from app.api import auth, characters, images, imports, install, search, settings as api_settings, stats, storage, system, tags, upload_tasks, updates, works
from app.auth import ADMIN_CSRF_COOKIE, ADMIN_SESSION_COOKIE, require_admin, verify_access_token, verify_api_key
from app.config import settings
from app.openapi import configure_openapi
from app.services.storage_service import ensure_storage_dirs


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class AuthorizationHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        authorization = request.headers.get("authorization", "").strip()
        if authorization:
            scheme, separator, token = authorization.partition(" ")
            token = token.strip()
            if scheme.lower() != "bearer" or not separator or not token:
                return JSONResponse(
                    {"detail": "Invalid authorization header"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not verify_api_key(token):
                try:
                    verify_access_token(token)
                except HTTPException:
                    return JSONResponse(
                        {"detail": "Invalid or expired token"},
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer"},
                    )
        return await call_next(request)


class CsrfMiddleware(BaseHTTPMiddleware):
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    EXEMPT_PATHS = {
        f"{settings.api_prefix}/auth/login",
        f"{settings.api_prefix}/install",
        f"{settings.api_prefix}/install/status",
    }

    async def dispatch(self, request, call_next):
        if request.method.upper() not in self.SAFE_METHODS and request.url.path not in self.EXEMPT_PATHS:
            session_cookie = request.cookies.get(ADMIN_SESSION_COOKIE)
            if session_cookie:
                csrf_cookie = request.cookies.get(ADMIN_CSRF_COOKIE, "")
                csrf_header = request.headers.get("x-csrf-token", "")
                if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                    return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
        return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuthorizationHeaderMiddleware)
app.add_middleware(CsrfMiddleware)

ensure_storage_dirs()

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(install.router, prefix=settings.api_prefix)
app.include_router(storage.router)
app.include_router(images.router, prefix=settings.api_prefix)
app.include_router(upload_tasks.router, prefix=settings.api_prefix)
app.include_router(updates.router, prefix=settings.api_prefix)
app.include_router(imports.router, prefix=settings.api_prefix)
app.include_router(works.router, prefix=settings.api_prefix)
app.include_router(characters.router, prefix=settings.api_prefix)
app.include_router(tags.router, prefix=settings.api_prefix)
app.include_router(search.router, prefix=settings.api_prefix)
app.include_router(stats.router, prefix=settings.api_prefix)
app.include_router(api_settings.router, prefix=settings.api_prefix)
app.include_router(system.router, prefix=settings.api_prefix)

configure_openapi(app)


SCALAR_API_DOCS_HTML = """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Anime Gallery API Docs</title>
    <style>
      body { margin: 0; }
    </style>
  </head>
  <body>
    <script
      id="api-reference"
      data-url="/api-docs/openapi.json"
      data-theme="alternate"
      data-layout="modern"
    ></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
  </body>
</html>
"""


@app.get("/api-docs", include_in_schema=False, response_class=HTMLResponse)
def api_docs(_admin: Annotated[dict, Depends(require_admin)]):
    return HTMLResponse(SCALAR_API_DOCS_HTML)


@app.get("/api-docs/openapi.json", include_in_schema=False)
def api_docs_openapi(_admin: Annotated[dict, Depends(require_admin)]):
    return app.openapi()


@app.get("/openapi.json", include_in_schema=False)
def protected_openapi(_admin: Annotated[dict, Depends(require_admin)]):
    return app.openapi()


@app.get(f"{settings.api_prefix}/health")
def health():
    return {"status": "ok", "name": settings.app_name}
