# MoeGallery 部署说明

本文说明 MoeGallery 支持的 Linux 裸机部署。项目只配置应用服务、监听地址和端口；域名、TLS 证书、防火墙、CDN 和反向代理站点由运维自行管理。

## 支持范围

- 使用 systemd 的 Linux。
- Python 3.11 或更新版本。
- 监听 `127.0.0.1` 或 `0.0.0.0`。
- 默认端口 `8111`。
- SQLite、MySQL 8.x 或兼容版本的 MariaDB。

安装器支持 `apt`、`dnf` 和 `yum`。RHEL 系发行版可能需要额外的软件源才能安装 FFmpeg；安装后可以在系统健康面板检查实际解码和编码能力。

## 推荐安装

从最新 Release 下载安装脚本。脚本需要 root 权限，建议执行前先查看内容：

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
less install.sh
sudo bash install.sh
```

交互式安装器只询问监听 `127.0.0.1` 还是 `0.0.0.0`，其余步骤自动完成：

1. 安装运行依赖。
2. 下载 `SHA256SUMS.txt` 和 Release 压缩包。
3. 校验压缩包 SHA256。
4. 安装程序和 Python 虚拟环境。
5. 创建专用的 `moegallery` 用户。
6. 安装并启动唯一的 `moegallery.service`。
7. 等待 `/api/health` 正常并输出首次安装地址。

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

`--reinstall` 会替换程序文件，但保留 `.env`、`installed.lock`、`storage/`、`logs/`、`backups/` 和虚拟环境。正常升级应使用后台更新中心。

## 监听方式

### 仅本机或反向代理

```bash
sudo bash install.sh --host 127.0.0.1 --port 8111 --non-interactive
```

应用只在服务器本机的 `http://127.0.0.1:8111` 提供服务。宝塔、Nginx、Caddy、Apache、SSH 隧道或其他反向代理需要单独配置。

### 直接通过网络访问

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

通过 `http://服务器IP:8111` 访问。普通 HTTP 不会加密管理员账号、密码和 Cookie，通过不可信网络使用前应自行配置 HTTPS。

安装器不会自动开放服务器或云平台防火墙端口。

## 首次安装

服务健康后打开 `/install`。

### SQLite

选择 SQLite 后继续。数据库文件保存在 MoeGallery 决定的默认位置，不需要填写文件路径。

### MySQL 或 MariaDB

先创建空数据库和专用应用账号：

```sql
CREATE DATABASE moegallery CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'moegallery'@'127.0.0.1' IDENTIFIED BY '替换为强密码';
GRANT ALL PRIVILEGES ON moegallery.* TO 'moegallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

在 `/install` 填写主机、端口、数据库、用户名和密码。MoeGallery 不会保存数据库管理员账号。

安装页会自动生成 `AGMS_AUTH_SECRET` 和初始运维 API Key，执行 Alembic 迁移，写入 `.env`，创建 `installed.lock`，并通知内置启动器自动重启。

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

专用 `moegallery` 用户拥有该目录，使内置启动器可以在不使用 root 的情况下安装通过校验的 Release。

## 面板更新

MoeGallery 只使用一个主服务，不再存在 `moegallery-updater@.service`，也不再添加 updater sudoers 规则。

更新顺序：

1. 面板在 `storage/updates/` 创建任务。
2. 启动器在网站保持在线时下载 Release 和校验文件。
3. 校验完成后只停止 FastAPI 子进程。
4. 备份程序文件和当前数据库。
5. 替换程序、安装依赖并执行迁移。
6. 启动新版本并检查 `/api/health`。
7. 失败时恢复程序和数据库备份，再启动旧版本。

MySQL 自动恢复依赖 `mysqldump` 和 `mysql` 命令。Debian/Ubuntu 的推荐安装器会安装对应客户端工具。

## 从旧 updater 部署迁移

将程序文件升级到包含 `moegallery_launcher.py` 的 Release 后，使用现有程序路径和服务名执行一次：

```bash
sudo bash /当前程序路径/scripts/install_systemd.sh \
  --app-dir /当前程序路径 \
  --service moegallery \
  --user moegallery \
  --group moegallery \
  --host 127.0.0.1 \
  --port 8111
```

该命令会停止旧主服务、安装基于启动器的新 unit、将程序目录交给专用用户、删除旧 updater unit 和 sudoers 文件，然后启动新服务。它不会修改 `.env`、数据库、图片或现有反向代理配置。

## 手工安装 Release

无法运行联网安装器时：

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

解压前必须使用 Release 中的 `SHA256SUMS.txt` 校验压缩包。

## 常见问题

### 端口无法访问

- 使用 `systemctl cat moegallery` 确认监听地址。
- 使用 `systemctl status moegallery` 确认服务状态。
- 在服务器执行 `curl http://127.0.0.1:8111/api/health`。
- `0.0.0.0` 模式检查服务器和云平台防火墙。
- `127.0.0.1` 模式检查自行维护的反向代理。

### 更新中心只能下载校验

当前程序可能直接通过 Uvicorn 启动，没有使用 `moegallery_launcher.py`，或者更新脚本缺失。重新执行 `scripts/install_systemd.sh` 并检查主服务日志。

### MySQL 备份失败

安装 MySQL 客户端工具，并确认专用数据库账号可以从服务器连接。更新前备份失败时，程序不会继续安装更新。

### 首次安装提示重启

标准启动器部署会自动重启。开发环境直接启动的 Uvicorn 没有父启动器，需要手动重启。
