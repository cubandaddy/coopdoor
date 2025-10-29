#!/usr/bin/env bash
set -euo pipefail

# CoopDoor Installation Script
# Installs the CoopDoor system with all dependencies and services

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEM_APP_DIR="/opt/coopdoor"
VENV_DIR="${SYSTEM_APP_DIR}/.venv"
CLI_SHIM="/usr/local/bin/coop-door"
APP_USER="root"

SYSTEMD_DIR="/etc/systemd/system"
CONFIG_DIR="/etc/coopdoor"
BACKUP_DIR="/var/lib/coopdoor-backups"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
    fi
}

check_dependencies() {
    log "Checking system dependencies"
    
    local missing=()
    
    command -v python3 >/dev/null 2>&1 || missing+=("python3")
    command -v pip3 >/dev/null 2>&1 || missing+=("python3-pip")
    command -v systemctl >/dev/null 2>&1 || missing+=("systemd")
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing dependencies: ${missing[*]}. Please install them first."
    fi
    
    # Check Python version (need 3.10+)
    local py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ $(echo "$py_version < 3.10" | bc -l 2>/dev/null || echo "0") -eq 1 ]]; then
        log "Warning: Python $py_version detected. Python 3.10+ recommended."
    fi
}

install_app_files() {
    log "Installing application files"
    
    mkdir -p "${SYSTEM_APP_DIR}"
    mkdir -p "${SYSTEM_APP_DIR}/ui"
    
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/coopd.py" "${SYSTEM_APP_DIR}/"
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/coopctl.py" "${SYSTEM_APP_DIR}/"
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/coopdoor_api.py" "${SYSTEM_APP_DIR}/"
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/schedule_apply.py" "${SYSTEM_APP_DIR}/"
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/door_state.py" "${SYSTEM_APP_DIR}/"
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/shared_config.py" "${SYSTEM_APP_DIR}/"
    
    log "Installing UI files"
    cp -r "${INSTALLER_DIR}/ui"/* "${SYSTEM_APP_DIR}/ui/"
    chown -R "${APP_USER}:${APP_USER}" "${SYSTEM_APP_DIR}/ui"
    
    install -m 0755 "${INSTALLER_DIR}/config/coop-door-cli-shim" "${CLI_SHIM}"
}

setup_venv() {
    log "Setting up Python virtual environment"
    
    if [[ -d "${VENV_DIR}" ]]; then
        log "Virtual environment already exists, recreating"
        rm -rf "${VENV_DIR}"
    fi
    
    python3 -m venv "${VENV_DIR}"
    
    log "Installing Python dependencies"
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install \
        fastapi \
        uvicorn[standard] \
        bleak \
        astral \
        pgeocode \
        requests
    
    chown -R "${APP_USER}:${APP_USER}" "${VENV_DIR}"
}

install_systemd_services() {
    log "Installing systemd services"
    
    # Install API service
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-api.service" "${SYSTEMD_DIR}/"
    
    # Install schedule timer and service
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-apply-schedule.service" "${SYSTEMD_DIR}/"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-apply-schedule.timer" "${SYSTEMD_DIR}/"
    
    systemctl daemon-reload
    
    log "Enabling and starting coopdoor-api service"
    systemctl enable coopdoor-api.service
    systemctl restart coopdoor-api.service
    
    log "Enabling coopdoor-apply-schedule timer"
    systemctl enable coopdoor-apply-schedule.timer
    systemctl start coopdoor-apply-schedule.timer
}

setup_config() {
    log "Setting up configuration directories"
    
    mkdir -p "${CONFIG_DIR}"
    mkdir -p "${BACKUP_DIR}"
    
    # Create default config if it doesn't exist
    if [[ ! -f "${CONFIG_DIR}/config.json" ]]; then
        log "Creating default device config"
        cat > "${CONFIG_DIR}/config.json" <<EOF
{
  "mac": "00:80:E1:22:EE:F2",
  "adapter": "hci0",
  "connect_timeout": 15,
  "base_pulses": 14,
  "pulse_interval": 2.0,
  "home_before_open": false,
  "min_pause_after_action": 1.0
}
EOF
    fi
    
    # Create default automation config if it doesn't exist
    if [[ ! -f "${CONFIG_DIR}/automation.json" ]]; then
        log "Creating default automation config"
        cat > "${CONFIG_DIR}/automation.json" <<EOF
{
  "mode": "fixed",
  "fixed": {
    "open": "07:00",
    "close": "20:30"
  },
  "open_percent": 100,
  "timezone": "America/New_York"
}
EOF
    fi
    
    # Initialize state files if they don't exist
    if [[ ! -f "${CONFIG_DIR}/door_state.json" ]]; then
        log "Initializing door state"
        cat > "${CONFIG_DIR}/door_state.json" <<EOF
{
  "position_pulses": 0,
  "position_percent": 0,
  "last_updated": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    fi
    
    chown -R "${APP_USER}:${APP_USER}" "${CONFIG_DIR}"
    chown -R "${APP_USER}:${APP_USER}" "${BACKUP_DIR}"
    chmod 755 "${CONFIG_DIR}"
    chmod 755 "${BACKUP_DIR}"
}

apply_schedule() {
    log "Applying initial schedule configuration"
    
    if [[ -x "${VENV_DIR}/bin/python3" && -f "${SYSTEM_APP_DIR}/schedule_apply.py" ]]; then
        "${VENV_DIR}/bin/python3" "${SYSTEM_APP_DIR}/schedule_apply.py" || log "Warning: Schedule apply failed (this is normal on first install)"
    fi
}

check_tailscale() {
    if command -v tailscale >/dev/null 2>&1; then
        log "Tailscale detected"
        
        if tailscale status >/dev/null 2>&1; then
            log "Setting up Tailscale funnel for remote access"
            tailscale serve --bg http://127.0.0.1:8080 || log "Warning: Tailscale serve setup failed"
        else
            log "Tailscale is installed but not connected. Run 'tailscale up' to enable remote access."
        fi
    fi
}

print_success() {
    local ip=$(hostname -I | awk '{print $1}')
    
    cat <<EOF

═══════════════════════════════════════════════════════════════
  CoopDoor Installation Complete! 🎉
═══════════════════════════════════════════════════════════════

Next steps:

1. Configure your BLE device MAC address:
   sudo coop-door config --set mac=XX:XX:XX:XX:XX:XX

2. Test the connection:
   coop-door status

3. Access the Web UI:
   Local:     http://${ip}:8080/
   Localhost: http://localhost:8080/

4. Configure your schedule in the Config tab

Services:
- API:       systemctl status coopdoor-api.service
- Scheduler: systemctl status coopdoor-apply-schedule.timer

Logs:
- API:       journalctl -u coopdoor-api.service -f
- Scheduler: journalctl -u coopdoor-apply-schedule.timer -f

Files:
- App:       ${SYSTEM_APP_DIR}/
- Config:    ${CONFIG_DIR}/
- Backups:   ${BACKUP_DIR}/
- CLI:       ${CLI_SHIM}

Documentation:
  cat ${INSTALLER_DIR}/README.md

═══════════════════════════════════════════════════════════════
EOF
}

main() {
    log "Starting CoopDoor installation"
    
    check_root
    check_dependencies
    install_app_files
    setup_venv
    setup_config
    install_systemd_services
    apply_schedule
    check_tailscale
    
    print_success
    
    log "Installation completed successfully"
}

main "$@"