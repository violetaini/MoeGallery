#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/moegallery"
BACKUP_ROOT=""
SERVICE_NAME="moegallery"
HEALTH_URL="http://127.0.0.1:8111/api/health"
ARCHIVE=""
RESULT_FILE=""
SKIP_BACKUP=0
SKIP_MIGRATE=0
DRY_RUN=0
NO_SERVICE_CONTROL=0
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage: upgrade_release.sh [options] <MoeGallery-vX.Y.Z.tar.gz|MoeGallery-vX.Y.Z.zip>

Options:
  --app-dir DIR        Application directory. Default: /opt/moegallery
  --backup-root DIR    Backup root. Default: <app-dir>/backups
  --service NAME       systemd service name. Default: moegallery
  --health-url URL     Health check URL. Default: http://127.0.0.1:8111/api/health
  --result-file FILE   Write the created backup path as JSON for the launcher
  --no-service-control Do not call systemctl or perform the final health check
  --skip-backup        Do not create a backup before upgrade
  --skip-migrate       Do not run Alembic migrations
  --dry-run            Print actions without changing application files
  -h, --help           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir)
      APP_DIR="${2:?missing value for --app-dir}"
      shift 2
      ;;
    --backup-root)
      BACKUP_ROOT="${2:?missing value for --backup-root}"
      shift 2
      ;;
    --service)
      SERVICE_NAME="${2:?missing value for --service}"
      shift 2
      ;;
    --health-url)
      HEALTH_URL="${2:?missing value for --health-url}"
      shift 2
      ;;
    --result-file)
      RESULT_FILE="${2:?missing value for --result-file}"
      shift 2
      ;;
    --no-service-control)
      NO_SERVICE_CONTROL=1
      shift
      ;;
    --skip-backup)
      SKIP_BACKUP=1
      shift
      ;;
    --skip-migrate)
      SKIP_MIGRATE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$ARCHIVE" ]]; then
        echo "Only one archive path is allowed" >&2
        exit 2
      fi
      ARCHIVE="$1"
      shift
      ;;
  esac
done

if [[ -z "$ARCHIVE" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Archive not found: $ARCHIVE" >&2
  exit 1
fi

APP_DIR="${APP_DIR%/}"
BACKUP_ROOT="${BACKUP_ROOT:-$APP_DIR/backups}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

service_exists() {
  command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "${SERVICE_NAME}.service" >/dev/null 2>&1
}

echo "Extracting $ARCHIVE"
case "$ARCHIVE" in
  *.tar.gz|*.tgz)
    tar -xzf "$ARCHIVE" -C "$WORK_DIR"
    ;;
  *.zip)
    if ! command -v unzip >/dev/null 2>&1; then
      echo "unzip not found; install unzip or use the .tar.gz archive" >&2
      exit 1
    fi
    unzip -q "$ARCHIVE" -d "$WORK_DIR"
    ;;
  *)
    echo "Unsupported archive format: $ARCHIVE" >&2
    exit 1
    ;;
esac

STAGE_DIR="$(find "$WORK_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$STAGE_DIR" || ! -d "$STAGE_DIR/backend" || ! -d "$STAGE_DIR/frontend/dist" ]]; then
  echo "Archive does not look like a MoeGallery release package" >&2
  exit 1
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  echo "Validating release package"
  "$PYTHON_BIN" -m compileall -q "$STAGE_DIR/backend/app" "$STAGE_DIR/backend/alembic" "$STAGE_DIR/scripts"
  "$PYTHON_BIN" "$STAGE_DIR/scripts/moegallery_launcher.py" --help >/dev/null
  "$PYTHON_BIN" "$STAGE_DIR/scripts/update_runner.py" --help >/dev/null
  bash -n "$STAGE_DIR/install.sh" "$STAGE_DIR"/scripts/*.sh
else
  echo "[dry-run] validate Python and shell entry points"
fi

CREATED_BACKUP_DIR=""
if [[ "$SKIP_BACKUP" -eq 0 ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $SCRIPT_DIR/backup_before_upgrade.sh --app-dir $APP_DIR --backup-root $BACKUP_ROOT"
  else
    BACKUP_OUTPUT="$(bash "$SCRIPT_DIR/backup_before_upgrade.sh" --app-dir "$APP_DIR" --backup-root "$BACKUP_ROOT")"
    printf '%s\n' "$BACKUP_OUTPUT"
    CREATED_BACKUP_DIR="$(printf '%s\n' "$BACKUP_OUTPUT" | tail -n 1)"
  fi
else
  echo "Backup skipped by request"
fi

if [[ -n "$RESULT_FILE" && "$DRY_RUN" -eq 0 ]]; then
  mkdir -p "$(dirname "$RESULT_FILE")"
  "$PYTHON_BIN" - "$RESULT_FILE" "$CREATED_BACKUP_DIR" <<'PY'
import json
import sys
from pathlib import Path

result_path = Path(sys.argv[1])
result_path.write_text(json.dumps({"backup_dir": sys.argv[2]}, ensure_ascii=False) + "\n", encoding="utf-8")
PY
fi

if [[ "$NO_SERVICE_CONTROL" -eq 0 ]] && service_exists; then
  run systemctl stop "$SERVICE_NAME"
elif [[ "$NO_SERVICE_CONTROL" -eq 0 ]]; then
  echo "systemd service ${SERVICE_NAME}.service not found; continuing without stop/start"
fi

run mkdir -p "$APP_DIR/backend" "$APP_DIR/frontend" "$APP_DIR/scripts" "$APP_DIR/storage" "$APP_DIR/logs"

run rsync -a --delete \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='anime_gallery.db*' \
  --exclude='*.db' \
  --exclude='*.db-*' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite-*' \
  "$STAGE_DIR/backend/" "$APP_DIR/backend/"

run rsync -a --delete "$STAGE_DIR/frontend/dist/" "$APP_DIR/frontend/dist/"
run rsync -a --delete "$STAGE_DIR/scripts/" "$APP_DIR/scripts/"

if [[ -d "$STAGE_DIR/docs" ]]; then
  run rsync -a --delete "$STAGE_DIR/docs/" "$APP_DIR/docs/"
fi

for file in install.sh .env.example LICENSE README.md README_zh.md README_zh-TW.md README_ja.md VERSION RELEASE_NOTES.md; do
  if [[ -e "$STAGE_DIR/$file" ]]; then
    run cp -a "$STAGE_DIR/$file" "$APP_DIR/$file"
  fi
done

if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
  run "$PYTHON_BIN" -m venv "$APP_DIR/venv"
fi
run "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

if [[ -f "$APP_DIR/scripts/create_linux_dirs.sh" ]]; then
  run bash "$APP_DIR/scripts/create_linux_dirs.sh" --app-dir "$APP_DIR"
fi

if [[ "$SKIP_MIGRATE" -eq 0 ]]; then
  run bash -c "cd '$APP_DIR/backend' && '$APP_DIR/venv/bin/alembic' upgrade head"
else
  echo "Alembic migration skipped by request"
fi

if [[ "$NO_SERVICE_CONTROL" -eq 0 ]] && service_exists; then
  run systemctl start "$SERVICE_NAME"
fi

if [[ "$DRY_RUN" -eq 0 && "$NO_SERVICE_CONTROL" -eq 0 ]]; then
  if command -v curl >/dev/null 2>&1; then
    sleep 2
    curl -fsS "$HEALTH_URL" >/dev/null
    echo "Health check passed: $HEALTH_URL"
  else
    echo "curl not found; skipped health check"
  fi
fi

echo "Upgrade completed"
