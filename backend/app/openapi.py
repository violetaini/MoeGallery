from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.auth import ADMIN_CSRF_COOKIE, ADMIN_SESSION_COOKIE
from app.config import settings


API_DESCRIPTION = """
Anime Gallery Media Server API 覆盖前台图片浏览、后台媒体资料维护、批量上传任务、
元数据导入、部署设置与系统健康检查。

鉴权模型：

- 浏览器后台会话使用 `agms_admin_session` HttpOnly Cookie。
- 运维脚本建议使用 `Authorization: Bearer <AGMS_API_KEYS value>`。
- 使用 Cookie 会话调用非安全方法时，还需要提交与 `agms_admin_csrf` Cookie 匹配的 `X-CSRF-Token`。
- API Key 不依赖 Cookie，因此不需要 CSRF；请只在服务端保存，泄露后及时轮换。
"""


TAGS_METADATA = [
    {"name": "auth", "description": "管理员登录、退出和当前账号检查。"},
    {"name": "install", "description": "首次部署状态检查与初始化。"},
    {"name": "images", "description": "图片列表、上传、预览、详情、收藏和批量维护。"},
    {"name": "upload-tasks", "description": "高并发批量上传队列与重复文件预检。"},
    {"name": "imports", "description": "CSV、JSON、XLSX、XLSM 元数据导入模板与执行接口。"},
    {"name": "works", "description": "作品资料、详情页、封面图与背景图绑定。"},
    {"name": "characters", "description": "角色资料、头像绑定与作品关系。"},
    {"name": "tags", "description": "为兼容旧数据保留的标签接口。"},
    {"name": "search", "description": "前台图片、作品和角色的全库搜索。"},
    {"name": "stats", "description": "后台首页统计数据。"},
    {"name": "settings", "description": "后台偏好、前台首页设置、登录密钥轮换和运维 API Key 管理。"},
    {"name": "system", "description": "部署诊断、存储与编解码健康检查。"},
    {"name": "updates", "description": "后台更新检查、下载校验和升级任务。"},
    {"name": "storage", "description": "带权限检查的存储文件访问。"},
    {"name": "health", "description": "轻量存活检查接口。"},
]


PROTECTED_OPERATIONS = {
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/images/upload"),
    ("POST", "/api/images/preview"),
    ("PUT", "/api/images/batch"),
    ("DELETE", "/api/images/batch"),
    ("PUT", "/api/images/{image_id}"),
    ("DELETE", "/api/images/{image_id}"),
    ("POST", "/api/upload-tasks"),
    ("POST", "/api/upload-tasks/check-duplicates"),
    ("POST", "/api/upload-tasks/check-duplicates-files"),
    ("GET", "/api/upload-tasks"),
    ("GET", "/api/upload-tasks/{task_id}"),
    ("POST", "/api/imports/metadata"),
    ("GET", "/api/imports/metadata/template"),
    ("POST", "/api/works"),
    ("PUT", "/api/works/{work_id}"),
    ("DELETE", "/api/works/{work_id}"),
    ("POST", "/api/characters"),
    ("PUT", "/api/characters/{character_id}"),
    ("DELETE", "/api/characters/{character_id}"),
    ("POST", "/api/tags"),
    ("PUT", "/api/tags/{tag_id}"),
    ("DELETE", "/api/tags/{tag_id}"),
    ("GET", "/api/stats"),
    ("GET", "/api/settings"),
    ("PUT", "/api/settings"),
    ("POST", "/api/settings/auth-secret/rotate"),
    ("POST", "/api/settings/api-keys/reset"),
    ("GET", "/api/system/health"),
    ("GET", "/api/updates/check"),
    ("GET", "/api/updates/tasks"),
    ("POST", "/api/updates/tasks"),
    ("GET", "/api/updates/tasks/{task_id}"),
}


