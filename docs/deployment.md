# MoeGallery Deployment

This guide covers the supported bare-metal Linux deployment. MoeGallery configures its application service and listen address only. Domains, TLS certificates, firewall policy, CDN settings, and reverse-proxy sites remain under the operator's control.

## Supported Path

- Linux with systemd.
- Python 3.11 or newer.
- `127.0.0.1` or `0.0.0.0` listen address.
- Port `8111` by default.
- SQLite, MySQL 8.x, or a compatible MariaDB release.

The installer supports `apt`, `dnf`, and `yum`. FFmpeg may require an additional repository on RHEL-family systems. The application health panel reports the available decoder and encoder capabilities after installation.

## Recommended Installation

Download the installer from the latest Release and inspect it before running it as root:

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
less install.sh
sudo bash install.sh
```

The interactive installer asks whether to bind to `127.0.0.1` or `0.0.0.0`. It then:

1. Installs runtime packages.
2. Downloads `SHA256SUMS.txt` and the Release archive.
3. Verifies the archive checksum.
4. Installs the application and Python environment.
5. Creates the dedicated `moegallery` account.
6. Installs and starts `moegallery.service`.
7. Waits for `/api/health` and prints the first-install URL.

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

`--reinstall` replaces application files while preserving `.env`, `installed.lock`, `storage/`, `logs/`, `backups/`, and the virtual environment. Use the panel Update Center for normal upgrades.

## Listen Address

### Local Or Reverse Proxy

```bash
sudo bash install.sh --host 127.0.0.1 --port 8111 --non-interactive
```

The application is available only on the server at `http://127.0.0.1:8111`. Configure BaoTa, Nginx, Caddy, Apache, an SSH tunnel, or another proxy separately.

### Direct Network Access

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

Open `http://SERVER_IP:8111`. Direct HTTP does not encrypt administrator credentials or cookies. Configure HTTPS before using this mode over an untrusted network.

The installer does not open the selected port in the host or cloud firewall.

## First Install

Open `/install` after the service becomes healthy.

### SQLite

Select SQLite and continue. MoeGallery stores the database in its managed default location. Do not enter a filesystem path.

### MySQL Or MariaDB

Create an empty database and dedicated application account first. Example:

```sql
CREATE DATABASE moegallery CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'moegallery'@'127.0.0.1' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT ALL PRIVILEGES ON moegallery.* TO 'moegallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

Enter that host, port, database, username, and password in `/install`. Database administrator credentials are not stored by MoeGallery.

The wizard generates `AGMS_AUTH_SECRET` and the initial operations API Key, runs Alembic migrations, writes `.env`, creates `installed.lock`, and requests an automatic restart from the built-in launcher.

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

The `moegallery` account owns this directory because the built-in launcher installs checksum-verified Releases without root privileges.

## Panel Updates

MoeGallery uses one service. There is no `moegallery-updater@.service` and no updater sudoers entry.

The update sequence is:

1. The panel creates a task in `storage/updates/`.
2. The launcher downloads the Release and checksum while the site remains online.
3. After verification, the launcher stops only the FastAPI child process.
4. The update tool backs up application files and the configured database.
5. It replaces program files, installs dependencies, and runs migrations.
6. The launcher starts the new version and checks `/api/health`.
7. On failure, it restores the application and database backup and starts the previous version.

MySQL rollback requires both `mysqldump` and `mysql` client commands. The recommended installer installs them on Debian and Ubuntu.

## Migrating A Legacy Updater Installation

After application files have been upgraded to a Release containing `moegallery_launcher.py`, run the service installer once with the existing application path and service name:

```bash
sudo bash /CURRENT/APP/PATH/scripts/install_systemd.sh \
  --app-dir /CURRENT/APP/PATH \
  --service moegallery \
  --user moegallery \
  --group moegallery \
  --host 127.0.0.1 \
  --port 8111
```

This command stops the old main service, installs the launcher-based unit, changes application ownership to the dedicated account, removes the legacy updater unit and sudoers file, and starts the new service. It does not change `.env`, the database, images, or reverse-proxy configuration.

## Manual Release Installation

For environments that cannot run the network installer:

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

Verify the archive against the Release `SHA256SUMS.txt` before extracting it.

## Troubleshooting

### The Port Is Not Reachable

- Confirm the selected bind address with `systemctl cat moegallery`.
- Confirm the service with `systemctl status moegallery`.
- Check `curl http://127.0.0.1:8111/api/health` on the server.
- For `0.0.0.0`, check host and cloud firewall policy.
- For `127.0.0.1`, check the independently managed reverse proxy.

### The Update Center Only Allows Verification

The application was started directly with Uvicorn instead of `moegallery_launcher.py`, or required update scripts are missing. Re-run `scripts/install_systemd.sh` and inspect the main service logs.

### MySQL Backup Fails

Install MySQL client tools and verify the dedicated application account can connect from the server. The update is not applied when the pre-update backup fails.

### First Install Requests A Restart

Standard launcher installations restart automatically. A direct development Uvicorn process must be restarted manually because it has no parent launcher.
