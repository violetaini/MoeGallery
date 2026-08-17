# MoeGallery 部署说明

本文介绍如何在使用 systemd 的 Linux 服务器上部署 MoeGallery。安装器只负责安装应用、创建系统服务并设置监听地址；域名、TLS 证书、防火墙、CDN 和反向代理需要另行配置。

## 支持范围

- 使用 systemd 的 Linux 发行版。
- Python 3.11 或更高版本。
- 监听 `127.0.0.1` 或 `0.0.0.0`。
- 默认端口 `8111`。
- SQLite、MySQL 8.x 或兼容版本的 MariaDB。

安装器可以识别 `apt`、`dnf` 和 `yum`。部分 RHEL 系发行版需要启用额外的软件源才能安装 FFmpeg。部署完成后，可在后台的系统健康页面检查服务器实际支持的图片编解码能力。

## 推荐安装

从最新的 GitHub 发布版本下载安装脚本。脚本需要 root 权限，建议先查看脚本内容，再执行安装：

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
less install.sh
sudo bash install.sh
```

交互模式只需选择监听 `127.0.0.1` 还是 `0.0.0.0`，其余步骤由安装器自动完成：

1. 安装运行依赖。
2. 下载 `SHA256SUMS.txt` 和程序压缩包。
3. 核对压缩包的 SHA256 校验值。
4. 安装程序和 Python 虚拟环境。
5. 创建不能登录系统、没有 root 权限的 `moegallery` 服务用户。
6. 安装并启动唯一的 `moegallery.service`。
7. 等待 `/api/health` 健康检查通过，并输出首次安装地址。

常用参数：

```text
--host 127.0.0.1|0.0.0.0
--port 8111
--app-dir /opt/moegallery
--service moegallery
--user moegallery
--version vX.Y.Z
--github-proxy https://可信代理.example/
--non-interactive
--reinstall
```

`--reinstall` 用于重新安装程序文件，同时保留 `.env`、`installed.lock`、SQLite 数据库、`storage/`、`logs/`、`backups/` 和 Python 虚拟环境。日常升级请使用后台的更新中心。

## 监听方式

### 仅本机或反向代理

```bash
sudo bash install.sh --host 127.0.0.1 --port 8111 --non-interactive
```

应用只监听服务器本机的 `http://127.0.0.1:8111`。如需从其他设备访问，可自行配置宝塔、Nginx、Caddy、Apache 等反向代理，也可以使用 SSH 隧道。

### 直接通过网络访问

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

此模式可通过 `http://服务器IP:8111` 访问。普通 HTTP 无法加密管理员账号、密码和 Cookie，因此在公网使用前必须配置 HTTPS。

安装器不会自动开放服务器或云平台防火墙端口。

## 反向代理与真实客户端 IP

后端默认只信任来自本机回环地址（`127.0.0.0/8`、`::1/128`）的客户端 IP 转发头，适用于同机部署的宝塔或 Nginx。反向代理必须覆盖外部请求携带的转发头，不能原样透传：

```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header Ali-Real-Client-IP "";
proxy_set_header Ali-Cdn-Real-Ip "";
proxy_set_header True-Client-IP "";
```

如果反向代理位于另一台服务器或容器网络中，把它的精确网段加入 `.env`，然后重启服务：

```env
AGMS_TRUSTED_PROXY_CIDRS=127.0.0.0/8,::1/128,10.20.30.0/24
```

不要配置 `0.0.0.0/0` 或 `::/0`，否则任意访问者都可以伪造 IP，削弱登录和首次安装限速。接入 CDN 时，应在 Nginx 的 `http` 或 `server` 配置中使用 CDN 官方公布的出口网段和 `real_ip` 模块，例如：

```nginx
set_real_ip_from 203.0.113.0/24; # 替换为 CDN 官方网段，可配置多行
real_ip_header True-Client-IP;   # 替换为 CDN 官方指定的请求头
real_ip_recursive on;
```

只有来自 `set_real_ip_from` 网段的请求头才会被 Nginx 接受；随后仍使用上面的 `$remote_addr` 规则转发给 MoeGallery。不要直接根据一个非空请求头改写客户端 IP。

