#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/anime-gallery"
SERVICE_NAME="anime-gallery"
WEB_USER="www-data"
WEB_GROUP="www-data"
HOST="127.0.0.1"
PORT="8000"
WRITE_ENV="1"
INSTALL_SUDOERS="1"
START_SERVICE="1"

usage() {
  cat <<'EOF'
Install MoeGallery systemd units.

Usage:
  sudo bash scripts/install_systemd.sh [options]

Options:
  --app-dir PATH          Application directory. Default: /opt/anime-gallery
  --service NAME          Main systemd service name. Default: anime-gallery
  --user USER             Web service user. Default: www-data
  --group GROUP           Web service group. Default: www-data
  --host HOST             Backend bind host. Default: 127.0.0.1
  --port PORT             Backend bind port. Default: 8000
  --no-env                Do not add updater defaults to .env
  --no-sudoers            Do not install passwordless updater sudoers rule
  --no-start              Install units but do not enable/start the main service
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
    --no-env)
      WRITE_ENV="0"
      shift
      ;;
    --no-sudoers)
      INSTALL_SUDOERS="0"
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

if [[ "${EUID}" -ne 0 ]]; then
  echo "install_systemd.sh must be run as root" >&2
  exit 1
fi

SYSTEMCTL="$(command -v systemctl || true)"
if [[ -z "$SYSTEMCTL" ]]; then
  echo "systemctl not found; this installer only supports systemd hosts" >&2
  exit 1
fi

APP_DIR="${APP_DIR%/}"
UPDATER_UNIT="${SERVICE_NAME}-updater@.service"
UPDATER_TRIGGER="sudo -n ${SYSTEMCTL} start ${SERVICE_NAME}-updater@{task_id}.service"
HEALTH_URL="http://${HOST}:${PORT}/api/health"

install -d -o "$WEB_USER" -g "$WEB_GROUP" "$APP_DIR/storage/original"
install -d -o "$WEB_USER" -g "$WEB_GROUP" "$APP_DIR/storage/preview"
install -d -o "$WEB_USER" -g "$WEB_GROUP" "$APP_DIR/storage/thumbnail"
install -d -o "$WEB_USER" -g "$WEB_GROUP" "$APP_DIR/storage/tasks"
install -d -o "$WEB_USER" -g "$WEB_GROUP" "$APP_DIR/storage/updates"
install -d -o "$WEB_USER" -g "$WEB_GROUP" "$APP_DIR/logs"

cat >"/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=MoeGallery Backend
After=network.target

[Service]
WorkingDirectory=${APP_DIR}/backend
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn app.main:app --host ${HOST} --port ${PORT}
Restart=always
RestartSec=3
User=${WEB_USER}
Group=${WEB_GROUP}

[Install]
WantedBy=multi-user.target
EOF

cat >"/etc/systemd/system/${UPDATER_UNIT}" <<EOF
[Unit]
Description=MoeGallery updater task %i
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/scripts/update_runner.py --app-dir ${APP_DIR} --task-id %i

[Install]
WantedBy=multi-user.target
EOF

ensure_env_line() {
  local key="$1"
  local value="$2"
  local env_path="${APP_DIR}/.env"
  install -d "$(dirname "$env_path")"
  touch "$env_path"
  if grep -qE "^${key}=" "$env_path"; then
    return 0
  fi
  printf '%s=%s\n' "$key" "$value" >>"$env_path"
}

if [[ "$WRITE_ENV" == "1" ]]; then
  ensure_env_line "AGMS_UPDATE_TRIGGER_COMMAND" "$UPDATER_TRIGGER"
  ensure_env_line "AGMS_UPDATE_SERVICE_NAME" "$SERVICE_NAME"
  ensure_env_line "AGMS_UPDATE_HEALTH_URL" "$HEALTH_URL"
  chown "$WEB_USER:$WEB_GROUP" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
fi

if [[ "$INSTALL_SUDOERS" == "1" ]]; then
  SUDOERS_PATH="/etc/sudoers.d/${SERVICE_NAME}-updater"
  cat >"$SUDOERS_PATH" <<EOF
${WEB_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL} start ${SERVICE_NAME}-updater@*.service
EOF
  chmod 440 "$SUDOERS_PATH"
  if command -v visudo >/dev/null 2>&1; then
    visudo -cf "$SUDOERS_PATH" >/dev/null
  fi
fi

"$SYSTEMCTL" daemon-reload
if [[ "$START_SERVICE" == "1" ]]; then
  "$SYSTEMCTL" enable --now "${SERVICE_NAME}.service"
fi

cat <<EOF
Installed:
  ${SERVICE_NAME}.service
  ${UPDATER_UNIT}

Updater trigger:
  ${UPDATER_TRIGGER}
EOF
