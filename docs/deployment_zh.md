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

## 首次安装

服务启动并通过健康检查后，打开安装脚本输出的 `/install` 地址。

### SQLite

选择 SQLite 后直接继续。数据库文件会保存在程序默认目录中，无需填写存储路径。

### MySQL 或 MariaDB

先创建空数据库和专用应用账号：

```sql
CREATE DATABASE moegallery CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'moegallery'@'127.0.0.1' IDENTIFIED BY '替换为强密码';
GRANT ALL PRIVILEGES ON moegallery.* TO 'moegallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

在 `/install` 中填写主机、端口、数据库名、用户名和密码。数据库连接信息会写入 `.env`，因此请务必使用只管理 MoeGallery 数据库的专用账号，不要填写 MySQL 的 root 或其他管理员账号。

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
sudo /opt/moegallery/venv/bin/pip install -r /opt/moegallery/backend/requirements.txt
sudo bash /opt/moegallery/scripts/install_systemd.sh \
  --app-dir /opt/moegallery \
  --host 127.0.0.1 \
  --port 8111
```

解压前必须使用同一发布版本中的 `SHA256SUMS.txt` 校验压缩包。

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