## 图片发送与缓存

默认配置无需额外组件，FastAPI 会直接发送图片。公开图片默认允许浏览器缓存 7 天、共享缓存或 CDN 缓存 30 天；每次媒体内容或访问策略变更都会切换到新的版本化 URL，因此不会被旧缓存阻挡。私有和隐藏图片禁止共享缓存。可在 `.env` 中调整：

```env
AGMS_MEDIA_PUBLIC_BROWSER_CACHE_SECONDS=604800
AGMS_MEDIA_PUBLIC_SHARED_CACHE_SECONDS=2592000
AGMS_MEDIA_ACCEL_REDIRECT_PREFIX=
```

如果 Nginx 直接托管 `frontend/dist`，并通过 `try_files` 把前端路由回退到 `index.html`，必须在前端回退规则之前把 `/media/` 转发给应用，否则图片请求会被错误地返回为 HTML：

```nginx
location ^~ /media/ {
    proxy_pass http://127.0.0.1:8111/media/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Ali-Real-Client-IP "";
    proxy_set_header Ali-Cdn-Real-Ip "";
    proxy_set_header True-Client-IP "";
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

如图片数量和并发访问明显增加，可让 Nginx 通过内部地址发送文件。该模式是可选优化，不影响首次安装，也不涉及域名配置：

```nginx
location ^~ /_agms_media/ {
    internal;
    alias /opt/moegallery/storage/;
}

