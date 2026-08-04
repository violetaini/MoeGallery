#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/moegallery"
BACKUP_DIR=""
PYTHON_BIN="python3"
PIP_BOOTSTRAP_VERSION="26.2"

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

sync_tree_without_rsync() {
  local source_dir="$1"
  local target_dir="$2"
  shift 2
  "$PYTHON_BIN" - "$source_dir" "$target_dir" "$@" <<'PY'
import fnmatch
import os
import shutil
import sys
from pathlib import Path


source = Path(sys.argv[1])
target = Path(sys.argv[2])
patterns = [item.replace("\\", "/").rstrip("/") for item in sys.argv[3:] if item]


def excluded(relative: Path) -> bool:
    normalized = relative.as_posix()
    for pattern in patterns:
        if normalized == pattern or normalized.startswith(f"{pattern}/"):
            return True
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(relative.name, pattern):
            return True
    return False


target.mkdir(parents=True, exist_ok=True)
for root, directories, files in os.walk(source):
    root_path = Path(root)
    relative_root = root_path.relative_to(source)
    directories[:] = [name for name in directories if not excluded(relative_root / name)]
    destination_root = target / relative_root
    destination_root.mkdir(parents=True, exist_ok=True)
    for filename in files:
        relative = relative_root / filename
        if excluded(relative):
            continue
        source_file = source / relative
        destination_file = target / relative
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        if destination_file.is_dir():
            shutil.rmtree(destination_file)
        shutil.copy2(source_file, destination_file)

for root, directories, files in os.walk(target, topdown=False):
    root_path = Path(root)
    relative_root = root_path.relative_to(target)
    for filename in files:
        relative = relative_root / filename
        if not excluded(relative) and not (source / relative).exists():
            (target / relative).unlink()
    for directory in directories:
        relative = relative_root / directory
        destination_directory = target / relative
        if excluded(relative) or (source / relative).exists():
            continue
        try:
            destination_directory.rmdir()
        except OSError:
            pass
PY
}

if [[ -z "$BACKUP_DIR" ]]; then
  echo "Valid --backup-dir is required" >&2
  exit 2
fi

APP_DIR="${APP_DIR%/}"
BACKUP_DIR="${BACKUP_DIR%/}"
APP_DIR="$(normalize_path "$APP_DIR")"
BACKUP_DIR="$(normalize_path "$BACKUP_DIR")"
PYTHON_BIN="$(normalize_path "$PYTHON_BIN")"

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "Valid --backup-dir is required" >&2
  exit 2
fi

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
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude='__pycache__/' \
      --exclude='*.pyc' \
      --exclude='*.pyo' \
      --exclude='anime_gallery.db*' \
      --exclude='*.db' \
      --exclude='*.db-*' \
      --exclude='*.sqlite' \
      --exclude='*.sqlite-*' \
      --exclude='*.sqlite3' \
      --exclude='*.sqlite3-*' \
      "$WORK_DIR/backend/" "$APP_DIR/backend/"
  else
    sync_tree_without_rsync "$WORK_DIR/backend" "$APP_DIR/backend" \
      '__pycache__/' '*.pyc' '*.pyo' 'anime_gallery.db*' '*.db' '*.db-*' '*.sqlite' '*.sqlite-*' '*.sqlite3' '*.sqlite3-*'
  fi
fi
if [[ -d "$WORK_DIR/frontend" ]]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude='dist/.user.ini' \
      "$WORK_DIR/frontend/" "$APP_DIR/frontend/"
  else
    sync_tree_without_rsync "$WORK_DIR/frontend" "$APP_DIR/frontend" 'dist/.user.ini'
  fi
fi
if [[ -d "$WORK_DIR/scripts" ]]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude='__pycache__/' \
      --exclude='*.pyc' \
      --exclude='*.pyo' \
      "$WORK_DIR/scripts/" "$APP_DIR/scripts/"
  else
    sync_tree_without_rsync "$WORK_DIR/scripts" "$APP_DIR/scripts" '__pycache__/' '*.pyc' '*.pyo'
  fi
fi
if [[ -d "$WORK_DIR/docs" ]]; then
  mkdir -p "$APP_DIR/docs"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$WORK_DIR/docs/" "$APP_DIR/docs/"
  else
    sync_tree_without_rsync "$WORK_DIR/docs" "$APP_DIR/docs"
  fi
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

if [[ -f "$BACKUP_DIR/storage-files.tar.gz" ]]; then
  echo "Restoring durable image files from $BACKUP_DIR"
  mkdir -p "$WORK_DIR/storage"
  tar -xzf "$BACKUP_DIR/storage-files.tar.gz" -C "$WORK_DIR"
  for directory in original preview thumbnail; do
    source_dir="$WORK_DIR/storage/$directory"
    target_dir="$APP_DIR/storage/$directory"
    if [[ -d "$source_dir" ]]; then
      mkdir -p "$target_dir"
      if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete "$source_dir/" "$target_dir/"
      else
        sync_tree_without_rsync "$source_dir" "$target_dir"
      fi
    elif [[ -d "$target_dir" ]]; then
      rm -rf -- "$target_dir"
    fi
  done
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

if [[ -x "$APP_DIR/venv/bin/python" && -f "$APP_DIR/backend/requirements.lock.txt" ]]; then
  "$APP_DIR/venv/bin/python" -m pip install --upgrade "pip==$PIP_BOOTSTRAP_VERSION"
  "$APP_DIR/venv/bin/python" -m pip install --require-hashes -r "$APP_DIR/backend/requirements.lock.txt"
elif [[ -x "$APP_DIR/venv/bin/python" && -f "$APP_DIR/backend/requirements.txt" ]]; then
  echo "Warning: restoring a legacy backup without a hashed dependency lock." >&2
  "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/backend/requirements.txt"
fi

echo "Restore completed"
