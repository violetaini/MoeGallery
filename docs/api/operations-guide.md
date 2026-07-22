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

Configure one or more keys in `.env`:

```env
AGMS_API_KEYS=ops-main:agms_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx,backup:agms_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
```

Only the key value after `:` is sent in the `Authorization` header. Keep keys server-side, rotate them if exposed, and do not put them in frontend code. The backend settings page can display the current operations API key and reset it to a new strong default key.

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
- derivative counts for original, preview, and thumbnail files
- FFmpeg / AVIF / JXR capability
- HDR metadata patch capability
- upload worker settings
- auth secret health

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
exclude_avatar_images=true
require_work_related=true
require_character_related=true
```

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

### Queue Batch Upload Tasks

Use `/api/upload-tasks` for larger batches. Processing workers run concurrently according to backend settings.

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
succeeded
failed
duplicate
```

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
- Pass real client IP safely and prevent spoofed `X-Forwarded-For`.
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
- Backend logs for worker exceptions.
- `upload_worker_count` and `upload_claim_batch_size`.
- Database connectivity and lock contention.

### Preview or thumbnail missing

Check:

- `/api/system/health` derivative counts.
- Storage write permissions.
- FFmpeg/Pillow/imagecodecs availability.
- Re-run one real upload sample and inspect generated original, preview, and thumbnail files.

### HDR AVIF metadata incomplete

Check:

- FFmpeg can encode AVIF still images.
- JXR decoding is available for JXR uploads.
- HDR metadata patch support reports healthy in `/api/system/health`.
- Confirm generated HDR AVIF contains `nclx`, `mdcv`, and `clli`.
