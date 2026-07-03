# Anime Gallery Backend

FastAPI backend for Anime Gallery Media Server.

The backend now includes admin authentication. Admin login writes an HttpOnly cookie session backed by the `admin_sessions` table; write endpoints require that session and validate CSRF headers for non-safe methods. Work cover images, work backdrop images, and character avatars are bound from uploaded images rather than pasted IDs. The public home feed excludes images already associated with works or characters.

## Development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The default development database is SQLite at `backend/anime_gallery.db`. Production deployments should use MySQL 8.x with `utf8mb4`.
Example production URL:

```env
AGMS_DATABASE_URL=mysql+pymysql://anime_gallery:change-this-db-password@127.0.0.1:3306/anime_gallery?charset=utf8mb4
```

Create the database before running Alembic:

```sql
CREATE DATABASE anime_gallery CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'anime_gallery'@'127.0.0.1' IDENTIFIED BY 'change-this-db-password';
GRANT ALL PRIVILEGES ON anime_gallery.* TO 'anime_gallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

The default storage path is `../storage`.

First-time deployment exposes `/install` in the frontend and `/api/install/status` plus `/api/install` in the backend. The install flow follows the same basic idea as lsky-pro: a project-root `installed.lock` marks the application as installed. For compatibility with existing deployments, a database that already contains a populated Alembic version table is also treated as installed even if the lock file is missing. The installer writes `.env`, runs Alembic migrations, initializes the administrator account, and then creates `installed.lock`.
The setup page does not ask for a storage path. New deployments use the configured default storage directory, which is `storage` under the project root unless `AGMS_STORAGE_PATH` is deliberately set before startup.
For MySQL/MariaDB installs, the installer prepares `alembic_version.version_num` as `VARCHAR(128)` before running migrations. This avoids MySQL's strict length check against Alembic's default `VARCHAR(32)` when a migration revision id is longer than 32 characters.

## Main APIs

OpenAPI documentation is generated from the FastAPI app. Runtime documentation is protected:

- `GET /api-docs` serves the Scalar API reference UI.
- `GET /api-docs/openapi.json` and `GET /openapi.json` return the OpenAPI document.

Both documentation endpoints require an administrator session or an operations API key. Generate static deployment docs with:

```bash
python scripts_generate_api_docs.py
```

The generated files are written to `../docs/api/openapi.json` and `../docs/api/index.html`. The operations runbook is `../docs/api/operations-guide.md`.

Operations scripts should authenticate with API keys instead of browser login cookies:

```env
AGMS_API_KEYS=ops-main:agms_generated_long_random_key,backup:agms_another_long_random_key
```

Requests send only the key value:

```bash
curl -H "Authorization: Bearer $AGMS_API_KEY" http://127.0.0.1:8000/api/system/health
```

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/install/status`
- `POST /api/install`
- `GET /api/images`
- `GET /api/images/{id}`
- `POST /api/images/upload`
- `PUT /api/images/{id}`
- `DELETE /api/images/{id}`
- `PUT /api/images/batch`
- `DELETE /api/images/batch`
- `GET /api/works`
- `GET /api/characters`
- `GET /api/tags`
- `GET /api/search`
- `GET /api/stats`
- `GET /api/settings`
- `PUT /api/settings`
- `GET /api/system/health`
- `POST /api/settings/auth-secret/rotate`
- `GET /api/imports/metadata/template`
Image listing supports extra filters used by the frontend:

- `work_id`
- `character_id`
- `rating=safe|sensitive|hidden`
- `exclude_work_related` and `exclude_character_related` for the public home feed
- `require_work_related` and `require_character_related` for bound image views
- `exclude_cover_images` and `exclude_avatar_images` for the admin image manager

