# Anime Gallery API Operations Guide

This guide is for deployment and operations users who need to call Anime Gallery Media Server APIs from scripts, monitoring jobs, reverse proxies, or maintenance tools.

## Base URL

Use the backend origin as `BASE_URL`.

```bash
export BASE_URL="https://gallery.example.com"
```

Local preview usually uses:

```bash
export BASE_URL="http://127.0.0.1:8000"
```

## Authentication

Browser administrators use an HttpOnly cookie session and CSRF cookie. Operations scripts should not automate browser login. Use an API key instead:

```bash
export AGMS_API_KEY="paste-key-from-AGMS_API_KEYS"
curl -H "Authorization: Bearer $AGMS_API_KEY" "$BASE_URL/api/auth/me"
```

The installer creates the first key in `.env`:

```env
AGMS_API_KEYS=default:agms_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Only the key value after `:` is sent in the `Authorization` header. Keep keys server-side and do not put them in frontend code. Create, edit, expire, or revoke additional keys from **System settings > Operations API Key**. The panel intentionally shows the complete key to authenticated administrators. Existing keys are granted all scopes once during an upgrade; newly created keys use the scopes selected by the administrator.

## API Key scopes

| Scope | Purpose |
| --- | --- |
| `library:read` | Read private or hidden library records and protected media files. |
| `uploads:manage` | Upload, preview, check duplicates, and inspect upload tasks. |
| `library:write` | Create or update image metadata, works, characters, and ratings. |
| `library:delete` | Permanently delete images, works, characters, and ratings. |
| `system:read` | Read statistics, system health, and API documentation. |
| `settings:manage` | Change backend preferences, administrator profile, password, and login secret. |
| `updates:read` | Check releases and inspect update tasks. |
| `updates:run` | Start validation or formal update tasks. |
| `api_keys:manage` | Create, edit, revoke, or reset API keys. |

Selecting all nine scopes gives the key full system control. Scope requirements are also shown on every protected operation in the web API reference as `x-api-key-scopes`. A key without the required scope receives `403`; an unknown, expired, or revoked key receives `401`.

API key management endpoints require `api_keys:manage`:

```text
GET    /api/settings/api-keys
POST   /api/settings/api-keys
PUT    /api/settings/api-keys/{key_id}
DELETE /api/settings/api-keys/{key_id}
POST   /api/settings/api-keys/reset
```

## Protected Docs

Runtime docs are protected:

```bash
curl -H "Authorization: Bearer $AGMS_API_KEY" "$BASE_URL/api-docs/openapi.json"
```

Open the interactive Scalar page after logging into the backend or through a trusted internal network path:

```text
https://gallery.example.com/api-docs
```

Static docs generated for deployment are in:

```text
docs/api/index.html
docs/api/openapi.json
```

## Common Calls

### Liveness

Use this for reverse proxy or uptime checks. It does not require authentication.

```bash
curl "$BASE_URL/api/health"
```

Expected shape:

```json
{"status":"ok","name":"Anime Gallery Media Server"}
```

### System Health

Use this after deployment and before large uploads.

```bash
curl -H "Authorization: Bearer $AGMS_API_KEY" "$BASE_URL/api/system/health"
```

Check these fields first:

- `database.ok`
- `storage.ok`
- `storage.consistency.expected`: original and thumbnail for every image, plus preview only for HDR images
- `storage.consistency.cleanup_required`: legacy SDR or animated previews that can be reclaimed after a dry run
- FFmpeg / AVIF / JXR capability
- HDR metadata patch capability
- upload worker settings
- auth secret health
- `media_delivery.mode`, shared cache duration, and optional Nginx internal-send status

### List Images

Public list:

```bash
curl "$BASE_URL/api/images?page=1&page_size=24&sort=latest"
```

Admin list including private or hidden images:

```bash
curl -H "Authorization: Bearer $AGMS_API_KEY" \
  "$BASE_URL/api/images?public_only=false&page=1&page_size=50"
