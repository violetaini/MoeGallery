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

MoeGallery 是一个可自行部署的二次元图片管理与展示系统。它包含供访客浏览的图片画廊和供管理员整理内容的后台，可统一管理图片、作品、角色、分级等信息，并提供批量导入、图片处理和 API 调用功能。

## 快速安装

下面的安装方式适用于使用 systemd 的 Linux。安装脚本会直接下载已经构建好的发布包，因此部署服务器不需要安装 Node.js。

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
sudo bash install.sh
```

首次运行时，安装脚本只会询问服务监听地址：

- `127.0.0.1`：只允许服务器本机访问，适合搭配 Nginx、宝塔或其他反向代理，推荐使用。
- `0.0.0.0`：监听所有网络接口，可通过服务器 IP 从局域网或公网访问。

默认端口为 `8111`。安装完成后，脚本会输出首次安装页面的地址。使用默认监听方式时，可先在服务器本机访问：

```text
http://127.0.0.1:8111/install
```

如果需要从其他电脑访问，请先配置反向代理或 SSH 隧道；选择 `0.0.0.0` 时，也可以访问 `http://服务器IP:8111/install`。

随后在网页中选择数据库并设置后台管理员账号。MoeGallery 会自动生成会话签名密钥和初始 API 密钥，执行数据库迁移，初始化存储目录，并记录安装状态。

| 数据库 | 操作 |
| --- | --- |
| SQLite | 直接选择 SQLite。数据库文件保存在程序默认目录，无需填写路径。 |
| MySQL / MariaDB | 先创建空数据库和专用应用账号，再在安装页填写连接信息。 |

如需无人值守安装并监听所有网络接口：

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

安装脚本只负责部署 MoeGallery，不会配置域名、TLS 证书、防火墙、CDN 或反向代理。监听方式、服务管理、MySQL 准备和手工安装等内容见[部署说明](docs/deployment_zh.md)。

## 安装内容

- 程序默认安装到 `/opt/moegallery`。
- 安装一个名为 `moegallery.service` 的 systemd 服务。
- 默认创建不能登录系统、没有 root 权限的 `moegallery` 服务用户，专门用于运行程序和读写 MoeGallery 自身目录。它与后台管理员账号无关，也可以通过 `--user` 参数改用已有的系统用户。
- 由内置启动器运行 FastAPI，并负责后台更新、健康检查和失败回滚。
- FastAPI 同时提供 API 与编译后的前端页面，部署时只需一个端口。

更新功能已经包含在主服务中，不需要额外的更新服务，也不会配置 sudo 免密规则。

## 主要功能

- 全屏幻灯片首页，可在后台指定展示图片；未指定时会从图库中随机选择。
- 瀑布流图片库，支持搜索、排序，以及按作品、角色和分级筛选。
- 滚动到底部后自动加载下一页，并提前预加载即将展示的图片。
- 点击图片即可在当前页面查看详情，同时保留可直接访问的独立详情地址。
- 作品页和角色页采用媒体库式布局，支持背景图、封面、头像和分页。
- 使用 `safe`、`sensitive`、`hidden` 三个固定分级。
- 后台图片管理可在经典表格和瀑布画廊之间切换，并支持批量操作。
- 批量上传提供文件预览、重复检测、处理队列、失败重试和元数据绑定。
- 提供 CSV、JSON、XLSX 和 XLSM 批量导入模板。
- 首次安装时可选择 SQLite 或 MySQL/MariaDB。
- 提供 HttpOnly 管理员会话、CSRF 校验、登录限流、API 密钥和自动生成的强随机会话密钥。
- 可在后台检查 GitHub 上的新版本、校验更新包、备份数据库、执行迁移和健康检查；新版本启动失败时会自动恢复。

## 图片处理

| 上传类型 | 入库存储 | 浏览器展示 |
| --- | --- | --- |
| 普通静态图片 | 转换为 WebP | 使用 WebP 预览图和缩略图 |
| GIF 或其他动图 | 保留原动画格式 | 使用静态 WebP 预览图和缩略图 |
| JXR / HDR 图片 | 转换为包含 `nclx / mdcv / clli` 元数据的 HDR AVIF | 在普通页面中使用 SDR WebP 预览图和缩略图 |
| 其他高位深图片 | 格式受支持时保留 HDR 原图 | 在普通页面中使用 SDR WebP 预览图和缩略图 |

允许上传的常见后缀：

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

上传时不仅检查文件后缀，还会实际尝试解析图片。后缀伪装或服务器无法解码的文件会被拒绝。

## 更新与备份

安装完成后，可在**后台 > 更新中心**直接升级。下载和校验更新包时网站保持在线；只有在替换程序文件和执行数据库迁移时，Web 服务才会短暂停止。新版本启动后会自动检查 `/api/health`，如果检查失败，系统会恢复更新前的程序和数据库，再重新启动旧版本。

手工备份：

```bash
sudo -u moegallery bash /opt/moegallery/scripts/backup_before_upgrade.sh \
  --app-dir /opt/moegallery
```

SQLite 通过 SQLite Backup API 创建一致性备份；MySQL/MariaDB 使用 `mysqldump --single-transaction --no-tablespaces`，因此服务器需要安装 MySQL 客户端工具。

## 文档

- [部署说明](docs/deployment_zh.md)
- [Deployment guide](docs/deployment.md)
- [API 运维指南](docs/api/operations-guide.md)
- 管理员登录后的交互式 API 文档：`/api-docs`
- OpenAPI 文件：`docs/api/openapi.json`

## 本地开发

参与本地开发需要 Python 3.11 或更高版本，以及 Node.js 20 或更高版本。

```bash
# 后端
python -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000

# 在另一个终端启动前端
cd frontend
npm ci
npm run dev
```

前端开发服务器地址为 `http://127.0.0.1:5173`。开发服务器会把 API 和存储请求代理到本机 `8000` 端口的后端。

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

- 不要把 `.env`、`installed.lock`、数据库、上传图片、备份或私钥提交到 Git。
- 通过公网访问后台前，请先配置 HTTPS，避免管理员密码和 Cookie 以明文传输。
- 为 MoeGallery 创建独立的 MySQL 账号，不要使用数据库的 root 或其他管理员账号。
- 不要关闭发布包的 SHA256 校验；需要使用 GitHub 代理时，只填写自己信任的地址。
- 发现安全问题时请私下报告，不要公开账号、密钥或漏洞利用细节。

## 许可证

MoeGallery 使用 [MIT License](LICENSE)。
