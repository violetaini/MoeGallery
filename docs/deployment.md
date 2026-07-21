# MoeGallery Deployment Guide

This guide explains how to deploy MoeGallery on a Linux server that uses systemd. The installer installs the application, creates its system service, and configures the listen address. You remain responsible for domains, TLS certificates, firewalls, CDNs, and reverse proxies.

## Requirements

- Linux with systemd.
- Python 3.11 or newer.
- A listen address of either `127.0.0.1` or `0.0.0.0`.
- Port `8111` by default.
- SQLite, MySQL 8.x, or a compatible version of MariaDB.

The installer detects `apt`, `dnf`, and `yum`. Some RHEL-family distributions require an additional package repository for FFmpeg. After deployment, the System Health page in the admin panel shows which image codecs are actually available on the server.

## Recommended Installation

Download the installer from the latest GitHub release. Because the script runs as root, inspect it before installation:

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
less install.sh
sudo bash install.sh
```

In interactive mode, you only need to choose whether the service listens on `127.0.0.1` or `0.0.0.0`. The installer then:

1. Installs runtime packages.
2. Downloads `SHA256SUMS.txt` and the release archive.
3. Verifies the archive checksum.
4. Installs the application and Python environment.
5. Creates a dedicated `moegallery` service account with no login shell or root privileges.
6. Installs and starts `moegallery.service`.
7. Waits for the `/api/health` check to pass and prints the first-time setup URL.

Useful options:

```text
--host 127.0.0.1|0.0.0.0
--port 8111
--app-dir /opt/moegallery
--service moegallery
--user moegallery
--version vX.Y.Z
--github-proxy https://trusted-proxy.example/
--non-interactive
--reinstall
```

`--reinstall` reinstalls the application files while preserving `.env`, `installed.lock`, `storage/`, `logs/`, `backups/`, and the Python virtual environment. Use the Update Center in the admin panel for routine upgrades.

## Listen Addresses

### Local Access or Reverse Proxy

```bash
sudo bash install.sh --host 127.0.0.1 --port 8111 --non-interactive
```

The application listens only on the server's loopback interface at `http://127.0.0.1:8111`. To access it from another device, configure Nginx, Caddy, Apache, a hosting panel, or another reverse proxy, or use an SSH tunnel.

### Direct Network Access

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

Open `http://SERVER_IP:8111`. Plain HTTP does not encrypt admin credentials or cookies, so configure HTTPS before using this mode on a public or otherwise untrusted network.

The installer does not open the selected port in the server firewall or cloud security group.

## First-Time Setup

After the service starts and passes its health check, open the `/install` URL printed by the installation script.

### SQLite

Select SQLite and continue. The database file is stored in the default application directory, so no filesystem path is required.

### MySQL or MariaDB

Create an empty database and dedicated application account first. Example:

```sql
CREATE DATABASE moegallery CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'moegallery'@'127.0.0.1' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT ALL PRIVILEGES ON moegallery.* TO 'moegallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

Enter the host, port, database name, username, and password in `/install`. These connection details are written to `.env`, so use an account dedicated to the MoeGallery database. Do not enter the MySQL root account or another database administrator account.

The setup wizard generates the `AGMS_AUTH_SECRET` session-signing secret and an initial operations API key. It then runs the database migrations, writes `.env`, creates `installed.lock`, and asks the built-in launcher to restart the application.

## Service Management

```bash
sudo systemctl status moegallery
sudo systemctl restart moegallery
sudo journalctl -u moegallery -n 100 --no-pager
sudo journalctl -u moegallery -f
```

Default layout:

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

By default, this directory is owned by the `moegallery` service account. The account can run the application and manage MoeGallery's own files, but it has no login shell or root privileges. It is separate from the web admin account. The main installer accepts `--user` to use an existing system account; `scripts/install_systemd.sh` also accepts `--group` when a specific group is required.

## Updates from the Admin Panel

Updates are coordinated by the launcher built into the main service. Only `moegallery.service` is required; no separate updater service or passwordless sudo rule is installed.

The update sequence is:

1. The admin panel creates an update task in `storage/updates/`.
2. The launcher downloads the new release and its checksum while the site remains online.
3. After the files have been verified, the launcher stops the FastAPI child process.
4. It backs up the current application and database.
5. It replaces the application files, installs dependencies, and runs database migrations.
6. It starts the new version and checks `/api/health`.
7. If the update fails, it restores the application and database backups and starts the previous version.

MySQL backup and recovery require the `mysqldump` and `mysql` commands. The installer adds the required client tools on Debian and Ubuntu; on other distributions, confirm that both commands are available.

## Migrating from a v0.1.x Installation

If the existing installation still uses the separate updater service, first upgrade its files to a release that contains `moegallery_launcher.py`. Then run the service installer once with the current application path and service name:

```bash
sudo bash /CURRENT/APP/PATH/scripts/install_systemd.sh \
  --app-dir /CURRENT/APP/PATH \
  --service moegallery \
  --user moegallery \
  --group moegallery \
  --host 127.0.0.1 \
  --port 8111
```

This command stops the old service, installs a systemd service managed by the built-in launcher, updates ownership of the application directory, removes the legacy updater service and sudoers file, and restarts MoeGallery. It does not modify `.env`, the database, uploaded images, or existing reverse-proxy configuration.

## Manual Installation

If the server cannot use the network installer, install a downloaded release archive manually:

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

Before extracting the archive, verify it against `SHA256SUMS.txt` from the same release.

## Troubleshooting

### The port is not reachable

- Use `systemctl cat moegallery` to confirm the configured listen address.
- Use `systemctl status moegallery` to check the service state.
- Run `curl http://127.0.0.1:8111/api/health` on the server.
- With `0.0.0.0`, check the server firewall and cloud security group.
- With `127.0.0.1`, check the reverse proxy or SSH tunnel.

### The Update Center cannot install updates

This usually means the service is still running Uvicorn directly instead of using `moegallery_launcher.py`, or that required update scripts are missing. Run `scripts/install_systemd.sh` again, then inspect the `moegallery.service` logs.

### MySQL backup fails

Install the MySQL client tools and confirm that the dedicated database account can connect from the server. To prevent data loss, MoeGallery stops the update if the pre-update backup fails.

### First-time setup requests a restart

With a standard installation, the built-in launcher restarts the application automatically. If Uvicorn is running directly in a development environment, restart the backend manually.
