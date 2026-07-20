#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/moegallery"
OWNER=""
GROUP=""

usage() {
  cat <<'EOF'
Create MoeGallery runtime directories.

Usage:
  bash create_linux_dirs.sh [options]

Options:
  --app-dir DIR    Application directory. Default: /opt/moegallery
  --owner USER     Optional directory owner (root only)
  --group GROUP    Optional directory group (root only)
  -h, --help       Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir)
      APP_DIR="${2:?missing value for --app-dir}"
      shift 2
      ;;
    --owner)
      OWNER="${2:?missing value for --owner}"
      shift 2
      ;;
    --group)
      GROUP="${2:?missing value for --group}"
      shift 2
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

APP_DIR="${APP_DIR%/}"
for directory in \
  storage/original \
  storage/preview \
  storage/thumbnail \
  storage/tasks \
  storage/updates \
  storage/runtime \
  logs \
  backups; do
  mkdir -p "$APP_DIR/$directory"
done

if [[ -n "$OWNER" || -n "$GROUP" ]]; then
  if [[ "$EUID" -ne 0 ]]; then
    echo "--owner and --group require root privileges" >&2
    exit 1
  fi
  OWNER="${OWNER:-$GROUP}"
  GROUP="${GROUP:-$OWNER}"
  chown -R "$OWNER:$GROUP" "$APP_DIR/storage" "$APP_DIR/logs" "$APP_DIR/backups"
fi
