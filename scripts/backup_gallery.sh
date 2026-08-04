#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/moegallery"
BACKUP_ROOT=""
ENV_FILE=""
KEEP_DAYS=14
SKIP_DATABASE=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Create a restorable MoeGallery backup with image files and bounded retention.

Usage: backup_gallery.sh [options]

Options:
  --app-dir DIR        Application directory. Default: /opt/moegallery
  --backup-root DIR    Backup root. Default: <app-dir>/backups
  --env-file FILE      Environment file. Default: <app-dir>/.env
  --keep-days DAYS     Retain scheduled backups for this many days. Default: 14
  --skip-database      Back up images and application files only
  --dry-run            Print the planned backup and cleanup actions
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
    --env-file)
      ENV_FILE="${2:?missing value for --env-file}"
      shift 2
      ;;
    --keep-days)
      KEEP_DAYS="${2:?missing value for --keep-days}"
      shift 2
      ;;
    --skip-database)
      SKIP_DATABASE=1
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
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

normalize_path() {
  local value="$1"
  case "$value" in
    [A-Za-z]:/*|[A-Za-z]:\\*)
      if command -v cygpath >/dev/null 2>&1; then
        cygpath -u "$value"
        return
      fi
      ;;
  esac
  printf '%s\n' "$value"
}

if [[ ! "$KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || (( KEEP_DAYS > 3650 )); then
  echo "--keep-days must be an integer from 1 to 3650" >&2
  exit 2
fi

APP_DIR="${APP_DIR%/}"
BACKUP_ROOT="${BACKUP_ROOT:-$APP_DIR/backups}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
APP_DIR="$(normalize_path "$APP_DIR")"
BACKUP_ROOT="$(normalize_path "$BACKUP_ROOT")"
ENV_FILE="$(normalize_path "$ENV_FILE")"
SCHEDULED_ROOT="$BACKUP_ROOT/scheduled"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Application directory does not exist: $APP_DIR" >&2
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] create a scheduled backup in $SCHEDULED_ROOT"
  echo "[dry-run] include database and durable image directories"
  echo "[dry-run] remove only scheduled upgrade backups older than $KEEP_DAYS days"
  exit 0
fi

SCRIPT_PATH="${BASH_SOURCE[0]//\\//}"
SCRIPT_DIR="$(cd "${SCRIPT_PATH%/*}" && pwd)"
mkdir -p "$SCHEDULED_ROOT"
chmod 700 "$SCHEDULED_ROOT" || true
SCHEDULED_ROOT_REAL="$(cd "$SCHEDULED_ROOT" && pwd -P)"
if [[ -z "$SCHEDULED_ROOT_REAL" || "$SCHEDULED_ROOT_REAL" == "/" ]]; then
  echo "Refusing to prune an unsafe backup directory" >&2
  exit 1
fi

backup_args=(
  --app-dir "$APP_DIR"
  --backup-root "$SCHEDULED_ROOT"
  --env-file "$ENV_FILE"
  --include-storage
)
if [[ "$SKIP_DATABASE" -eq 1 ]]; then
  backup_args+=(--skip-database)
fi

BACKUP_OUTPUT="$(bash "$SCRIPT_DIR/backup_before_upgrade.sh" "${backup_args[@]}")"
printf '%s\n' "$BACKUP_OUTPUT"

while IFS= read -r -d '' candidate; do
  candidate_real="$(cd "$candidate" && pwd -P)"
  if [[ "$candidate_real" != "$SCHEDULED_ROOT_REAL"/upgrade-* ]]; then
    continue
  fi
  rm -rf -- "$candidate_real"
  echo "Removed expired scheduled backup: $candidate_real"
done < <(find "$SCHEDULED_ROOT_REAL" -mindepth 1 -maxdepth 1 -type d -name 'upgrade-*' -mtime "+$KEEP_DAYS" -print0)
