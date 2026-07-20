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
  <a href="https://anime.chitanda.net/">Live Site</a> |
  <a href="https://anime.chitanda.net/api-docs">API Docs</a> |
  <a href="https://github.com/violetaini/MoeGallery/releases">Releases</a>
</p>

MoeGallery is a self-hosted anime image media library. It combines a public gallery with an administration panel for uploads, works, characters, ratings, metadata, image processing, and API access.

## Quick Start

The recommended installer supports Linux with systemd and installs a prebuilt Release. Node.js is not required for deployment.

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
sudo bash install.sh
```

The installer asks for only the listen mode:

- `127.0.0.1`: local access or your own reverse proxy, recommended.
- `0.0.0.0`: direct public or LAN access.

The default port is `8111`. When the service is ready, open:

```text
http://SERVER_IP:8111/install
```

The web installer then handles the database, administrator account, migrations, session secret, API Key, storage directories, and install lock.

| Database | Setup |
| --- | --- |
| SQLite | Select SQLite and continue. MoeGallery chooses the file location. |
| MySQL / MariaDB | Create an empty database and dedicated account first, then enter the connection details. |

For an unattended public bind:

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

MoeGallery does not create domains, TLS certificates, firewall rules, or reverse-proxy sites. See the [deployment guide](docs/deployment.md) for bind modes, service commands, MySQL preparation, manual installation, and migration from older installations.

## What Gets Installed

- Application files in `/opt/moegallery` by default.
- One `moegallery.service` systemd unit.
- A dedicated non-root `moegallery` account.
- A built-in launcher that starts FastAPI and coordinates panel updates.
- The prebuilt frontend, served directly by FastAPI on the same port.

There is no separate updater service and no updater sudoers rule.

## Features

- Fullscreen visual home page with configurable slideshow images.
- Waterfall gallery with search, work, character and rating filters, sorting, automatic loading, and prefetching.
- Image detail overlay plus direct detail routes.
- Media-library style work and character pages with backdrops, posters, avatars, and pagination.
- Fixed `safe`, `sensitive`, and `hidden` ratings.
- Classic and waterfall administration modes with batch operations.
- Batch upload with previews, duplicate pre-checks, processing queues, retry, and metadata binding.
- CSV, JSON, XLSX, and XLSM metadata import templates.
- SQLite and MySQL/MariaDB deployment choices.
- HttpOnly administrator sessions, CSRF validation, login rate limiting, API Keys, and strong generated secrets.
- In-panel Release checks, verified updates, database backups, migrations, health checks, and automatic rollback.

## Image Pipeline

| Source | Original storage | Browser preview |
| --- | --- | --- |
| Normal static image | Convert to WebP | WebP preview and thumbnail |
| GIF or animated image | Preserve animation | Static WebP preview and thumbnail |
| JXR / HDR image | HDR AVIF with `nclx / mdcv / clli` | SDR WebP preview and thumbnail |
| Other high-bit-depth image | Preserve compatible HDR source | SDR WebP preview and thumbnail |

Accepted upload suffixes include:

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

The backend validates both the suffix and actual decoder support. Disguised or undecodable files are rejected.

## Updates And Backups

Installed instances update from **Admin > Update Center**. The built-in launcher downloads and verifies the Release while the site stays online, briefly stops the web child process for installation and migration, then performs a health check. A failed health check restores the pre-update application and database backup.

Manual backup:

```bash
sudo -u moegallery bash /opt/moegallery/scripts/backup_before_upgrade.sh \
  --app-dir /opt/moegallery
```

SQLite uses the SQLite backup API. MySQL/MariaDB uses `mysqldump --single-transaction` and therefore requires MySQL client tools.

## Documentation

- [Deployment](docs/deployment.md)
- [部署说明（简体中文）](docs/deployment_zh.md)
- [API operations guide](docs/api/operations-guide.md)
- Interactive API documentation: `/api-docs` after administrator login
- OpenAPI document: `docs/api/openapi.json`

## Development

Development requires Python 3.11 or newer and Node.js 20 or newer.

```bash
# Backend
python -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend, in another terminal
cd frontend
npm ci
npm run dev
```

The frontend development server runs on `http://127.0.0.1:5173` and proxies API and storage requests to port `8000`.

## Main Routes

```text
/                Home slideshow
/gallery         Image gallery
/works           Works
/characters      Characters
/tags            Ratings
/admin            Administration panel
/install          First-install wizard
/api-docs         Administrator API documentation
```

## Security

- Keep `.env`, `installed.lock`, databases, uploaded files, backups, and private keys out of Git.
- Use HTTPS before exposing administrator login over an untrusted network.
- Use a dedicated MySQL account instead of a database administrator account.
- Keep Release checksum verification enabled and configure a trusted GitHub proxy only when needed.
- Report security issues privately instead of publishing credentials or exploit details.

## License

MoeGallery is released under the [MIT License](LICENSE).
