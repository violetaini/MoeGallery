<div align="center">

<img src="frontend/public/avatar.webp" alt="MoeGallery" width="120" />

# **MoeGallery**

[![Release](https://img.shields.io/github/v/release/violetaini/MoeGallery?style=for-the-badge)](https://github.com/violetaini/MoeGallery/releases/latest)
[![Frontend](https://img.shields.io/badge/Frontend-Vue%203%20%2B%20Vite-42b883?style=for-the-badge)](frontend/package.json)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20SQLAlchemy-009688?style=for-the-badge)](backend/requirements.txt)
[![Database](https://img.shields.io/badge/Database-MySQL%20%2F%20SQLite-2563eb?style=for-the-badge)](.env.example)
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
  <a href="https://github.com/violetaini/MoeGallery/releases">Release</a>
</p>

MoeGallery 是一个自托管的二次元图片媒体库，提供访客画廊和管理后台，用于维护图片、作品、角色、分级、元数据、图片处理任务和 API。

## 快速安装

推荐安装器面向使用 systemd 的 Linux，并直接安装已经构建好的 Release。部署时不需要 Node.js。

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
sudo bash install.sh
```

安装脚本只询问监听方式：

- `127.0.0.1`：仅本机访问或自行配置反向代理，推荐。
- `0.0.0.0`：直接通过公网或局域网访问。

默认端口为 `8111`。服务启动后打开：

```text
http://服务器IP:8111/install
```

网页安装器继续完成数据库选择、管理员账号、数据库迁移、登录密钥、API Key、存储目录和安装锁初始化。

| 数据库 | 操作 |
| --- | --- |
| SQLite | 选择 SQLite 后继续，数据库文件位置由 MoeGallery 决定。 |
| MySQL / MariaDB | 先创建空数据库和专用账号，再填写连接信息。 |

无人值守并直接监听公网：

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

MoeGallery 不创建域名、TLS 证书、防火墙规则或反向代理站点。监听方式、服务命令、MySQL 准备、手工安装和旧版迁移见[部署说明](docs/deployment_zh.md)。

## 安装内容

- 默认安装到 `/opt/moegallery`。
- 只创建一个 `moegallery.service` systemd 服务。
- 创建专用的非 root 用户 `moegallery`。
- 内置启动器负责启动 FastAPI 和协调面板更新。
- 后端在同一端口直接提供已经构建好的前端。

项目不再安装独立 updater 服务，也不再写入 updater sudoers 规则。

## 主要功能

- 可由后台选择图片的全屏幻灯片首页。
- 瀑布流图片库，支持搜索、作品/角色/分级筛选、排序、自动加载和预加载。
- 当前页面图片详情浮层，同时保留独立详情路由。
- 媒体库风格的作品页和角色页，支持背景、封面、头像和分页。
- 固定 `safe`、`sensitive`、`hidden` 三种分级。
- 后台图片管理支持经典表格和瀑布画廊，并提供批量操作。
- 批量上传支持预览、重复预检、处理队列、失败重试和元数据绑定。
- CSV、JSON、XLSX、XLSM 批量导入模板。
- 首次部署可选择 SQLite 或 MySQL/MariaDB。
- HttpOnly 管理员会话、CSRF 校验、登录限流、API Key 和自动生成的强密钥。
- 面板检查 Release、校验更新包、备份数据库、执行迁移、健康检查并在失败时自动恢复。

## 图片管线

| 来源 | 原图入库 | 浏览器预览 |
| --- | --- | --- |
| 普通静态图片 | 转为 WebP | WebP 预览图和缩略图 |
| GIF / 动图 | 保留动画格式 | 静态 WebP 预览图和缩略图 |
| JXR / HDR | 转为带 `nclx / mdcv / clli` 的 HDR AVIF | SDR WebP 预览图和缩略图 |
| 其他高位深图片 | 保留兼容的 HDR 原图 | SDR WebP 预览图和缩略图 |

允许上传的常见后缀：

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

后端同时校验后缀和真实解码能力，伪装文件和无法解码的文件会被拒绝。

## 更新与备份

安装完成后通过**后台 > 更新中心**更新。内置启动器会在网站在线时下载并校验 Release，安装和迁移时短暂停止 Web 子进程，随后重新启动并执行健康检查；检查失败会恢复更新前的程序和数据库备份。

手工备份：

```bash
sudo -u moegallery bash /opt/moegallery/scripts/backup_before_upgrade.sh \
  --app-dir /opt/moegallery
```

SQLite 使用 SQLite backup API；MySQL/MariaDB 使用 `mysqldump --single-transaction`，因此需要安装 MySQL 客户端工具。

## 文档

- [部署说明](docs/deployment_zh.md)
- [Deployment guide](docs/deployment.md)
- [API 运维指南](docs/api/operations-guide.md)
- 管理员登录后的交互式 API 文档：`/api-docs`
- OpenAPI 文件：`docs/api/openapi.json`

## 本地开发

本地开发需要 Python 3.11 或更新版本，以及 Node.js 20 或更新版本。

```bash
# 后端
python -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000

# 新终端启动前端
cd frontend
npm ci
npm run dev
```

前端开发服务器位于 `http://127.0.0.1:5173`，并将 API 和存储请求代理到 `8000` 端口。

## 主要路由

```text
/                首页幻灯片
/gallery         图片库
/works           作品
/characters      角色
/tags            分级
/admin            管理后台
/install          首次安装
/api-docs         管理员 API 文档
```

## 安全

- 不要将 `.env`、`installed.lock`、数据库、上传图片、备份和私钥提交到 Git。
- 通过不可信网络开放管理员登录前应自行配置 HTTPS。
- MySQL 使用专用账号，不要使用数据库管理员账号。
- 保持 Release SHA256 校验，只在必要时配置可信的 GitHub 代理。
- 安全问题请私下报告，不要公开账号、密钥或利用细节。

## 许可证

MoeGallery 使用 [MIT License](LICENSE)。