OPERATION_METADATA = {
    ("POST", "/api/auth/login"): {
        "summary": "管理员登录",
        "description": "创建 HttpOnly 管理员会话 Cookie。脚本和自动化任务应优先使用 API Key，而不是模拟浏览器登录。",
    },
    ("POST", "/api/auth/logout"): {
        "summary": "退出当前管理员会话",
        "description": "撤销当前 Cookie 会话并清理管理员 Cookie。",
    },
    ("GET", "/api/auth/me"): {
        "summary": "查看当前管理员身份",
        "description": "返回已登录管理员资料。支持浏览器会话 Cookie 或运维 API Key。",
    },
    ("GET", "/api/install/status"): {
        "summary": "检查首次安装状态",
        "description": "返回应用是否已经完成初始化。",
    },
    ("POST", "/api/install"): {
        "summary": "执行首次安装",
        "description": "初始化 SQLite 或 MySQL 部署配置，创建管理员账号，执行迁移，写入 `.env`，并创建安装锁。",
    },
    ("GET", "/storage/{relative_path}"): {
        "summary": "读取存储媒体文件",
        "description": "在路径规范化和数据库权限检查后，返回原图、预览图或缩略图。",
    },
    ("GET", "/api/images"): {
        "summary": "获取图片列表",
        "description": "默认返回前台公开画廊图片。管理员鉴权后可查询隐藏/私有图片和后台专用筛选条件。",
    },
    ("POST", "/api/images/upload"): {
        "summary": "立即上传一张或多张图片",
        "description": "上传文件，校验后缀与内容，支持静态 SDR 原图转 WebP、动图保留原格式、HDR JXR 转 HDR AVIF。",
    },
    ("POST", "/api/images/preview"): {
        "summary": "生成上传预览",
        "description": "文件正式入库前，为选中的上传文件返回临时 WebP 预览图。",
    },
    ("PUT", "/api/images/batch"): {
        "summary": "批量编辑图片元数据",
        "description": "批量修改作品、角色、分级、收藏数、来源地址和作者。文件名不允许批量修改。",
    },
    ("DELETE", "/api/images/batch"): {
        "summary": "批量删除图片",
        "description": "删除多张图片记录及其原图、预览图和缩略图文件。",
    },
    ("GET", "/api/images/{image_id}"): {
        "summary": "获取图片详情",
        "description": "返回图片元数据和关联关系。隐藏/私有图片需要管理员鉴权。",
    },
    ("POST", "/api/images/{image_id}/view"): {
        "summary": "增加图片浏览数",
        "description": "前台图片详情浮窗使用的公开计数接口。",
    },
    ("POST", "/api/images/{image_id}/favorite"): {
        "summary": "增加图片收藏数",
        "description": "用于增加图片收藏计数的公开接口。",
    },
    ("DELETE", "/api/images/{image_id}/favorite"): {
        "summary": "减少图片收藏数",
        "description": "用于减少图片收藏计数的公开接口，最低不会低于 0。",
    },
    ("PUT", "/api/images/{image_id}"): {
        "summary": "更新单张图片",
        "description": "更新单张图片的元数据和关联关系。修改文件名时必须保留原后缀。",
    },
    ("DELETE", "/api/images/{image_id}"): {
        "summary": "删除单张图片",
        "description": "删除图片记录及其全部衍生文件。",
    },
    ("POST", "/api/upload-tasks"): {
        "summary": "创建批量上传任务",
        "description": "将一个或多个文件加入服务端并发上传处理队列。",
    },
    ("POST", "/api/upload-tasks/check-duplicates"): {
        "summary": "检查重复哈希",
        "description": "用客户端计算的 SHA-256 与已入库图片和待处理队列做重复预检。",
    },
    ("POST", "/api/upload-tasks/check-duplicates-files"): {
        "summary": "检查重复上传文件",
        "description": "当客户端未计算哈希时，由服务端对选中文件执行重复预检。",
    },
    ("GET", "/api/upload-tasks"): {
        "summary": "获取上传任务列表",
        "description": "返回最近的排队、运行、成功或失败上传任务，供管理员监控。",
    },
    ("GET", "/api/upload-tasks/{task_id}"): {
        "summary": "获取上传任务详情",
        "description": "返回单个上传任务的状态、结果或错误信息。",
    },
    ("POST", "/api/imports/metadata"): {
        "summary": "预览或提交元数据导入",
        "description": "从 CSV、JSON、XLSX 或 XLSM 导入作品和角色。正式提交前建议先使用 `dry_run=true` 预览。",
    },
    ("GET", "/api/imports/metadata/template"): {
        "summary": "下载元数据导入模板",
        "description": "下载包含全部支持字段的空白 CSV、JSON、XLSX 或 XLSM 模板。",
    },
    ("GET", "/api/works"): {"summary": "获取作品列表", "description": "获取作品记录，可按关键词筛选。"},
    ("POST", "/api/works"): {"summary": "创建作品", "description": "创建作品记录，并可同时绑定元数据和图片。"},
    ("GET", "/api/works/{work_id}"): {"summary": "获取作品详情", "description": "返回单个作品、作品角色和相关图片。"},
    ("PUT", "/api/works/{work_id}"): {"summary": "更新作品", "description": "更新作品元数据、封面图和背景图绑定。"},
    ("DELETE", "/api/works/{work_id}"): {"summary": "删除作品", "description": "删除作品记录并移除相关绑定。"},
    ("GET", "/api/characters"): {"summary": "获取角色列表", "description": "获取角色记录，可按作品或关键词筛选。"},
    ("POST", "/api/characters"): {"summary": "创建角色", "description": "创建角色，并可同时绑定作品和头像。"},
    ("GET", "/api/characters/{character_id}"): {"summary": "获取角色详情", "description": "返回单个角色和相关图片。"},
    ("PUT", "/api/characters/{character_id}"): {"summary": "更新角色", "description": "更新角色元数据、作品绑定和头像图片。"},
    ("DELETE", "/api/characters/{character_id}"): {"summary": "删除角色", "description": "删除单个角色并移除相关绑定。"},
    ("GET", "/api/tags"): {"summary": "获取标签列表", "description": "获取为兼容旧数据保留的标签记录。"},
    ("POST", "/api/tags"): {"summary": "创建标签", "description": "创建兼容旧数据的标签记录。"},
    ("GET", "/api/tags/{tag_id}"): {"summary": "获取标签详情", "description": "返回单个标签和相关图片。"},
    ("PUT", "/api/tags/{tag_id}"): {"summary": "更新标签", "description": "更新兼容旧数据的标签记录。"},
    ("DELETE", "/api/tags/{tag_id}"): {"summary": "删除标签", "description": "删除兼容旧数据的标签记录。"},
    ("GET", "/api/search"): {"summary": "搜索媒体库", "description": "使用单个关键词搜索图片、作品和角色。"},
    ("GET", "/api/stats"): {"summary": "获取后台统计", "description": "返回后台首页统计计数。"},
    ("GET", "/api/settings"): {"summary": "获取后台设置", "description": "返回管理员偏好、前台首页图片绑定、上传队列参数、GitHub 更新检查代理和运维 API Key。"},
    ("GET", "/api/settings/public"): {"summary": "获取公开设置", "description": "返回前台首页和列表页背景图片设置。"},
    ("PUT", "/api/settings"): {"summary": "更新后台设置", "description": "更新管理员资料、图片管理显示模式、首页幻灯片、前台背景图、上传 worker 参数和 GitHub 更新检查代理。"},
    ("POST", "/api/settings/auth-secret/rotate"): {"summary": "轮换登录密钥", "description": "生成新的 `AGMS_AUTH_SECRET`，写入 `.env`，并撤销当前浏览器会话。"},
    ("POST", "/api/settings/api-keys/reset"): {"summary": "重置运维 API Key", "description": "生成新的默认 `AGMS_API_KEYS`，写入 `.env`，并使旧 API Key 立即失效。"},
    ("GET", "/api/system/health"): {"summary": "获取系统健康状态", "description": "返回程序版本、最新 Release、数据库迁移状态、存储、上传队列、FFmpeg、JXR 和 HDR 补丁诊断信息。"},
    ("GET", "/api/updates/check"): {"summary": "检查可用更新", "description": "读取当前版本并查询 GitHub Latest Release，返回是否有新版本以及更新执行模式。"},
    ("GET", "/api/updates/tasks"): {"summary": "获取更新任务列表", "description": "返回最近的后台更新任务、进度和日志摘要。"},
    ("POST", "/api/updates/tasks"): {"summary": "创建更新任务", "description": "创建下载校验或正式更新任务。正式更新会校验 SHA256、备份、迁移数据库并重启服务。"},
    ("GET", "/api/updates/tasks/{task_id}"): {"summary": "获取更新任务详情", "description": "返回单个更新任务的状态、进度和日志。"},
    ("GET", "/api/health"): {"tags": ["health"], "summary": "存活检查", "description": "供反向代理和可用性监控使用的轻量免登录接口。"},
}