The admin image manager supports classic table and waterfall image-wall display modes, click-to-edit thumbnails, configurable page sizes, and batch edit/delete actions.
Its main toolbar filters are work, character, and rating.
Batch image edits are limited to works, characters, rating, favorite count, source URL, and artist. Filenames can only be changed one image at a time, and the original extension must be preserved.
Admin settings persist the administrator profile, image manager display mode, and upload queue parameters. The profile supports changing the login username, password, and avatar image. Passwords are stored as PBKDF2-SHA256 hashes in `app_settings`; when no database profile exists yet, the backend falls back to `AGMS_ADMIN_USERNAME` and `AGMS_ADMIN_PASSWORD`.
`upload_worker_count` controls concurrent upload processing workers, and `upload_claim_batch_size` controls how many tasks one worker can claim in one pass; saving settings causes the backend to start any missing workers up to the configured count.
`GET /api/system/health` returns database and storage status, derivative count consistency, current upload queue settings, ffmpeg/AVIF capability, JXR decode capability, and HDR metadata patch availability. Database URLs are password-redacted in this response. The admin settings page renders loading, error, and retry states around this endpoint so deployment diagnostics are visible even when the check fails.
The admin image upload page supports multi-file preview before submission. Every selected file can be previewed, `JXR` previews are generated server-side as temporary WebP responses, and the preview list supports pagination, lightbox viewing, and single-item removal before the final batch upload.
The admin metadata import page can download CSV, JSON, XLSX, and XLSM templates. The same template fields are covered by backend tests that run dry-run and commit imports for every supported format.
Upload policy is now strict in two layers: the filename suffix must be in the supported image whitelist (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.tif`, `.tiff`, `.heif`, `.heic`, `.avif`, `.jxr`), and the decoded content must be parseable by the server. Unsupported suffixes and undecodable files are rejected before they reach storage.
HDR JPEG XR uploads are transcoded to HDR AVIF originals through `ffmpeg` while still generating SDR WebP preview and thumbnail derivatives.
The HDR AVIF path writes `BT.2020 + PQ` `nclx` color information and then patches the container to add `mdcv / clli`, so the output carries complete static HDR metadata even when the local `ffmpeg` CLI does not expose `master_display` and `max_cll` options.
Image responses now include `is_animated`, `dynamic_range`, `bit_depth`, and `color_profile`. The frontend uses those fields to prefer browser-displayable HDR originals on `dynamic-range: high` displays while keeping SDR WebP fallbacks for formats that are not used as direct browser originals.
Existing static originals can be migrated with `python scripts_convert_originals_to_webp.py --apply`; animated and HDR originals are skipped, and the script also backfills the new image metadata fields.
The old public `StaticFiles` mount has been removed. Storage files are now served through `/storage/{path}` with path normalization, database lookup, and permission checks, so hidden/private images cannot be fetched anonymously by guessing file paths.

Deployment recommendation: validate the target `ffmpeg` build before going live. It does not need to expose `master_display` or `max_cll` on the CLI, but it must support AV1 still-picture encoding for AVIF output. Re-run one real HDR upload sample after deployment and confirm the generated original contains `nclx`, `mdcv`, and `clli`.
Basic hardening now also includes login rate limiting, HttpOnly Cookie sessions, CSRF checks, server-side session revocation, auth secret rotation, and security response headers. `POST /api/auth/login` tracks failed attempts by source IP. Defaults are 8 failed attempts per 300-second window; further attempts return `429 Too many login attempts`, and a successful login clears that IP's failure counter. The defaults can be changed with `AGMS_LOGIN_RATE_LIMIT_WINDOW_SECONDS` and `AGMS_LOGIN_RATE_LIMIT_MAX_ATTEMPTS`.
The current limiter stores counters in process memory, which is enough for local or single-process deployments. For multi-process or multi-instance production deployments, move the counter to shared storage such as Redis. If the app is behind a reverse proxy, make sure the proxy passes the real client IP and prevents untrusted clients from spoofing `X-Forwarded-For`.
The `/install` setup flow generates `AGMS_AUTH_SECRET` and a default `AGMS_API_KEYS` entry automatically and writes them to `.env`. `AGMS_AUTH_SECRET` is not an API key; keep both values server-side only. If you maintain `.env` manually, generate strong random values with at least 32 characters. When no persistent auth secret is configured, the backend falls back to a per-process random secret so old fixed defaults cannot be abused, but sessions will be invalid after restart. Use `AGMS_COOKIE_SECURE=true` for HTTPS production deployments.

UI-visible identifiers are presentation-only display numbers generated by the frontend list order. API routes, payloads, and database relationships continue to use immutable database IDs, so deleted rows may leave primary-key gaps without affecting the displayed sequence.

Work records include metadata used by the Jellyfin-style detail page, including backdrop image, tagline, production year, runtime, community rating, content rating, genres, studios, official site, and status.
Image galleries open image details in a frosted-glass overlay on the current page. The standalone `GET /api/images/{id}` backed detail route remains available for direct links and new-tab navigation.
