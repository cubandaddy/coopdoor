#!/usr/bin/env bash
set -euo pipefail

# Get script directory and source shared config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"
INSTALLER_DIR="$(dirname "${SCRIPT_DIR}")"

preflight_checks() {
    log "Running preflight checks"
    need_root; need_cmd python3; need_cmd systemctl
    
    local py_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log "Found Python ${py_version}"
    
    [[ -d "${INSTALLER_DIR}/app" ]] || die "app/ directory not found"
    [[ -d "${INSTALLER_DIR}/ui" ]] || die "ui/ directory not found"
    
    log "Updating package manager"
    apt-get update -y >/dev/null 2>&1
    apt-get install -y python3 python3-venv python3-pip curl >/dev/null 2>&1
    ensure_user "${APP_USER}"
}

setup_directories() {
    log "Setting up directory structure"
    mkdir -p "${SYSTEM_APP_DIR}" "${SYSTEM_APP_DIR}/ui" "${SYSTEM_CONF_DIR}"
    chown -R "${APP_USER}:${APP_USER}" "${SYSTEM_APP_DIR}" "${SYSTEM_CONF_DIR}"
    chmod 755 "${SYSTEM_APP_DIR}" "${SYSTEM_APP_DIR}/ui" "${SYSTEM_CONF_DIR}"
    
    # Create backup directory with proper permissions for API
    log "Setting up backup directory"
    mkdir -p "/var/lib/coopdoor-backups"
    chown "${APP_USER}:${APP_USER}" "/var/lib/coopdoor-backups"
    chmod 755 "/var/lib/coopdoor-backups"
    
    if [[ -n "${SUDO_USER:-}" ]]; then
        local real_home=$(get_real_home)
        sudo -u "${SUDO_USER}" mkdir -p "${real_home}/coopdoor" "${real_home}/.config/coopdoor" "${real_home}/.cache/coopdoor"
    fi
}

setup_python_env() {
    log "Setting up Python virtual environment"
    [[ ! -x "${BIN_PY}" ]] && sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
    log "Installing dependencies"
    sudo -u "${APP_USER}" "${BIN_PIP}" install --quiet --upgrade pip bleak "fastapi>=0.111" "uvicorn[standard]>=0.30" "astral>=3.2" "pgeocode>=0.4" >/dev/null 2>&1
}

install_app_files() {
    log "Installing application files"
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/coopd.py" "${SYSTEM_APP_DIR}/"
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/coopctl.py" "${SYSTEM_APP_DIR}/"
    install -m 0644 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/coopdoor_api.py" "${SYSTEM_APP_DIR}/"
    install -m 0755 -o "${APP_USER}" -g "${APP_USER}" "${INSTALLER_DIR}/app/schedule_apply.py" "${SYSTEM_APP_DIR}/"
    log "Installing UI files"
    cp -r "${INSTALLER_DIR}/ui"/* "${SYSTEM_APP_DIR}/ui/"
    chown -R "${APP_USER}:${APP_USER}" "${SYSTEM_APP_DIR}/ui"
    install -m 0755 "${INSTALLER_DIR}/config/coop-door-cli-shim" "${CLI_SHIM}"
}

write_configs() {
    log "Writing configuration files"
    cat > "${SYSTEM_CONF_DIR}/config.json" <<EOF
{
  "mac": "${MAC_DEFAULT}",
  "adapter": "${ADAPTER_DEFAULT}",
  "connect_timeout": ${CONNECT_TIMEOUT_DEFAULT},
  "base_pulses": ${BASE_PULSES_DEFAULT},
  "pulse_interval": ${PULSE_INTERVAL_DEFAULT},
  "home_before_open": ${HOME_BEFORE_OPEN_DEFAULT},
  "min_pause_after_action": ${MIN_PAUSE_AFTER_ACTION_DEFAULT}
}
EOF
    chown "${APP_USER}:${APP_USER}" "${SYSTEM_CONF_DIR}/config.json"
    
    if [[ -n "${SUDO_USER:-}" ]]; then
        local real_home=$(get_real_home)
        sudo -u "${SUDO_USER}" mkdir -p "${real_home}/.config/coopdoor"
        sudo -u "${SUDO_USER}" cp "${SYSTEM_CONF_DIR}/config.json" "${real_home}/.config/coopdoor/"
    fi
}

install_systemd_services() {
    log "Installing systemd services"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-api.service" "${SYSTEMD_DIR}/"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-apply-schedule.service" "${SYSTEMD_DIR}/"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-apply-schedule.timer" "${SYSTEMD_DIR}/"
    systemctl daemon-reload
    systemctl enable --now coopdoor-api.service coopdoor-apply-schedule.timer
}

install_sudoers() {
    log "Installing sudoers rule"
    install -m 0440 "${INSTALLER_DIR}/config/coopdoor-apply-sudoers" "${SUDOERS_FILE}"
    visudo -cf "${SUDOERS_FILE}" >/dev/null 2>&1 || { rm -f "${SUDOERS_FILE}"; die "Invalid sudoers file"; }
}

setup_tailscale() {
    [[ "${TAILSCALE_ENABLE_SERVE}" == "1" ]] && command -v tailscale >/dev/null 2>&1 && {
        log "Setting up Tailscale Serve"
        tailscale serve --bg http://127.0.0.1:8080 || warn "Tailscale serve failed"
    }
}

main() {
    log "CoopDoor Unified Installer v3.3"; log "Installing from: ${INSTALLER_DIR}"; log ""
    preflight_checks; setup_directories; setup_python_env; install_app_files
    write_configs; install_systemd_services; install_sudoers; setup_tailscale
    log ""; log "Installation Complete!"
    log "CLI: coop-door status | open 75 | close | diag"
    log "Web: http://127.0.0.1:8080/"
    log "Backup: sudo ${SCRIPT_DIR}/backup.sh"
    log "Uninstall: sudo ${SCRIPT_DIR}/uninstall.sh"
}

main "$@"