PARAMETER_DESCRIPTIONS = {
    "page": "从 1 开始的页码。",
    "page_size": "每页记录数。大多数列表接口最多返回 100 条。",
    "q": "用于模糊搜索的关键词。",
    "work_id": "作品数据库 ID。",
    "character_id": "角色数据库 ID。",
    "tag_id": "兼容旧标签的数据库 ID。",
    "image_id": "图片数据库 ID。",
    "task_id": "任务 ID。",
    "ids": "可选，逗号分隔的上传任务 ID 列表，用于直接查询指定任务。",
    "limit": "最多返回的结果数量。",
    "type": "兼容旧标签的类型筛选。",
    "relative_path": "图片元数据返回的存储相对路径，例如 `preview/example.webp`。",
    ADMIN_SESSION_COOKIE: "管理员会话 Cookie。运维脚本建议改用 `Authorization: Bearer <api-key>`。",
    "rating": "`safe`、`sensitive` 或 `hidden`。",
    "sort": "`latest`、`random`、`favorites` 或 `resolution`。",
    "public_only": "为 true 时排除隐藏/私有图片。",
    "exclude_work_related": "排除已绑定作品的图片。",
    "exclude_character_related": "排除已绑定角色的图片。",
    "require_work_related": "只返回至少绑定一个作品的图片。",
    "require_character_related": "只返回至少绑定一个角色的图片。",
    "exclude_cover_images": "排除已作为作品封面的图片。",
    "exclude_avatar_images": "排除已作为角色头像的图片。",
    "format": "模板格式：`csv`、`json`、`xlsx` 或 `xlsm`。",
    "dry_run": "为 true 时只校验和预览导入变更，不正式写入。",
}


