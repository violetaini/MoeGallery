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
  <a href="https://anime.chitanda.net/">Live Site</a> |
  <a href="https://anime.chitanda.net/api-docs">API Docs</a> |
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

## About

MoeGallery is a self-hosted anime image media library for organizing illustrations, screenshots, characters, works, ratings, and image metadata. It provides a public gallery experience for browsing and a private admin panel for uploading, binding, editing, importing, and maintaining the media library.

The project is designed as a Jellyfin-like media library for images: the frontend focuses on gallery browsing, work pages, character pages, ratings, slideshow visuals, and detail overlays; the backend handles uploads, metadata, storage, duplicate checks, image conversion, background jobs, authentication, and API documentation.

## Features

- Fullscreen visual home page with configurable slideshow images.
- Public image gallery with waterfall layout, search, filters by work/character/rating, and sorting by latest, random, favorites, or resolution.
- Image detail overlay on top of the gallery, with direct detail routes still available.
- Work and character pages with media-library style backdrops, posters, avatars, paginated sections, and admin editing pages.
- Fixed rating system: `safe`, `sensitive`, and `hidden`.
- Admin image management with classic table mode and gallery waterfall mode.
- Batch upload with previews, pagination, duplicate pre-checks, queue processing, status polling, and per-file removal before upload.
- Batch metadata import from CSV, JSON, XLSX, and XLSM templates.
- Admin preferences for profile, avatar, password, image-management display mode, upload worker parameters, and home/list background images.
- System health panel for database, storage consistency, upload queue, ffmpeg, JXR decoding, AVIF encoding, and HDR metadata patching.
- Admin security with HttpOnly cookie sessions, CSRF validation, login brute-force protection, operations API keys, install lock, and strong `AGMS_AUTH_SECRET` handling.

## Media Pipeline

| Source | Storage strategy | Preview strategy |
| --- | --- | --- |
| Normal static images | Convert original to WebP | Generate WebP preview and thumbnail |
| GIF / animated images | Preserve original format | Generate static WebP preview and thumbnail |
| JXR / HDR images | Convert JXR to HDR AVIF with `nclx / mdcv / clli` | Generate SDR WebP preview and thumbnail |
| Non-8-bit images | Preserve HDR / high-bit-depth original | Generate SDR WebP preview and thumbnail |

Supported upload suffixes include:

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

The backend validates both filename suffixes and actual decoder support. Files outside the whitelist, files that cannot be decoded, and disguised non-image uploads are rejected.

## Routes

```text
/                         Home slideshow
/gallery                  Image gallery
/images/:id               Image detail
/works                    Work list
/works/:id                Work detail
/characters               Character list
/characters/:id           Character detail
/tags                     Rating page
/search                   Search page
/admin                    Admin panel
/install                  First-install wizard
/api-docs                 Admin API documentation
```

## Tech Stack

| Layer | Stack |
| --- | --- |
| Frontend | Vue 3, Vite, Pinia, Vue Router, Element Plus |
| Backend | FastAPI, SQLAlchemy, Alembic, Pydantic |
| Database | SQLite for local development, MySQL/MariaDB for production |
| Image processing | Pillow, pillow-heif, imagecodecs, ffmpeg |
| Deployment | systemd, Nginx, BaoTa/Linux bare metal |

## Requirements

- Python 3.12 or newer
- Node.js 20 or newer
- MySQL 8.x / MariaDB 11.x for production, or SQLite for local development
- ffmpeg with AVIF/AV1 encoding support

## Development

Backend:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The Vite development server runs on `http://127.0.0.1:5173/` by default.

## Configuration

Copy `.env.example` to `.env` and adjust the deployment values.

```text
AGMS_DATABASE_URL                  SQLite or MySQL SQLAlchemy URL
AGMS_STORAGE_PATH                  Storage root for originals, previews, thumbnails, and task files
AGMS_ADMIN_USERNAME                Initial fallback admin username
AGMS_ADMIN_PASSWORD                Initial fallback admin password
AGMS_AUTH_SECRET                   Strong session signing secret, generated by installer
AGMS_AUTH_TOKEN_TTL_SECONDS        Admin session lifetime
AGMS_COOKIE_SECURE                 Set true behind HTTPS
AGMS_MAX_UPLOAD_SIZE               Maximum upload size in bytes
AGMS_PREVIEW_MAX_SIZE              Preview longest side
AGMS_THUMBNAIL_MAX_SIZE            Thumbnail longest side
AGMS_CORS_ORIGINS                  Allowed browser origins
```

