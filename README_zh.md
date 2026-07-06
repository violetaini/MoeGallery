<div align="center">

<img src="frontend/public/avatar.webp" alt="MoeGallery" width="120" />

# **MoeGallery**

[![Version](https://img.shields.io/badge/Version-0.1.0-7c3aed?style=for-the-badge)](frontend/package.json)
[![Frontend](https://img.shields.io/badge/Frontend-Vue%203%20%2B%20Vite-42b883?style=for-the-badge)](frontend/package.json)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20SQLAlchemy-009688?style=for-the-badge)](backend/requirements.txt)
[![Database](https://img.shields.io/badge/Database-MySQL%20%2F%20SQLite-2563eb?style=for-the-badge)](.env.example)
[![HDR](https://img.shields.io/badge/HDR-JXR%20%2B%20AVIF-f97316?style=for-the-badge)](backend/app/utils/image_process.py)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

</div>

<p align="center">
  <a href="README.md">English</a> |
  <a href="README_zh.md">简体中文</a> |
  <a href="README_zh-TW.md">繁體中文</a> |
  <a href="README_ja.md">日本語</a>
</p>

<p align="center">
  <a href="https://anime.chitanda.net/">在线站点</a> |
  <a href="https://anime.chitanda.net/api-docs">API 文档</a> |
  <a href="https://github.com/violetaini/MoeGallery">GitHub</a>
</p>

<p align="center">
  <code>anime-gallery</code>
  <code>image-gallery</code>
  <code>media-library</code>
  <code>vue</code>
  <code>vite</code>
  <code>fastapi</code>
  <code>mysql</code>
  <code>sqlite</code>
  <code>webp</code>
  <code>avif</code>
  <code>hdr</code>
</p>

## 关于

MoeGallery 是一个面向二次元图片收藏与整理的自托管媒体库，用于管理插画、截图、作品、角色、分级与图片元数据。它提供面向访客的前台画廊，也提供用于上传、绑定、编辑、导入和维护的后台面板。

项目定位接近“图片版本 Jellyfin”：前台负责图库浏览、作品页、角色页、分级、首页幻灯片和图片详情浮层；后台负责上传、元数据、存储、重复检测、图片转码、后台任务、登录鉴权和 API 文档。

## 功能

- 全屏视觉首页，幻灯片图片可在后台指定，未指定时从图库随机选择。
- 图片库支持瀑布流、搜索、按作品/角色/分级筛选，以及按最新、随机、收藏数、分辨率排序。
- 图片点击后在当前页面打开详情浮层，同时保留独立图片详情路由。
- 作品页和角色页支持媒体库风格背景、封面、头像、分页区域和后台编辑页面。
- 固定分级系统：`safe`、`sensitive`、`hidden`。
- 后台图片管理支持经典表格和瀑布画廊两种模式。
- 批量上传支持预览、分页、重复预检、任务队列、状态轮询，以及上传前单张移除。
- 批量导入支持 CSV、JSON、XLSX、XLSM 模板。
- 后台偏好可维护管理员资料、头像、密码、图片管理显示模式、上传 worker 参数和首页/列表背景图。
- 系统健康面板检查数据库、存储一致性、上传队列、ffmpeg、JXR 解码、AVIF 编码和 HDR metadata patch 能力。
- 后台安全包含 HttpOnly Cookie 会话、CSRF 校验、登录防爆破、运维 API Key、安装锁和强随机 `AGMS_AUTH_SECRET`。

## 图片管线

| 来源 | 入库策略 | 预览策略 |
| --- | --- | --- |
| 普通静态图片 | 原图转 WebP | 生成 WebP preview 和 thumbnail |
| GIF / 动图 | 保留原格式 | 生成静态 WebP preview 和 thumbnail |
| JXR / HDR 图片 | JXR 转 HDR AVIF，写入 `nclx / mdcv / clli` | 生成 SDR WebP preview 和 thumbnail |
| 非 8-bit 图片 | 保留 HDR / 高位深原图 | 生成 SDR WebP preview 和 thumbnail |

允许上传的常见后缀包括：

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

后端会同时校验文件后缀和实际解码能力。不在白名单内、无法解码或伪装成图片的文件会被拒绝。

## 路由

```text
/                         首页幻灯片
/gallery                  图片库
/images/:id               图片详情
/works                    作品列表
/works/:id                作品详情
/characters               角色列表
/characters/:id           角色详情
/tags                     分级页
/search                   搜索页
/admin                    后台面板
/install                  首次安装向导
/api-docs                 后台 API 文档
```

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3, Vite, Pinia, Vue Router, Element Plus |
| 后端 | FastAPI, SQLAlchemy, Alembic, Pydantic |
| 数据库 | 本地开发使用 SQLite，生产环境使用 MySQL/MariaDB |
| 图片处理 | Pillow, pillow-heif, imagecodecs, ffmpeg |
| 部署 | systemd, Nginx, 宝塔/Linux 裸机 |

## 环境要求

- Python 3.12 或更新版本
- Node.js 20 或更新版本
- 生产环境使用 MySQL 8.x / MariaDB 11.x，本地开发可用 SQLite
- 支持 AVIF/AV1 编码的 ffmpeg

## 本地开发

后端：

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 开发服务器默认运行在 `http://127.0.0.1:5173/`。

## 配置

复制 `.env.example` 为 `.env`，按部署环境调整配置。

```text
AGMS_DATABASE_URL                  SQLite 或 MySQL SQLAlchemy 连接串
AGMS_STORAGE_PATH                  原图、预览图、缩略图和任务文件的存储根目录
AGMS_ADMIN_USERNAME                初始兜底管理员用户名
AGMS_ADMIN_PASSWORD                初始兜底管理员密码
AGMS_AUTH_SECRET                   会话签名强密钥，由安装器生成
AGMS_AUTH_TOKEN_TTL_SECONDS        管理员会话有效期
AGMS_COOKIE_SECURE                 HTTPS 后建议设为 true
AGMS_MAX_UPLOAD_SIZE               最大上传大小
AGMS_PREVIEW_MAX_SIZE              预览图最长边
AGMS_THUMBNAIL_MAX_SIZE            缩略图最长边
AGMS_CORS_ORIGINS                  允许的浏览器来源
```

`AGMS_AUTH_SECRET` 不是 API Key。它用于后端签发和校验管理员会话，必须保密。安装器会自动生成；如果绕过安装器，请手动生成强随机值：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 首次安装

当 `installed.lock` 不存在，并且目标数据库没有有效 Alembic 版本时，前端会进入 `/install`。

安装器支持初始化 SQLite 或 MySQL：

- SQLite：数据库路径由程序决定。
- MySQL：填写主机、端口、数据库名、用户名和密码。
- 存储：使用项目 `storage/` 目录。
- 管理员：设置第一个管理员账号和密码。
- 密钥：自动生成并写入 `.env`。

安装成功后，程序会写入 `.env`、执行迁移、初始化管理员账号、创建 `installed.lock`，必要时提示重启后端。

## 部署

创建目录、安装后端依赖并构建前端：

```bash
sudo mkdir -p /opt/anime-gallery
sudo rsync -a ./ /opt/anime-gallery/
sudo bash /opt/anime-gallery/scripts/create_linux_dirs.sh

cd /opt/anime-gallery
sudo python3 -m venv venv
sudo /opt/anime-gallery/venv/bin/pip install -r backend/requirements.txt

cd /opt/anime-gallery/frontend
npm install
npm run build
```

安装 systemd 和 Nginx 示例：

```bash
sudo cp /opt/anime-gallery/scripts/anime-gallery.service /etc/systemd/system/anime-gallery.service
sudo systemctl daemon-reload
sudo systemctl enable --now anime-gallery

sudo cp /opt/anime-gallery/scripts/nginx-anime-gallery.conf /etc/nginx/sites-available/anime-gallery.conf
sudo ln -s /etc/nginx/sites-available/anime-gallery.conf /etc/nginx/sites-enabled/anime-gallery.conf
sudo nginx -t
sudo systemctl reload nginx
```

把 Nginx 示例中的 `gallery.example.com` 改成自己的域名，生产环境启用 HTTPS。

干净部署时，打开浏览器访问 `/install`。安装页会配置 SQLite 或 MySQL、写入 `.env`、执行迁移、初始化管理员账号、生成 `AGMS_AUTH_SECRET`，并创建 `installed.lock`。

如果安装页选择 MySQL，先创建空数据库和专用账号：

```sql
CREATE DATABASE anime_gallery
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'anime_gallery'@'127.0.0.1' IDENTIFIED BY 'change-this-db-password';
GRANT ALL PRIVILEGES ON anime_gallery.* TO 'anime_gallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

然后在安装页填写 MySQL 主机、端口、数据库名、用户名和密码。安装页提示需要重启时，重启后端服务即可。

只有明确跳过安装器，或升级已有部署时，才需要手动编辑 `.env` 和手动执行 Alembic 迁移。

## Release 包部署

GitHub Releases 会提供预构建部署包：

```text
MoeGallery-vX.Y.Z.zip
MoeGallery-vX.Y.Z.tar.gz
SHA256SUMS.txt
```

压缩包包含后端源码、Alembic 迁移、已构建的 `frontend/dist`、部署脚本、文档、`.env.example`，以及空的 `storage/` 和 `logs/` 目录。压缩包不会包含 `.env`、数据库文件、上传图片、日志、虚拟环境、`node_modules` 或私钥。

部署 Release 包：

```bash
sudo mkdir -p /opt/anime-gallery
sudo tar -xzf MoeGallery-vX.Y.Z.tar.gz -C /opt/anime-gallery --strip-components=1

cd /opt/anime-gallery
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r backend/requirements.txt
```

然后按上面的方式安装 systemd 服务和 Nginx 配置，打开 `/install`，在网页安装器里完成数据库、管理员和密钥初始化。已有部署升级前应先备份 `.env`、`storage/` 和数据库。

## 升级

已有部署可以使用包内升级脚本：

```bash
sudo bash /opt/anime-gallery/scripts/upgrade_release.sh /tmp/MoeGallery-vX.Y.Z.tar.gz
```

脚本会创建带时间戳的备份、停止服务、只替换程序文件、保留 `.env`、`installed.lock`、`storage/` 和数据库文件、更新 Python 依赖、执行 Alembic 迁移、重启服务，并检查 `/api/health`。

只备份不升级：

```bash
sudo bash /opt/anime-gallery/scripts/backup_before_upgrade.sh
```

备份会保存到 `/opt/anime-gallery/backups/upgrade-YYYYmmdd-HHMMSS/`。MySQL 使用 `mysqldump --single-transaction`，SQLite 使用 sqlite backup API。

## 自动 Release

仓库已通过 `.github/workflows/release.yml` 支持自动发布 GitHub Releases。

通过 tag 发布：

```bash
git tag v0.1.0
git push origin v0.1.0
```

也可以在 GitHub Actions 页面手动运行 `Release` workflow，填写 `v0.1.0` 这样的版本号。

workflow 会安装 Node.js 和 Python、检查后端语法、构建前端、运行 `scripts/package_release.py` 打包、上传 workflow artifact，并创建或更新 GitHub Release。

## ESA/CDN 后的真实客户端 IP

如果站点套了阿里云 ESA/CDN，需要把边缘节点提供的真实客户端 IP 传给后端。示例 Nginx 配置优先使用 `ali-real-client-ip`，兼容 `ali-cdn-real-ip` 和 `true-client-ip`，最后回退到 `$remote_addr`。

后端也会识别这些头，并且只信任来自本机/内网反向代理的转发头。生产环境建议通过安全组、防火墙或回源鉴权限制源站直连，避免外部伪造真实 IP 头。

## API

OpenAPI 文档地址：

```text
/api-docs
/api-docs/openapi.json
/openapi.json
```

API 文档需要管理员认证。运维自动化可以使用管理员会话 Cookie 或已配置的 operations API key。

## 安全说明

- 后台写操作需要有效的 HttpOnly 会话 Cookie。
- 带会话 Cookie 的非安全请求必须包含 CSRF token header。
- 登录失败会同时按客户端 IP 和用户名限流。
- API Key 只用于运维自动化，不应暴露给浏览器。
- `/storage/*` 通过后端受控路由输出，私有/隐藏文件不能直接按路径匿名获取。
- 如果后端使用多 worker 或多实例，登录限流计数应迁移到 Redis 等共享存储。
- 不要把 `.env`、数据库备份、上传媒体和私钥提交到公开仓库。

## 许可证

本项目源码基于 [MIT License](LICENSE) 开源。

上传图片、角色作品图、导入元数据和用户提供的媒体内容不自动包含在本仓库许可证范围内。