REQUEST_EXAMPLES = {
    ("POST", "/api/auth/login"): {
        "application/json": {
            "adminLogin": {
                "summary": "浏览器管理员登录",
                "value": {"username": "admin", "password": "change-this-password"},
            }
        }
    },
    ("POST", "/api/install"): {
        "application/json": {
            "sqliteInstall": {
                "summary": "SQLite 安装",
                "value": {"database_type": "sqlite", "admin_username": "admin", "admin_password": "change-this-password"},
            },
            "mysqlInstall": {
                "summary": "MySQL 安装",
                "value": {
                    "database_type": "mysql",
                    "mysql_host": "127.0.0.1",
                    "mysql_port": 3306,
                    "mysql_database": "anime_gallery",
                    "mysql_username": "anime_gallery",
                    "mysql_password": "change-this-db-password",
                    "admin_username": "admin",
                    "admin_password": "change-this-password",
                },
            },
        }
    },
    ("PUT", "/api/images/batch"): {
        "application/json": {
            "batchEdit": {
                "summary": "批量绑定作品并设置分级",
                "value": {"image_ids": [101, 102], "update": {"work_ids": [12], "rating": "safe", "artist_name": "Kyoto Animation"}},
            }
        }
    },
    ("DELETE", "/api/images/batch"): {
        "application/json": {
            "batchDelete": {"summary": "删除图片", "value": {"image_ids": [101, 102]}}
        }
    },
    ("PUT", "/api/settings"): {
        "application/json": {
            "uploadWorkers": {
                "summary": "调整上传 worker 和更新检查代理",
                "value": {
                    "upload_worker_count": 24,
                    "upload_claim_batch_size": 4,
                    "image_manage_view_mode": "waterfall",
                    "github_proxy_url": "https://gh-proxy.example.com/",
                },
            }
        }
    },
    ("POST", "/api/updates/tasks"): {
        "application/json": {
            "dryRun": {
                "summary": "只下载并校验",
                "value": {"dry_run": True, "force": True},
            },
            "upgrade": {
                "summary": "正式更新到最新版本",
                "value": {"dry_run": False},
            },
        }
    },
}


