#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="violetaini/MoeGallery"
APP_DIR="/opt/moegallery"
SERVICE_NAME="moegallery"
SERVICE_USER="moegallery"
SERVICE_GROUP="moegallery"
HOST=""
PORT="8111"
VERSION=""
GITHUB_PROXY="${MOEGALLERY_GITHUB_PROXY:-}"
REINSTALL="0"
NON_INTERACTIVE="0"

usage() {
  cat <<'EOF'
Install MoeGallery from an official GitHub Release.

Usage:
  sudo bash install.sh [options]

Options:
  --host HOST             127.0.0.1 or 0.0.0.0
  --port PORT             Listen port. Default: 8111
  --app-dir DIR           Install directory. Default: /opt/moegallery
  --service NAME          systemd service name. Default: moegallery
  --user USER             Dedicated service user. Default: moegallery
  --version VERSION       Install a specific release, for example v0.2.0
  --github-proxy URL      Optional generic GitHub download proxy prefix
  --reinstall             Replace program files while preserving data and .env
  --non-interactive       Use defaults without prompting
  -h, --help              Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:?missing value for --host}"
      shift 2
      ;;
    --port)
      PORT="${2:?missing value for --port}"
      shift 2
      ;;
    --app-dir)
      APP_DIR="${2:?missing value for --app-dir}"
      shift 2
      ;;
    --service)
      SERVICE_NAME="${2:?missing value for --service}"
      shift 2
      ;;
    --user)
      SERVICE_USER="${2:?missing value for --user}"
      SERVICE_GROUP="$SERVICE_USER"
      shift 2
      ;;
    --version)
      VERSION="${2:?missing value for --version}"
      shift 2
      ;;
    --github-proxy)
      GITHUB_PROXY="${2:?missing value for --github-proxy}"
      shift 2
      ;;
    --reinstall)
      REINSTALL="1"
      shift
      ;;
    --non-interactive)
      NON_INTERACTIVE="1"
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

if [[ "$EUID" -ne 0 ]]; then
  echo "Run this installer as root: sudo bash install.sh" >&2
  exit 1
fi
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  echo "--port must be between 1024 and 65535" >&2
  exit 2
fi

if [[ -z "$HOST" && "$NON_INTERACTIVE" == "0" && -r /dev/tty ]]; then
  cat >/dev/tty <<'EOF'
Listen mode:
  1. 127.0.0.1  (local access or your own reverse proxy, recommended)
  2. 0.0.0.0    (direct public/LAN access)
EOF
  read -r -p "Select [1]: " LISTEN_MODE </dev/tty
  if [[ "${LISTEN_MODE:-1}" == "2" ]]; then
    HOST="0.0.0.0"
  else
    HOST="127.0.0.1"
  fi
fi
HOST="${HOST:-127.0.0.1}"
if [[ "$HOST" != "127.0.0.1" && "$HOST" != "0.0.0.0" ]]; then
  echo "--host must be 127.0.0.1 or 0.0.0.0" >&2
  exit 2
fi

APP_DIR="${APP_DIR%/}"
if [[ -e "$APP_DIR/installed.lock" || -e "$APP_DIR/.env" ]]; then
  if [[ "$REINSTALL" != "1" ]]; then
    echo "MoeGallery is already installed in $APP_DIR." >&2
    echo "Use the panel update center, or pass --reinstall to repair program files." >&2
    exit 1
  fi
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "This installer currently supports Linux distributions using systemd." >&2
  exit 1
fi

install_dependencies() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y ca-certificates curl tar rsync python3 python3-venv python3-pip ffmpeg default-mysql-client
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates curl tar rsync python3 python3-pip
    dnf install -y ffmpeg || echo "Warning: ffmpeg is not available from enabled repositories; install it before uploading images."
    dnf install -y mysql || true
    return
  fi
  if command -v yum >/dev/null 2>&1; then
    yum install -y ca-certificates curl tar rsync python3 python3-pip
    yum install -y ffmpeg || echo "Warning: ffmpeg is not available from enabled repositories; install it before uploading images."
    yum install -y mysql || true
    return
  fi
  echo "Unsupported package manager. Install Python 3.11+, curl, tar, rsync and FFmpeg manually." >&2
  exit 1
}

proxy_url() {
  local target="$1"
  if [[ -z "$GITHUB_PROXY" ]]; then
    printf '%s\n' "$target"
  elif [[ "$GITHUB_PROXY" == *'{raw_url}'* ]]; then
    printf '%s\n' "${GITHUB_PROXY//\{raw_url\}/$target}"
  else
    printf '%s/%s\n' "${GITHUB_PROXY%/}" "$target"
  fi
}

