#!/usr/bin/env bash
# Shared configuration for all CoopDoor scripts
# Source this file in other scripts: source "$(dirname "$0")/config.sh"

# ========== CONFIGURATION (Single Source of Truth) ==========

# Device defaults
readonly MAC_DEFAULT="00:80:E1:22:EE:F2"
readonly ADAPTER_DEFAULT="hci0"
readonly CONNECT_TIMEOUT_DEFAULT=15
readonly BASE_PULSES_DEFAULT=14
readonly PULSE_INTERVAL_DEFAULT=2.0
readonly HOME_BEFORE_OPEN_DEFAULT=false
readonly MIN_PAUSE_AFTER_ACTION_DEFAULT=1.0

# System paths
readonly APP_USER="coop"
readonly SYSTEM_APP_DIR="/opt/coopdoor"
readonly SYSTEM_CONF_DIR="/etc/coopdoor"
readonly SYSTEMD_DIR="/etc/systemd/system"
readonly SUDOERS_FILE="/etc/sudoers.d/coopdoor-apply"
readonly CLI_SHIM="/usr/local/bin/coop-door"

# Virtual environment
readonly VENV_DIR="${SYSTEM_APP_DIR}/.venv"
readonly BIN_PY="${VENV_DIR}/bin/python3"
readonly BIN_PIP="${VENV_DIR}/bin/pip"

# User paths
readonly USER_HOME="${HOME}"
readonly USER_CONF_DIR="${USER_HOME}/.config/coopdoor"
readonly USER_RUNTIME_DIR="${USER_HOME}/.cache/coopdoor"

# Services
readonly SERVICES=(
    "coopdoor-api.service"
    "coopdoor-apply-schedule.service"
    "coopdoor-apply-schedule.timer"
    "coopdoor-open.service"
    "coopdoor-close.service"
    "coopdoor-open.timer"
    "coopdoor-close.timer"
)

# Features
readonly TAILSCALE_ENABLE_SERVE="${TAILSCALE_ENABLE_SERVE:-1}"

# Backup settings
readonly BACKUP_DIR="${HOME}/coopdoor-backups"
readonly BACKUP_DATE=$(date +%Y%m%d-%H%M%S)

# ========== HELPER FUNCTIONS ==========

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARNING: $*" >&2; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }
need_root() { [[ $EUID -eq 0 ]] || die "This script must be run as root (use sudo)"; }

ensure_user() {
    local user="$1"
    if ! id "$user" >/dev/null 2>&1; then
        log "Creating user: $user"
        useradd -r -s /bin/bash -d "${SYSTEM_APP_DIR}" -c "Coop Door Service" "$user"
    fi
}

# Get the real user when running via sudo
get_real_user() {
    if [[ -n "${SUDO_USER:-}" ]]; then
        echo "${SUDO_USER}"
    else
        echo "${USER}"
    fi
}

get_real_home() {
    local real_user=$(get_real_user)
    getent passwd "${real_user}" | cut -d: -f6
}