RESPONSE_EXAMPLES = {
    ("GET", "/api/health"): {
        "200": {"status": "ok", "name": "Anime Gallery Media Server"},
    },
    ("GET", "/api/auth/me"): {
        "200": {"username": "admin", "avatar_image_id": None, "avatar_image": None},
    },
    ("GET", "/api/upload-tasks/{task_id}"): {
        "200": {
            "id": 1,
            "status": "succeeded",
            "filename": "example.webp",
            "error_message": None,
            "image_id": 100,
        },
    },
    ("GET", "/api/system/health"): {
        "200": {
            "database": {"ok": True, "dialect": "mysql", "url": "mysql+pymysql://user:***@127.0.0.1:3306/anime_gallery"},
            "storage": {"ok": True},
            "auth_secret": {"configured": True, "ephemeral": False, "strong": True, "message": "已配置持久化强密钥"},
        },
    },
    ("GET", "/api/updates/check"): {
        "200": {
            "current_version": "v0.1.2",
            "latest_release": {"available": True, "version": "v0.1.3", "proxied": False},
            "update_available": True,
            "updater_available": True,
            "updater_mode": "command",
        },
    },
}


def _inject_examples(operation: dict, method: str, path: str) -> None:
    request_examples = REQUEST_EXAMPLES.get((method, path))
    if request_examples:
        content = operation.get("requestBody", {}).get("content", {})
        for media_type, examples in request_examples.items():
            if media_type in content:
                content[media_type]["examples"] = examples

    response_examples = RESPONSE_EXAMPLES.get((method, path))
    if response_examples:
        for status_code, value in response_examples.items():
            response = operation.get("responses", {}).get(status_code)
            if not response:
                continue
            content = response.setdefault("content", {}).setdefault("application/json", {})
            content.setdefault("examples", {})["example"] = {"summary": "示例响应", "value": value}


def _mark_security(operation: dict, method: str, path: str) -> None:
    if (method, path) not in PROTECTED_OPERATIONS:
        return
    operation["security"] = [
        {"OperationsApiKey": []},
        {"AdminSessionCookie": [], "CsrfTokenCookie": [], "CsrfTokenHeader": []},
    ]
    responses = operation.setdefault("responses", {})
    responses.setdefault(
        "401",
        {
            "description": "需要鉴权，或提交的令牌无效。",
            "content": {"application/json": {"example": {"detail": "Authentication required"}}},
        },
    )
    responses.setdefault(
        "403",
        {
            "description": "使用 Cookie 会话发起写入请求时，缺少匹配的 CSRF 请求头。",
            "content": {"application/json": {"example": {"detail": "CSRF validation failed"}}},
        },
    )


def _describe_parameters(operation: dict) -> None:
    for parameter in operation.get("parameters", []):
        name = parameter.get("name")
        if name in PARAMETER_DESCRIPTIONS and not parameter.get("description"):
            parameter["description"] = PARAMETER_DESCRIPTIONS[name]


def _customize_schema(schema: dict) -> dict:
    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["OperationsApiKey"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "AGMS_API_KEY",
        "description": "通过 `AGMS_API_KEYS` 配置的运维 API Key。",
    }
    security_schemes["AdminSessionCookie"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": ADMIN_SESSION_COOKIE,
        "description": "浏览器管理员会话 Cookie。",
    }
    security_schemes["CsrfTokenCookie"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": ADMIN_CSRF_COOKIE,
        "description": "管理员会话同时签发的 CSRF Cookie。",
    }
    security_schemes["CsrfTokenHeader"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-CSRF-Token",
        "description": "使用 Cookie 会话调用非安全方法时，必须与 CSRF Cookie 一致。",
    }

    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            method_upper = method.upper()
            metadata = OPERATION_METADATA.get((method_upper, path))
            if metadata:
                operation.update(metadata)
            _mark_security(operation, method_upper, path)
            if (method_upper, path) not in PROTECTED_OPERATIONS and operation.get("security") == [{"HTTPBearer": []}]:
                operation.pop("security", None)
            _describe_parameters(operation)
            _inject_examples(operation, method_upper, path)
    security_schemes.pop("HTTPBearer", None)
    return schema


def configure_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=settings.app_name,
            version=settings.app_version,
            description=API_DESCRIPTION,
            routes=app.routes,
            tags=TAGS_METADATA,
            servers=[
                {"url": "/", "description": "当前部署域名"},
                {"url": settings.api_prefix, "description": "API 前缀"},
            ],
        )
        app.openapi_schema = _customize_schema(schema)
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
