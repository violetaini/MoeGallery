#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/moegallery"
SERVICE_NAME="moegallery"
WEB_USER="moegallery"
WEB_GROUP="moegallery"
HOST="127.0.0.1"
PORT="8111"
CREATE_USER="1"
START_SERVICE="1"

usage() {
  cat <<'EOF'
Install the single MoeGallery systemd service.

Usage:
  sudo bash scripts/install_systemd.sh [options]

Options:
  --app-dir PATH          Application directory. Default: /opt/moegallery
  --service NAME          systemd service name. Default: moegallery
  --user USER             Service user. Default: moegallery
  --group GROUP           Service group. Default: moegallery
  --host HOST             127.0.0.1 or 0.0.0.0. Default: 127.0.0.1
  --port PORT             Backend and frontend port. Default: 8111
  --no-create-user        Require the service user and group to exist
  --no-start              Install the unit without enabling or starting it
  -h, --help              Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir)
      APP_DIR="${2:?missing value for --app-dir}"
      shift 2
      ;;
    --service)
      SERVICE_NAME="${2:?missing value for --service}"
      shift 2
      ;;
    --user)
      WEB_USER="${2:?missing value for --user}"
      shift 2
      ;;
    --group)
      WEB_GROUP="${2:?missing value for --group}"
      shift 2
      ;;
    --host)
      HOST="${2:?missing value for --host}"
      shift 2
      ;;
    --port)
      PORT="${2:?missing value for --port}"
      shift 2
      ;;
    --no-create-user)
      CREATE_USER="0"
      shift
      ;;
    --no-start)
      START_SERVICE="0"
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
  echo "install_systemd.sh must be run as root" >&2
  exit 1
fi
if [[ "$HOST" != "127.0.0.1" && "$HOST" != "0.0.0.0" ]]; then
  echo "--host must be 127.0.0.1 or 0.0.0.0" >&2
  exit 2
fi
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "--port must be between 1 and 65535" >&2
  exit 2
fi

SYSTEMCTL="$(command -v systemctl || true)"
if [[ -z "$SYSTEMCTL" ]]; then
  echo "systemctl not found; use the launcher directly on non-systemd hosts" >&2
  exit 1
fi

APP_DIR="${APP_DIR%/}"
if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
  echo "Python virtual environment is missing: $APP_DIR/venv/bin/python" >&2
  exit 1
fi
if [[ ! -f "$APP_DIR/scripts/moegallery_launcher.py" ]]; then
  echo "Built-in launcher is missing: $APP_DIR/scripts/moegallery_launcher.py" >&2
  exit 1
fi

if "$SYSTEMCTL" is-active --quiet "${SERVICE_NAME}.service"; then
  "$SYSTEMCTL" stop "${SERVICE_NAME}.service"
fi

if [[ "$CREATE_USER" == "1" ]]; then
  if ! getent group "$WEB_GROUP" >/dev/null 2>&1; then
    groupadd --system "$WEB_GROUP"
  fi
  if ! id "$WEB_USER" >/dev/null 2>&1; then
    useradd --system --gid "$WEB_GROUP" --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$WEB_USER"
  fi
fi
if ! id "$WEB_USER" >/dev/null 2>&1; then
  echo "Service user does not exist: $WEB_USER" >&2
  exit 1
fi
if ! getent group "$WEB_GROUP" >/dev/null 2>&1; then
  echo "Service group does not exist: $WEB_GROUP" >&2
  exit 1
fi

bash "$APP_DIR/scripts/create_linux_dirs.sh" \
  --app-dir "$APP_DIR" \
  --owner "$WEB_USER" \
  --group "$WEB_GROUP"

# The dedicated account owns release files so the in-process launcher can
# install a verified release without a privileged updater service.
chown -R "$WEB_USER:$WEB_GROUP" "$APP_DIR"
chmod 755 "$APP_DIR"
chmod 700 "$APP_DIR/backups"
if [[ -f "$APP_DIR/.env" ]]; then
  chmod 600 "$APP_DIR/.env"
fi

UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
UNIT_TEMP="${UNIT_PATH}.tmp.$$"
cat >"$UNIT_TEMP" <<EOF
[Unit]
Description=MoeGallery
After=network-online.target mysql.service mysqld.service mariadb.service
Wants=network-online.target

[Service]
Type=simple
User=${WEB_USER}
Group=${WEB_GROUP}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/scripts/moegallery_launcher.py --app-dir ${APP_DIR} --host ${HOST} --port ${PORT}
Restart=always
RestartSec=3
TimeoutStopSec=45
UMask=0027
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$UNIT_TEMP"
mv -f "$UNIT_TEMP" "$UNIT_PATH"

# Remove the legacy privileged updater. Existing installations are migrated
# when this script is run after upgrading to the new launcher release.
for legacy_service in "${SERVICE_NAME}-updater@.service" "anime-gallery-updater@.service"; do
  "$SYSTEMCTL" disable --now "$legacy_service" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$legacy_service"
done
rm -f "/etc/sudoers.d/${SERVICE_NAME}-updater" "/etc/sudoers.d/anime-gallery-updater"

"$SYSTEMCTL" daemon-reload
if [[ "$START_SERVICE" == "1" ]]; then
  "$SYSTEMCTL" enable "${SERVICE_NAME}.service"
  "$SYSTEMCTL" start "${SERVICE_NAME}.service"
fi

cat <<EOF
Installed ${SERVICE_NAME}.service
Listen: ${HOST}:${PORT}
Updater service: removed (updates are coordinated by the MoeGallery launcher)
EOF