```

Useful filters:

```text
work_id=12
character_id=34
character=伊蕾娜|イレイナ|别名
rating=safe|sensitive|hidden
sort=latest|random|favorites|resolution
exclude_cover_images=true
exclude_backdrop_images=true
exclude_avatar_images=true
require_work_related=true
require_character_related=true
```

### Read Image Files

Image metadata includes `media_version`. New clients should build image URLs with the image ID, requested variant, and that version:

```text
/media/{image_id}/{variant}/{media_version}
variant=original|preview|thumbnail
```

Example:

```bash
curl -I "$BASE_URL/media/101/preview/1"
```

If the requested preview or thumbnail does not exist, the server falls back to another usable variant and reports the served variant in `X-AGMS-Media-Variant`. Public files return `ETag` and short cache headers. The default browser lifetime is 60 seconds and the default shared/CDN lifetime is 300 seconds. A matching `If-None-Match` returns `304`.

Changing an image between public/private or changing its rating increments `media_version`; old versioned URLs then return `404` at the origin. Private and `hidden` files require a browser administrator session or an API key with `library:read` and always return `Cache-Control: private, no-store`.

`/storage/{relative_path}` remains available for older clients. New integrations should use `/media` so access changes produce a new cache key. A CDN may cache public `/media/*` responses only when it honors the origin `Cache-Control`; do not override `private` or `no-store` responses.

### Work and Character Details

Detail responses contain metadata and exact relationship counts, but deliberately do not embed every related image or character:

```bash
curl "$BASE_URL/api/works/12"
curl "$BASE_URL/api/characters/34"
```

A work detail includes `character_count` and `image_count`. A character detail includes `image_count`. Fetch the related records through the paginated list endpoints:

```bash
curl "$BASE_URL/api/characters?work_id=12&page=1&page_size=24"
curl "$BASE_URL/api/images?work_id=12&page=1&page_size=24"
curl "$BASE_URL/api/images?character_id=34&page=1&page_size=24"
```

For anonymous callers, image counts and image pages exclude private and `hidden` records. An API key with `library:read` may pass `public_only=false` to include them. This contract avoids loading an entire large library through one detail request.

### Get One Random Image

The public random-image endpoint returns a `307` redirect to one usable image by default:

```bash
curl -L "$BASE_URL/api/images/random" -o random-image.webp
```

With no query parameters, the server detects the device from `Sec-CH-UA-Mobile` or the user agent. The initial defaults are:

```text
PC: landscape
Mobile: portrait
Rating: safe
Variant: preview
```

Administrators can change these four defaults in **System Settings > Random Image API**. Explicit query parameters always override them:

```bash
curl -L \
  "$BASE_URL/api/images/random?work_id=12&character=%E4%BC%8A%E8%95%BE%E5%A8%9C&orientation=portrait&rating=safe&variant=original" \
  -o character-wallpaper.webp
```

The `character` parameter accepts a Chinese name, Japanese original name, or stored alias. With `curl`, `--data-urlencode` is convenient for non-ASCII names:

```bash
curl -G -L "$BASE_URL/api/images/random" \
  --data-urlencode "character=イレイナ" \
  --data-urlencode "orientation=portrait" \
  -o elaina.webp
```

Supported random-image parameters:

```text
work_id=<database ID>
character_id=<database ID>
character=<Chinese name, Japanese name, or alias>
orientation=landscape|portrait|square|any
rating=safe|sensitive|any
device=auto|pc|mobile
variant=original|preview|thumbnail
response=redirect|json
```

Use `response=json` when a client needs metadata instead of an immediate redirect:

```bash
curl "$BASE_URL/api/images/random?device=mobile&response=json"
```

`hidden` and private images are never returned, including when `rating=any`. Device auto-detection distinguishes PC from mobile hardware; it cannot reliably detect the current screen rotation, so landscape phones should pass `orientation=landscape` explicitly. The random endpoint itself is sent with `Cache-Control: no-store` so each request can select a new image.

`variant=preview` returns the HDR SDR-preview where one exists. For normal SDR or animated images, it falls back to the master file because those types intentionally do not keep a duplicate preview derivative. `variant=thumbnail` always requests the lightweight card-sized derivative.

### Upload Images Immediately

Use `/api/images/upload` for smaller batches or synchronous maintenance tools.

```bash
curl -X POST "$BASE_URL/api/images/upload" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -F "files=@/data/a.jpg" \
  -F "files=@/data/b.png" \
  -F "work_ids=12" \
  -F "character_ids=34" \
  -F "rating=safe" \
  -F "is_public=true" \
  -F "merge_duplicate_relations=false"
```

Supported upload suffixes:

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

The server still validates decoded file content. Unsupported suffixes or undecodable content are rejected.

### Duplicate Preflight

If the client can compute SHA-256 values, check duplicates before uploading:

```bash
curl -X POST "$BASE_URL/api/upload-tasks/check-duplicates" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"filename": "a.jpg", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
    ]
  }'
```

If the client cannot compute hashes, send files for server-side duplicate preflight:

```bash
curl -X POST "$BASE_URL/api/upload-tasks/check-duplicates-files" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -F "files=@/data/a.jpg" \
  -F "files=@/data/b.png"
```

Each result distinguishes three cases:

- `duplicate`: the image is already stored in the library.
- `duplicate_in_queue`: the same content is already queued or processing.
- `duplicate_in_batch`: an earlier file in this request has the same content.

Both preflight endpoints query hashes in batches. Preflight is advisory; the image table's SHA-256 uniqueness check remains the final protection against concurrent duplicate writes.

### Queue Batch Upload Tasks

Use `/api/upload-tasks` for larger batches. The server validates every file and relation ID before creating any task, then inserts all tasks in one database transaction. If validation, staging, or task insertion fails, the full batch is rejected and its staged files are removed. Processing workers run concurrently according to backend settings.

```bash
curl -X POST "$BASE_URL/api/upload-tasks" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -F "files=@/data/a.jpg" \
  -F "files=@/data/b.png" \
  -F "work_ids=12" \
  -F "character_ids=34" \
  -F "rating=safe" \
  -F "is_public=true"
```

List recent tasks:

```bash
curl -H "Authorization: Bearer $AGMS_API_KEY" \
  "$BASE_URL/api/upload-tasks?page=1&page_size=50"
```

Inspect one task:

```bash
curl -H "Authorization: Bearer $AGMS_API_KEY" "$BASE_URL/api/upload-tasks/123"
```

Common statuses:

```text
queued
processing
retry_wait
success
failed
canceled
```

A successful task can also return `duplicate=true`; this means it resolved to an existing image instead of creating another file. `preflight_duplicate=true` records that the server had already detected a matching library, queue, or earlier batch item before processing.

`retry_wait` means a recoverable failure is waiting for its next automatic attempt. The default maximum is three total attempts, so the default retry delays are 10 and 30 seconds before the final failure. Administrators can set the total attempt limit from 1 to 10 in **System Settings > Upload queue parameters**.

Retry one failed task while its staged file is still available:

```bash
curl -X POST -H "Authorization: Bearer $AGMS_API_KEY" \
  "$BASE_URL/api/upload-tasks/123/retry"
```

Cancel one queued, processing, or retry-waiting task:

```bash
curl -X POST -H "Authorization: Bearer $AGMS_API_KEY" \
  "$BASE_URL/api/upload-tasks/123/cancel"
```

Processing cancellation is cooperative. If the worker has already committed a complete image, the successful result wins instead of deleting valid data.

Apply one action to multiple task IDs:

```bash
curl -X POST "$BASE_URL/api/upload-tasks/batch/actions" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"ids":[123,124],"action":"retry"}'
```

`action` accepts `retry`, `cancel`, or `delete`. Delete only removes terminal task history and any remaining staged file; it does not delete an image that a successful task already created.

Workers claim tasks with expiring leases and renew them with heartbeats. On startup, the service automatically requeues processing tasks whose leases have expired. A live lease is not disturbed. Failed staged files are retained for manual retry for seven days by default, and terminal task history is retained for 90 days.

### Batch Edit Image Metadata

Batch edits intentionally exclude filenames.

```bash
curl -X PUT "$BASE_URL/api/images/batch" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "image_ids": [101, 102],
    "update": {
      "work_ids": [12],
      "character_ids": [34],
      "rating": "safe",
      "favorite_count": 0,
      "source_url": "https://example.com/source",
      "artist_name": "unknown"
    }
  }'
```

### Batch Delete Images

```bash
curl -X DELETE "$BASE_URL/api/images/batch" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"image_ids":[101,102]}'
```

### Metadata Import

Download a template:

```bash
curl -L -H "Authorization: Bearer $AGMS_API_KEY" \
  "$BASE_URL/api/imports/metadata/template?format=xlsx" \
  -o metadata-template.xlsx
```

Dry-run import first:

```bash
curl -X POST "$BASE_URL/api/imports/metadata?dry_run=true" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -F "file=@metadata-template.xlsx"
```

Commit after review:

```bash
curl -X POST "$BASE_URL/api/imports/metadata?dry_run=false" \
  -H "Authorization: Bearer $AGMS_API_KEY" \
  -F "file=@metadata-template.xlsx"
```

## Error Codes

Common responses:

```text
400  Bad input, invalid image, duplicate conflict, or unsupported file content.
401  Missing/invalid Cookie session or API key.
403  Cookie session write request missing matching X-CSRF-Token.
404  Record not found, or hidden/private record requested without admin authentication.
422  Validation failed: wrong enum, bad field type, missing required field.
429  Login rate limit exceeded.
500  Unexpected server error; inspect backend logs.
```

API-key script requests do not need CSRF. Browser cookie-session write requests do need `X-CSRF-Token`.

## Rate Limits

Login is rate-limited per source IP:

```env
AGMS_LOGIN_RATE_LIMIT_WINDOW_SECONDS=300
AGMS_LOGIN_RATE_LIMIT_MAX_ATTEMPTS=8
```

The current limiter is process-local. For multi-process or multi-instance production, move it to shared storage such as Redis.

## Reverse Proxy Notes

Recommended production checks:

- Force HTTPS and set `AGMS_COOKIE_SECURE=true`.
- Keep `/api-docs` internal or behind administrator/API-key authentication.
- Pass real client IP safely, overwrite spoofed forwarding headers, and restrict `AGMS_TRUSTED_PROXY_CIDRS` to the actual proxy networks.
- Increase upload body limits for large image batches.
- Preserve `Authorization` headers.
- Do not cache protected `/storage/*`, `/api/*`, or `/api-docs/*` responses globally.

## Troubleshooting

### API key returns 401

Check:

- `.env` contains `AGMS_API_KEYS`.
- The request sends only the key value, not the `name:` prefix.
- Reverse proxy forwards the `Authorization` header.
- The app process was restarted after `.env` changes.

### Upload returns 400

Check:

- Suffix is in the whitelist.
- File content is decodable by the server.
- JXR/HDR support is available on the deployment host.
- File size is below `AGMS_MAX_UPLOAD_SIZE`.

### Upload task is stuck

Check:

- `/api/system/health` upload queue section.
- `alive_workers` matches `target_workers`; a short mismatch can occur while worker settings are changing.
- `queued`, `processing`, and `retry_wait` counts are moving rather than growing continuously.
- Backend logs and each task's `error_code` / `error_message` for worker exceptions.
- `upload_worker_count`, `upload_claim_batch_size`, `max_attempts`, and `failed_retention_days`.
- Database connectivity and lock contention.

Restarting the application is safe for queued tasks. Processing tasks are recovered only after their lease expires, which prevents a slow old worker and a replacement worker from finalizing the same task at the same time.

### Required derivative missing or legacy previews pending cleanup

Check:

- `/api/system/health` `storage.consistency.expected`, `missing_hdr_preview_references`, and `cleanup_required` fields.
- Storage write permissions.
- FFmpeg/Pillow/imagecodecs availability.
- Re-run one real upload sample and inspect its expected files: all images require original and thumbnail; HDR images additionally require an SDR preview.

After upgrading from an older release, reclaim redundant SDR and animated preview files in two steps from `backend/`:

```bash
python scripts_prune_redundant_previews.py
python scripts_prune_redundant_previews.py --apply
```

The first command is a dry run. Back up the database and storage before the `--apply` command. The cleanup re-inspects each master file and retains HDR previews.

### HDR AVIF metadata incomplete

Check:

- FFmpeg can encode AVIF still images.
- JXR decoding is available for JXR uploads.
- HDR metadata patch support reports healthy in `/api/system/health`.
- Confirm generated HDR AVIF contains `nclx`, `mdcv`, and `clli`.
