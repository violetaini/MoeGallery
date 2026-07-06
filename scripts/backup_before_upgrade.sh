#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/anime-gallery"
BACKUP_ROOT=""
ENV_FILE=""
SKIP_DATABASE=0
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage: backup_before_upgrade.sh [options]

Options:
  --app-dir DIR        Application directory. Default: /opt/anime-gallery
  --backup-root DIR    Backup root. Default: <app-dir>/backups
  --env-file FILE      Environment file. Default: <app-dir>/.env
  --skip-database      Back up only files, not the configured database
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
    --skip-database)
      SKIP_DATABASE=1
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

APP_DIR="${APP_DIR%/}"
BACKUP_ROOT="${BACKUP_ROOT:-$APP_DIR/backups}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/upgrade-$TIMESTAMP"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" || true

echo "Creating backup in $BACKUP_DIR"

copy_if_exists() {
  local source="$1"
  local target="$2"
  if [[ -e "$source" ]]; then
    mkdir -p "$(dirname "$target")"
    cp -a "$source" "$target"
  fi
}

copy_if_exists "$ENV_FILE" "$BACKUP_DIR/env/.env"
copy_if_exists "$APP_DIR/installed.lock" "$BACKUP_DIR/install/installed.lock"
copy_if_exists "$APP_DIR/VERSION" "$BACKUP_DIR/install/VERSION"

app_items=()
for item in backend frontend scripts docs .env.example LICENSE README.md README_zh.md README_zh-TW.md README_ja.md VERSION RELEASE_NOTES.md; do
  if [[ -e "$APP_DIR/$item" ]]; then
    app_items+=("$item")
  fi
done

if [[ ${#app_items[@]} -gt 0 ]]; then
  tar \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='backend/anime_gallery.db*' \
    --exclude='frontend/node_modules' \
    --exclude='frontend/dist/.vite' \
    -czf "$BACKUP_DIR/app-files.tar.gz" \
    -C "$APP_DIR" \
    "${app_items[@]}"
fi

if [[ "$SKIP_DATABASE" -eq 0 ]]; then
  "$PYTHON_BIN" - "$APP_DIR" "$ENV_FILE" "$BACKUP_DIR" <<'PY'
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


app_dir = Path(sys.argv[1]).resolve()
env_file = Path(sys.argv[2])
backup_dir = Path(sys.argv[3])
database_dir = backup_dir / "database"
database_dir.mkdir(parents=True, exist_ok=True)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


env_values = read_env(env_file)
database_url = os.environ.get("AGMS_DATABASE_URL") or env_values.get("AGMS_DATABASE_URL")
if not database_url:
    database_url = f"sqlite:///{(app_dir / 'backend' / 'anime_gallery.db').as_posix()}"

info: dict[str, object] = {
    "database_url_type": database_url.split(":", 1)[0],
    "backup": "",
    "message": "",
}

if database_url.startswith("sqlite"):
    db_path_text = database_url[len("sqlite:///") :] if database_url.startswith("sqlite:///") else ""
    db_path = Path(db_path_text).expanduser()
    if not db_path.is_absolute():
        db_path = app_dir / db_path
    info["path"] = str(db_path)
    if not db_path.exists():
        info["message"] = "SQLite database file does not exist; skipped database backup"
    else:
        target = database_dir / db_path.name
        source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
        info["backup"] = str(target)
        info["message"] = "SQLite database backed up with sqlite3 backup API"
elif database_url.startswith(("mysql", "mariadb")):
    parsed = urlparse(database_url)
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise SystemExit("MySQL database name is missing in AGMS_DATABASE_URL")
    mysqldump = shutil.which("mysqldump")
    if not mysqldump:
        raise SystemExit("mysqldump not found; install MySQL client tools or use --skip-database")
    target = database_dir / "mysql.sql"
    command = [
        mysqldump,
        "--single-transaction",
        "--routines",
        "--triggers",
        "--default-character-set=utf8mb4",
        "-h",
        host,
        "-P",
        str(port),
        "-u",
        username,
        database,
    ]
    run_env = os.environ.copy()
    if password:
        run_env["MYSQL_PWD"] = password
    with target.open("wb") as output:
        subprocess.run(command, check=True, stdout=output, env=run_env)
    info.update(
        {
            "host": host,
            "port": port,
            "database": database,
            "backup": str(target),
            "message": "MySQL database backed up with mysqldump",
        }
    )
else:
    info["message"] = f"Unsupported database URL type for automatic backup: {database_url.split(':', 1)[0]}"

(backup_dir / "database-backup.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(info["message"])
PY
else
  echo "Database backup skipped by request"
fi

cat > "$BACKUP_DIR/README.txt" <<EOF
MoeGallery upgrade backup
Created at: $TIMESTAMP
Application: $APP_DIR

Contents:
- env/.env when present
- install/installed.lock when present
- install/VERSION when present
- app-files.tar.gz for application files
- database/ for SQLite or MySQL dump when database backup is enabled

Restore strategy:
1. Stop the service.
2. Restore application files from app-files.tar.gz if needed.
3. Restore .env and installed.lock if needed.
4. Restore database from database/ using sqlite copy or mysql client tools.
5. Start the service.
EOF

echo "$BACKUP_DIR"
