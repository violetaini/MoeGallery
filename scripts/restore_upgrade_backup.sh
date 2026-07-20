#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/moegallery"
BACKUP_DIR=""
PYTHON_BIN="python3"

usage() {
  cat <<'EOF'
Restore a backup created by backup_before_upgrade.sh.

Usage:
  bash restore_upgrade_backup.sh --backup-dir DIR [options]

Options:
  --app-dir DIR        Application directory. Default: /opt/moegallery
  --backup-dir DIR     Upgrade backup directory to restore
  --python-bin PATH    Python executable used to restore the database
  -h, --help           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir)
      APP_DIR="${2:?missing value for --app-dir}"
      shift 2
      ;;
    --backup-dir)
      BACKUP_DIR="${2:?missing value for --backup-dir}"
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN="${2:?missing value for --python-bin}"
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

if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
  echo "Valid --backup-dir is required" >&2
  exit 2
fi

APP_DIR="${APP_DIR%/}"
BACKUP_DIR="${BACKUP_DIR%/}"

if [[ ! -f "$BACKUP_DIR/app-files.tar.gz" ]]; then
  echo "Application backup is missing: $BACKUP_DIR/app-files.tar.gz" >&2
  exit 1
fi

echo "Restoring application files from $BACKUP_DIR"
WORK_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT
tar -xzf "$BACKUP_DIR/app-files.tar.gz" -C "$WORK_DIR"

mkdir -p "$APP_DIR/backend" "$APP_DIR/frontend" "$APP_DIR/scripts"
if [[ -d "$WORK_DIR/backend" ]]; then
  rsync -a --delete \
    --exclude='anime_gallery.db*' \
    --exclude='*.db' \
    --exclude='*.db-*' \
    --exclude='*.sqlite' \
    --exclude='*.sqlite-*' \
    "$WORK_DIR/backend/" "$APP_DIR/backend/"
fi
if [[ -d "$WORK_DIR/frontend" ]]; then
  rsync -a --delete \
    --exclude='dist/.user.ini' \
    "$WORK_DIR/frontend/" "$APP_DIR/frontend/"
fi
if [[ -d "$WORK_DIR/scripts" ]]; then
  rsync -a --delete "$WORK_DIR/scripts/" "$APP_DIR/scripts/"
fi
if [[ -d "$WORK_DIR/docs" ]]; then
  mkdir -p "$APP_DIR/docs"
  rsync -a --delete "$WORK_DIR/docs/" "$APP_DIR/docs/"
else
  rm -rf "$APP_DIR/docs"
fi

for file in install.sh .env.example LICENSE README.md README_zh.md README_zh-TW.md README_ja.md VERSION RELEASE_NOTES.md; do
  if [[ -e "$WORK_DIR/$file" ]]; then
    cp -a "$WORK_DIR/$file" "$APP_DIR/$file"
  fi
done

if [[ -f "$BACKUP_DIR/env/.env" ]]; then
  cp -a "$BACKUP_DIR/env/.env" "$APP_DIR/.env"
fi
if [[ -f "$BACKUP_DIR/install/installed.lock" ]]; then
  cp -a "$BACKUP_DIR/install/installed.lock" "$APP_DIR/installed.lock"
fi
if [[ -f "$BACKUP_DIR/install/VERSION" ]]; then
  cp -a "$BACKUP_DIR/install/VERSION" "$APP_DIR/VERSION"
fi

if [[ -f "$BACKUP_DIR/database-backup.json" ]]; then
  "$PYTHON_BIN" - "$APP_DIR" "$BACKUP_DIR" <<'PY'
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


app_dir = Path(sys.argv[1]).resolve()
backup_dir = Path(sys.argv[2]).resolve()
info = json.loads((backup_dir / "database-backup.json").read_text(encoding="utf-8"))
backup = Path(str(info.get("backup") or ""))
if not backup.is_absolute():
    backup = backup_dir / backup


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


database_type = str(info.get("database_url_type") or "")
if database_type == "sqlite":
    target = Path(str(info.get("path") or ""))
    if backup.exists() and target:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        print(f"Restored SQLite database to {target}")
elif database_type.startswith(("mysql", "mariadb")):
    if not backup.exists():
        raise SystemExit(f"MySQL backup is missing: {backup}")
    database_url = read_env(app_dir / ".env").get("AGMS_DATABASE_URL", "")
    parsed = urlparse(database_url)
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    database = unquote(parsed.path.lstrip("/"))
    mysql = shutil.which("mysql")
    if not mysql:
        raise SystemExit("mysql client not found; cannot restore MySQL backup automatically")
    command = [mysql, "-h", host, "-P", str(port), "-u", username, database]
    environment = os.environ.copy()
    if password:
        environment["MYSQL_PWD"] = password
    with backup.open("rb") as source:
        subprocess.run(command, stdin=source, env=environment, check=True)
    print(f"Restored MySQL database {database}")
PY
fi

if [[ -x "$APP_DIR/venv/bin/pip" && -f "$APP_DIR/backend/requirements.txt" ]]; then
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"
fi

echo "Restore completed"
