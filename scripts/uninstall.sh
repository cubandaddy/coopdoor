#!/usr/bin/env bash
set -euo pipefail

# CoopDoor Uninstallation Script
# Removes the CoopDoor system while optionally preserving configuration

SYSTEM_APP_DIR="/opt/coopdoor"
CLI_SHIM="/usr/local/bin/coop-door"
SYSTEMD_DIR="/etc/systemd/system"
CONFIG_DIR="/etc/coopdoor"
BACKUP_DIR="/var/lib/coopdoor-backups"

KEEP_CONFIG=false

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

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --keep-config)
                KEEP_CONFIG=true
                log "Config preservation mode enabled"
                shift
                ;;
            -h|--help)
                cat <<EOF
CoopDoor Uninstaller

Usage: sudo ./uninstall.sh [OPTIONS]

Options:
  --keep-config    Keep configuration files in ${CONFIG_DIR}
  -h, --help       Show this help message

Default behavior removes everything including configuration.
Backups in ${BACKUP_DIR} are always preserved.
EOF
                exit 0
                ;;
            *)
                error "Unknown option: $1. Use --help for usage."
                ;;
        esac
    done
}

stop_services() {
    log "Stopping and disabling services"
    
    local services=(
        "coopdoor-api.service"
        "coopdoor-apply-schedule.timer"
        "coopdoor-apply-schedule.service"
        "coopdoor-open.timer"
        "coopdoor-open.service"
        "coopdoor-close.timer"
        "coopdoor-close.service"
    )
    
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "${service}"; then
            log "Stopping ${service}"
            systemctl stop "${service}" || true
        fi
        
        if systemctl is-enabled --quiet "${service}" 2>/dev/null; then
            log "Disabling ${service}"
            systemctl disable "${service}" || true
        fi
    done
}

remove_systemd_services() {
    log "Removing systemd service files"
    
    local files=(
        "coopdoor-api.service"
        "coopdoor-apply-schedule.service"
        "coopdoor-apply-schedule.timer"
        "coopdoor-open.service"
        "coopdoor-open.timer"
        "coopdoor-close.service"
        "coopdoor-close.timer"
    )
    
    for file in "${files[@]}"; do
        if [[ -f "${SYSTEMD_DIR}/${file}" ]]; then
            log "Removing ${SYSTEMD_DIR}/${file}"
            rm -f "${SYSTEMD_DIR}/${file}"
        fi
    done
    
    systemctl daemon-reload
}

remove_app_files() {
    log "Removing application files"
    
    if [[ -d "${SYSTEM_APP_DIR}" ]]; then
        log "Removing ${SYSTEM_APP_DIR}"
        rm -rf "${SYSTEM_APP_DIR}"
    fi
    
    if [[ -f "${CLI_SHIM}" ]]; then
        log "Removing ${CLI_SHIM}"
        rm -f "${CLI_SHIM}"
    fi
}

remove_config() {
    if [[ "${KEEP_CONFIG}" == "true" ]]; then
        log "Keeping configuration files in ${CONFIG_DIR}"
        log "To remove manually later: sudo rm -rf ${CONFIG_DIR}"
    else
        if [[ -d "${CONFIG_DIR}" ]]; then
            log "Removing configuration directory ${CONFIG_DIR}"
            rm -rf "${CONFIG_DIR}"
        fi
    fi
}

cleanup_user_data() {
    log "Checking for user data"
    
    # Check for user's home directory cache
    local user_homes=(/home/*)
    for home in "${user_homes[@]}"; do
        if [[ -d "${home}/.cache/coopdoor" ]]; then
            log "Found user cache: ${home}/.cache/coopdoor"
            rm -rf "${home}/.cache/coopdoor"
        fi
        
        if [[ -d "${home}/.config/coopdoor" ]]; then
            log "Found user config: ${home}/.config/coopdoor"
            rm -rf "${home}/.config/coopdoor"
        fi
    done
}

check_tailscale() {
    if command -v tailscale >/dev/null 2>&1; then
        log "Tailscale detected - you may want to remove funnel/serve config manually"
        log "Run: tailscale serve reset"
    fi
}

print_summary() {
    cat <<EOF

═══════════════════════════════════════════════════════════════
  CoopDoor Uninstallation Complete
═══════════════════════════════════════════════════════════════

Removed:
- Application files: ${SYSTEM_APP_DIR}
- CLI command: ${CLI_SHIM}
- Systemd services

EOF

    if [[ "${KEEP_CONFIG}" == "true" ]]; then
        cat <<EOF
Preserved:
- Configuration: ${CONFIG_DIR}
- Backups: ${BACKUP_DIR}

To remove configuration later:
  sudo rm -rf ${CONFIG_DIR}

To remove backups:
  sudo rm -rf ${BACKUP_DIR}
EOF
    else
        cat <<EOF
Configuration removed: ${CONFIG_DIR}

Backups preserved: ${BACKUP_DIR}
  (These survive uninstall and can be manually removed if needed)

To remove backups:
  sudo rm -rf ${BACKUP_DIR}
EOF
    fi

    cat <<EOF

═══════════════════════════════════════════════════════════════
EOF
}

confirm_uninstall() {
    if [[ "${KEEP_CONFIG}" == "true" ]]; then
        echo "This will remove CoopDoor but KEEP configuration files."
    else
        echo "This will completely remove CoopDoor including all configuration."
        echo "(Backups in ${BACKUP_DIR} will be preserved)"
    fi
    
    read -p "Are you sure you want to continue? [y/N] " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Uninstallation cancelled"
        exit 0
    fi
}

main() {
    log "Starting CoopDoor uninstallation"
    
    check_root
    parse_args "$@"
    confirm_uninstall
    
    stop_services
    remove_systemd_services
    remove_app_files
    remove_config
    cleanup_user_data
    check_tailscale
    
    print_summary
    
    log "Uninstallation completed"
}

main "$@"