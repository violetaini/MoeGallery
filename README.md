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

MoeGallery is a self-hosted media library for organizing and showcasing anime images. It includes a public gallery and an admin panel for managing images, titles, characters, content ratings, and related metadata, with batch import, image processing, and API access built in.

## Quick Start

The installer supports systemd-based Linux distributions and downloads a prebuilt release package. Node.js is not required on the deployment server.

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
sudo bash install.sh
```

On its first run, the installer asks which address the service should listen on:

- `127.0.0.1`: accepts connections from the server itself only. This is the recommended option when using Nginx, aaPanel, or another reverse proxy.
- `0.0.0.0`: listens on every network interface, allowing access through the server's LAN or public IP address.

The default port is `8111`. When installation finishes, the script prints the first-time setup URL. With the default listen address, open the following URL on the server itself:

```text
http://127.0.0.1:8111/install
```

To open the setup page from another computer, configure a reverse proxy or an SSH tunnel first. If you selected `0.0.0.0`, you can instead open `http://SERVER_IP:8111/install` directly.

The setup wizard lets you choose a database and create the admin account. It also generates a session-signing secret and an initial API key, runs database migrations, initializes the storage directories, and records that installation is complete.

| Database | Setup |
| --- | --- |
| SQLite | Select SQLite and continue. The database file is stored in the default application directory; no path is required. |
| MySQL / MariaDB | Create an empty database and a dedicated application account, then enter the connection details in the setup wizard. |

To install non-interactively and listen on every network interface:

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

The installer deploys MoeGallery itself; it does not configure domains, TLS certificates, firewalls, CDNs, or reverse proxies. See the [deployment guide](docs/deployment.md) for listen addresses, service management, MySQL preparation, manual installation, and migration from older versions.

## What Gets Installed

- Application files under `/opt/moegallery` by default.
- A single systemd service named `moegallery.service`.
- A dedicated `moegallery` service account with no login shell or root privileges. It runs the application and owns the MoeGallery application directory; it is unrelated to the web admin account. Use `--user` to run the service under an existing system account instead.
- A built-in launcher that starts FastAPI and coordinates updates, health checks, and rollback.
- The prebuilt frontend, served by FastAPI on the same port as the API.

Updates are handled by the main service, so no separate updater service or passwordless sudo rule is installed.

## Features

- A fullscreen slideshow home page whose images can be selected from the admin panel; when none are selected, images are chosen randomly from the library.
- A masonry gallery with search, sorting, and filters for titles, characters, and content ratings.
- Automatic loading at the end of the page, with upcoming images prefetched in advance.
- An in-page image detail overlay, while retaining a direct URL for every image.
- Media-library-style title and character pages with backdrops, posters, avatars, and pagination.
- Three fixed content ratings: `safe`, `sensitive`, and `hidden`.
- A public random-image API can filter by work, character ID, Chinese/Japanese character names and aliases, rating, and orientation, with configurable desktop and mobile defaults.
- Classic table and masonry views in the admin panel, both with batch operations.
- Batch uploads with file previews, duplicate detection, processing queues, retries, and metadata assignment.
- CSV, JSON, XLSX, and XLSM templates for bulk metadata imports.
- SQLite or MySQL/MariaDB selection during first-time setup.
- HttpOnly admin sessions, CSRF validation, login rate limiting, API keys, and a cryptographically strong session secret generated during setup.
- Checks for new GitHub releases, verified updates, database backups, migrations, health checks, and automatic rollback from the admin panel.

## Image Processing

| Upload type | Stored format | Browser delivery |
| --- | --- | --- |
| Standard static image | Converted to WebP | WebP preview and thumbnail |
| GIF or other animated image | Original animation format retained | Static WebP preview and thumbnail |
| JXR or HDR image | Converted to HDR AVIF with `nclx / mdcv / clli` metadata | SDR WebP preview and thumbnail on standard pages |
| Other high-bit-depth image | HDR source retained when its format is supported | SDR WebP preview and thumbnail on standard pages |

Supported file extensions include:

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

Uploads are not accepted based on the file extension alone. The server also attempts to decode each image and rejects disguised or unsupported files.

## Updates and Backups

After installation, upgrades can be started from **Admin > Update Center**. The site remains available while the release package is downloaded and verified. The web service stops briefly only while files are replaced and database migrations run. After starting the new version, MoeGallery checks `/api/health`; if that check fails, it restores the previous application and database before restarting the old version.

Manual backup:

```bash
sudo -u moegallery bash /opt/moegallery/scripts/backup_before_upgrade.sh \
  --app-dir /opt/moegallery
```

SQLite backups use the SQLite Backup API to create a consistent snapshot. MySQL/MariaDB backups use `mysqldump --single-transaction --no-tablespaces`, so MySQL client tools must be installed on the server.

## Documentation

- [Deployment](docs/deployment.md)
- [Deployment guide (Simplified Chinese)](docs/deployment_zh.md)
- [API operations guide](docs/api/operations-guide.md)
- Interactive API documentation: `/api-docs` after signing in as an administrator
- OpenAPI document: `docs/api/openapi.json`

## Development

Local development requires Python 3.11 or later and Node.js 20 or later.

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

The frontend development server runs at `http://127.0.0.1:5173` and proxies API and storage requests to the backend on local port `8000`.

## Main Routes

```text
/                Home slideshow
/gallery         Image gallery
/works           Works
/characters      Characters
/tags            Ratings
/admin            Administration panel
/install          First-time setup wizard
/api-docs         Admin API documentation
```

## Security

- Keep `.env`, `installed.lock`, databases, uploaded files, backups, and private keys out of Git.
- Configure HTTPS before exposing the admin login over a public or otherwise untrusted network.
- Create a dedicated MySQL account for MoeGallery; do not use the MySQL root account or another database administrator account.
- Keep release package checksum verification enabled. If a GitHub proxy is required, use only one you trust.
- Report security issues privately instead of publishing credentials or exploit details.

## License

MoeGallery is released under the [MIT License](LICENSE).