`AGMS_AUTH_SECRET` is not an API key. It signs and verifies backend admin sessions and must stay private. The installer generates it automatically. If you bypass the installer, generate a strong value manually:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## First Install

When `installed.lock` is missing and the target database has no valid Alembic version, the frontend enters `/install`.

The installer can initialize either SQLite or MySQL:

- SQLite: the database path is chosen by the application.
- MySQL: enter host, port, database name, username, and password.
- Storage: uses the project `storage/` directory.
- Admin: set the first administrator username and password.
- Secret: generated automatically and written to `.env`.

After a successful install, the app writes `.env`, runs migrations, initializes the admin account, creates `installed.lock`, and asks for a backend restart if required.

## Deployment

Create directories and install backend dependencies:

```bash
sudo mkdir -p /opt/anime-gallery
sudo rsync -a ./ /opt/anime-gallery/
sudo bash /opt/anime-gallery/scripts/create_linux_dirs.sh

cd /opt/anime-gallery
sudo python3 -m venv venv
sudo /opt/anime-gallery/venv/bin/pip install -r backend/requirements.txt
sudo cp .env.example .env
```

For MySQL production deployments:

```sql
CREATE DATABASE anime_gallery
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'anime_gallery'@'127.0.0.1' IDENTIFIED BY 'change-this-db-password';
GRANT ALL PRIVILEGES ON anime_gallery.* TO 'anime_gallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

Set `AGMS_DATABASE_URL`:

```env
AGMS_DATABASE_URL=mysql+pymysql://anime_gallery:change-this-db-password@127.0.0.1:3306/anime_gallery?charset=utf8mb4
```

Run migrations and build the frontend:

```bash
cd /opt/anime-gallery/backend
sudo -u www-data /opt/anime-gallery/venv/bin/alembic upgrade head

cd /opt/anime-gallery/frontend
npm install
npm run build
```

Install systemd and Nginx examples:

```bash
sudo cp /opt/anime-gallery/scripts/anime-gallery.service /etc/systemd/system/anime-gallery.service
sudo systemctl daemon-reload
sudo systemctl enable --now anime-gallery

sudo cp /opt/anime-gallery/scripts/nginx-anime-gallery.conf /etc/nginx/sites-available/anime-gallery.conf
sudo ln -s /etc/nginx/sites-available/anime-gallery.conf /etc/nginx/sites-enabled/anime-gallery.conf
sudo nginx -t
sudo systemctl reload nginx
```

Change `gallery.example.com` in the Nginx example to your own domain and enable HTTPS in production.

## Real Client IP Behind ESA/CDN

If the site is behind Alibaba Cloud ESA/CDN, pass the real client IP from the edge to the backend. The example Nginx config prefers `ali-real-client-ip`, also accepts `ali-cdn-real-ip` and `true-client-ip`, then falls back to `$remote_addr`.

The backend also understands those headers and only trusts forwarded headers from loopback/private reverse proxies. For production, restrict direct origin access with security groups/firewall rules or origin authentication headers so external clients cannot spoof real-IP headers.

## API

The OpenAPI documentation is available at:

```text
/api-docs
/api-docs/openapi.json
/openapi.json
```

API documentation is protected by admin authentication. Operations can use either the admin session cookie or a configured operations API key.

## Security Notes

- Admin writes require a valid HttpOnly session cookie.
- Unsafe requests with a session cookie must include the CSRF token header.
- Login failures are rate-limited by both client IP and username.
- API keys are for operations automation only and must not be exposed to browsers.
- `/storage/*` is served through the backend so private/hidden files cannot be fetched directly by path.
- If the backend runs multiple workers or multiple instances, move login rate-limit counters to Redis or another shared store.
- Keep `.env`, database dumps, uploaded media, and private keys out of the public repository.

## License

This project is open source under the [MIT License](LICENSE).

The source code is licensed under MIT. Uploaded images, character artwork, imported metadata, and user-provided media are not automatically covered by this repository license.