location / {
    proxy_pass http://127.0.0.1:8111;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Ali-Real-Client-IP "";
    proxy_set_header Ali-Cdn-Real-Ip "";
    proxy_set_header True-Client-IP "";
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

然后设置并重启服务：

```env
AGMS_MEDIA_ACCEL_REDIRECT_PREFIX=/_agms_media
```

Nginx worker 必须对 `/opt/moegallery/storage/` 具有只读和目录遍历权限。配置不一致时图片会返回错误，因此修改后应在“系统设置 > 系统健康”确认显示“`Nginx 发送`”，并实际打开原图、预览图和缩略图检查。CDN 只应按源站响应头缓存公开的 `/media/*`，不能强制缓存带 `private` 或 `no-store` 的响应。旧 `/storage/*` 仅用于兼容客户端。

## 图片分享

在“图片管理”中选择一张或多张图片后点击“分享”，可以复制普通图床格式的原图 URL、Markdown 或论坛 BBCode。普通格式只适用于公开且非隐藏图片。

“相册分享”会生成一个不可猜测的 `/s/:token` 页面：一张图片显示为单图页，多张图片按选择顺序显示为相册。创建时可设为永久、1 天、7 天或 30 天有效；到期后，分享页和附带令牌的图片链接都会立即失效。它也会提供带访问授权的 URL、Markdown 和 BBCode，因此可有选择地分享非公开或隐藏图片。管理员可以在“分享管理”中预览所含图片、查看状态，并通过复制、撤销、修改三个操作管理链接；图片详情每页显示 12 张，修改标题或有效期后，有限期会从保存时重新计算。带令牌的媒体响应始终使用 `private, no-store`，不要让 CDN 强制缓存。

## 首次安装

服务启动并通过健康检查后，完整打开安装脚本输出的首次安装地址。地址中的 `#token=...` 是一次性安装令牌，网页会自动读取并立即从地址栏清除，不需要手工填写。

令牌只在安装尚未完成时生成，有效期为两小时，安装成功后立即销毁。没有正确令牌的请求不能创建管理员或修改安装状态；同一时间也只允许一个安装任务执行。地址遗失或过期时，重启服务并读取最新地址：

```bash
sudo systemctl restart moegallery
sudo journalctl -u moegallery -n 100 --no-pager -o cat \
  | grep '^\[setup\] First install:' \
  | tail -n 1
```

管理员密码至少需要 12 个字符，不能与用户名相同，也不能使用常见默认密码。

### SQLite

选择 SQLite 后直接继续。数据库文件会保存在程序默认目录中，无需填写存储路径。

文件型 SQLite 会自动启用 WAL、外键检查和 8 秒忙等待；上传队列最多同时运行 4 个 worker，避免多个写事务互相锁住。默认 `AGMS_SQLITE_SYNCHRONOUS=NORMAL` 适合 SSD 上的图库服务；它在突然断电时可能丢失最后极少量已提交事务。对断电一致性要求更高时，在 `.env` 设置 `AGMS_SQLITE_SYNCHRONOUS=FULL` 后重启服务。需要调整等待时间或 worker 上限时，可设置 `AGMS_SQLITE_BUSY_TIMEOUT_MS` 与 `AGMS_SQLITE_UPLOAD_WORKER_LIMIT`。

### MySQL 或 MariaDB

先创建空数据库和专用应用账号：

```sql
CREATE DATABASE moegallery CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'moegallery'@'127.0.0.1' IDENTIFIED BY '替换为强密码';
GRANT ALL PRIVILEGES ON moegallery.* TO 'moegallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

在 `/install` 中填写主机、端口、数据库名、用户名和密码。数据库连接信息会写入 `.env`，因此请务必使用只管理 MoeGallery 数据库的专用账号，不要填写 MySQL 的 root 或其他管理员账号。

MySQL 8 会使用 `SKIP LOCKED` 并行领取上传任务。默认连接池为 24 个常驻连接和 40 个溢出连接，预留部分连接给网页请求；上传 worker 的实际可用上限会在后台设置和系统健康中显示。可在 `.env` 调整 `AGMS_MYSQL_POOL_SIZE`、`AGMS_MYSQL_MAX_OVERFLOW`、`AGMS_MYSQL_POOL_TIMEOUT_SECONDS`、`AGMS_MYSQL_POOL_RECYCLE_SECONDS` 及连接读写超时；这些参数只在服务启动时读取，修改后必须重启服务。

安装页面会自动生成会话签名密钥 `AGMS_AUTH_SECRET` 和初始 API Key，然后执行数据库迁移、写入 `.env`、创建 `installed.lock`，最后通知内置启动器重启应用。

## 服务管理

```bash
sudo systemctl status moegallery
sudo systemctl restart moegallery
sudo journalctl -u moegallery -n 100 --no-pager
sudo journalctl -u moegallery -f
```

默认目录：

```text
/opt/moegallery/
  backend/
  frontend/dist/
  scripts/
  venv/
  storage/
  backups/
  logs/
  .env
  installed.lock
```

默认情况下，以上目录归 `moegallery` 服务用户所有。这个账号只能运行应用和读写 MoeGallery 自身文件，不能登录系统，也没有 root 权限。它与网页中的后台管理员账号没有关系。使用主安装器时可通过 `--user` 改用已有账号；直接运行 `scripts/install_systemd.sh` 时，还可以通过 `--group` 指定用户组。

## 定期备份与恢复

后台更新前会创建轻量级回滚备份。除此之外，建议每天创建一次完整的定期备份；它会同时保存数据库、程序配置、原图、缩略图和 HDR 图片的 SDR 预览图。上传暂存任务、更新下载文件和运行时锁不会备份，避免恢复过期任务。

```bash
sudo -u moegallery bash /opt/moegallery/scripts/backup_gallery.sh \
  --app-dir /opt/moegallery \
  --keep-days 14
```

定期备份保存在 `/opt/moegallery/backups/scheduled/`，只会清理该目录下超过保留天数的 `upgrade-*` 备份；面板更新产生的其他备份不会被此脚本删除。可先使用 `--dry-run` 查看计划操作。以 root 的 crontab 为例，每天凌晨 03:20 执行：

```cron
20 3 * * * sudo -u moegallery bash /opt/moegallery/scripts/backup_gallery.sh --app-dir /opt/moegallery --keep-days 14 >> /opt/moegallery/logs/backup.log 2>&1
```

恢复前先停止服务，再选择一个完整备份目录执行恢复，最后启动服务：

```bash
sudo systemctl stop moegallery
sudo bash /opt/moegallery/scripts/restore_upgrade_backup.sh \
  --app-dir /opt/moegallery \
  --backup-dir /opt/moegallery/backups/scheduled/upgrade-YYYYMMDD-HHMMSS
sudo systemctl start moegallery
```

备份中包含 `.env` 和数据库凭据，目录权限会限制为仅所有者可读写。它不能替代异地灾备：请将已加密的定期备份复制到另一块磁盘或其他可信位置。MySQL 恢复仍需要 `mysqldump` 和 `mysql` 客户端命令。

## 自动验证

GitHub 会在任意分支推送、Pull Request 和每周计划任务中运行验证：SQLite 全量后端测试、真实 MySQL 8 迁移与并发领取、SQLite/MySQL 备份恢复演练、前端生产构建，以及 Chromium 的桌面和手机端关键流程。发布工作流也必须先通过独立的 MySQL 8 验证和恢复演练，才会生成发布包。

## 面板更新

MoeGallery 的更新功能由主服务内置的启动器完成。系统中只有一个 `moegallery.service`，无需额外安装更新服务，也不会添加 sudo 免密规则。

更新顺序：

1. 后台在 `storage/updates/` 中创建更新任务。
2. 启动器在网站保持在线的情况下下载新版本及其校验文件。
3. 文件校验通过后，启动器停止 FastAPI 子进程。
4. 备份当前程序和数据库。
5. 替换程序文件、安装依赖并执行数据库迁移。
6. 启动新版本，并通过 `/api/health` 检查运行状态。
7. 如果更新失败，恢复程序和数据库备份，再启动原来的版本。

MySQL 的备份和恢复依赖 `mysqldump` 与 `mysql` 命令。安装器会在 Debian 和 Ubuntu 上安装所需的客户端工具；其他发行版请确认这些命令已经可用。

## 从 v0.1.x 旧版部署迁移

如果旧版本仍使用独立的 updater 服务，请先把程序文件升级到包含 `moegallery_launcher.py` 的版本，再按现有程序路径和服务名执行一次：

```bash
sudo bash /当前程序路径/scripts/install_systemd.sh \
  --app-dir /当前程序路径 \
  --service moegallery \
  --user moegallery \
  --group moegallery \
  --host 127.0.0.1 \
  --port 8111
```

该命令会停止旧服务，安装由内置启动器管理的新 systemd 服务，调整程序目录权限，删除旧的 updater 服务和 sudoers 文件，然后重新启动 MoeGallery。它不会修改 `.env`、数据库、图片或已有的反向代理配置。

## 手工安装发布包

无法使用联网安装器时，可以手工安装下载好的发布包：

```bash
sudo mkdir -p /opt/moegallery
sudo tar -xzf MoeGallery-vX.Y.Z.tar.gz -C /opt/moegallery --strip-components=1
sudo python3 -m venv /opt/moegallery/venv
sudo /opt/moegallery/venv/bin/python -m pip install "pip==26.2"
sudo /opt/moegallery/venv/bin/python -m pip install --require-hashes -r /opt/moegallery/backend/requirements.lock.txt
sudo bash /opt/moegallery/scripts/install_systemd.sh \
  --app-dir /opt/moegallery \
  --host 127.0.0.1 \
  --port 8111
```

解压前必须使用同一发布版本中的 `SHA256SUMS.txt` 校验压缩包。
依赖锁维护与安全升级流程见 [依赖安全维护](dependency-security_zh.md)。

## 常见问题

### 端口无法访问

- 使用 `systemctl cat moegallery` 确认监听地址。
- 使用 `systemctl status moegallery` 确认服务状态。
- 在服务器执行 `curl http://127.0.0.1:8111/api/health`。
- 使用 `0.0.0.0` 时，检查服务器防火墙和云平台安全组。
- 使用 `127.0.0.1` 时，检查反向代理或 SSH 隧道配置。

### 更新中心只能下载校验

这通常表示当前服务仍然直接运行 Uvicorn，没有使用 `moegallery_launcher.py`，或者更新脚本不完整。请重新执行 `scripts/install_systemd.sh`，然后检查 `moegallery.service` 的日志。

### MySQL 备份失败

请安装 MySQL 客户端工具，并确认专用数据库账号可以在服务器上正常连接。为避免数据损坏，更新前的备份一旦失败，程序就会终止更新。

### 首次安装提示重启

使用标准安装方式时，内置启动器会自动重启应用。开发环境如果直接运行 Uvicorn，则需要手动重启后端。