download() {
  local source="$1"
  local target="$2"
  curl --fail --location --silent --show-error \
    --retry 5 --retry-delay 2 --connect-timeout 20 \
    --output "$target" "$(proxy_url "$source")"
}

echo "Installing system dependencies"
install_dependencies

PYTHON_BIN="$(command -v python3)"
if ! "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  echo "MoeGallery requires Python 3.11 or newer." >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

if [[ -n "$VERSION" ]]; then
  RELEASE_BASE="https://github.com/$REPOSITORY/releases/download/$VERSION"
else
  RELEASE_BASE="https://github.com/$REPOSITORY/releases/latest/download"
fi

echo "Downloading release manifest"
download "$RELEASE_BASE/SHA256SUMS.txt" "$TEMP_DIR/SHA256SUMS.txt"
ARCHIVE_NAME="$(awk '$2 ~ /^MoeGallery-v[^/]+\.tar\.gz$/ {gsub(/^\*/, "", $2); print $2; exit}' "$TEMP_DIR/SHA256SUMS.txt")"
if [[ -z "$ARCHIVE_NAME" ]]; then
  echo "SHA256SUMS.txt does not contain a MoeGallery .tar.gz release." >&2
  exit 1
fi

echo "Downloading $ARCHIVE_NAME"
download "$RELEASE_BASE/$ARCHIVE_NAME" "$TEMP_DIR/$ARCHIVE_NAME"
EXPECTED_SHA256="$(awk -v name="$ARCHIVE_NAME" '$2 == name || $2 == "*" name {print $1; exit}' "$TEMP_DIR/SHA256SUMS.txt")"
ACTUAL_SHA256="$(sha256sum "$TEMP_DIR/$ARCHIVE_NAME" | awk '{print $1}')"
if [[ -z "$EXPECTED_SHA256" || "$EXPECTED_SHA256" != "$ACTUAL_SHA256" ]]; then
  echo "Release checksum verification failed." >&2
  exit 1
fi

mkdir -p "$TEMP_DIR/stage"
tar -xzf "$TEMP_DIR/$ARCHIVE_NAME" -C "$TEMP_DIR/stage"
STAGE_DIR="$(find "$TEMP_DIR/stage" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$STAGE_DIR" || ! -f "$STAGE_DIR/backend/requirements.txt" || ! -f "$STAGE_DIR/frontend/dist/index.html" ]]; then
  echo "The downloaded archive is not a valid MoeGallery release." >&2
  exit 1
fi

echo "Installing MoeGallery into $APP_DIR"
mkdir -p "$APP_DIR"
rsync -a --delete \
  --exclude='.env' \
  --exclude='installed.lock' \
  --exclude='frontend/dist/.user.ini' \
  --exclude='storage/' \
  --exclude='logs/' \
  --exclude='backups/' \
  --exclude='venv/' \
  --exclude='*.db' \
  --exclude='*.db-*' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite-*' \
  --exclude='*.sqlite3' \
  --exclude='*.sqlite3-*' \
  "$STAGE_DIR/" "$APP_DIR/"

if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

bash "$APP_DIR/scripts/install_systemd.sh" \
  --app-dir "$APP_DIR" \
  --service "$SERVICE_NAME" \
  --user "$SERVICE_USER" \
  --group "$SERVICE_GROUP" \
  --host "$HOST" \
  --port "$PORT"

HEALTH_URL="http://127.0.0.1:$PORT/api/health"
for _ in {1..45}; do
  if curl --fail --silent "$HEALTH_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! curl --fail --silent "$HEALTH_URL" >/dev/null 2>&1; then
  echo "MoeGallery did not become healthy. Check: journalctl -u $SERVICE_NAME -n 100" >&2
  exit 1
fi

echo
echo "MoeGallery installation is ready."
echo "Service: $SERVICE_NAME"
if [[ "$HOST" == "0.0.0.0" ]]; then
  SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "First install: http://${SERVER_IP:-SERVER_IP}:$PORT/install"
  echo "Warning: direct HTTP access is not encrypted. Configure HTTPS before using it over an untrusted network."
else
  echo "First install: http://127.0.0.1:$PORT/install"
  echo "The service only listens locally. Configure your own reverse proxy or use an SSH tunnel when remote access is needed."
fi
