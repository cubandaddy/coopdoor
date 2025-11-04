#!/usr/bin/env bash
set -euo pipefail

# CoopDoor Uninstallation Script - Improved Architecture Edition
# Removes CoopDoor system while optionally preserving configuration

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
CoopDoor Uninstaller (Improved Architecture Edition)

Usage: sudo ./uninstall.sh [OPTIONS]

Options:
  --keep-config    Keep configuration files in ${CONFIG_DIR}
  -h, --help       Show this help message

Default behavior removes everything including configuration.
Backups in ${BACKUP_DIR} are always preserved.

This version removes the persistent daemon service (coopdoor-daemon.service).
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
        "coopdoor-daemon.service"          # NEW: Persistent daemon
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
        "coopdoor-daemon.service"          # NEW: Persistent daemon
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
        rm -rf "${SYSTEM_APP_DIR}"
        log "Removed ${SYSTEM_APP_DIR}"
    fi
    
    if [[ -f "${CLI_SHIM}" ]]; then
        rm -f "${CLI_SHIM}"
        log "Removed ${CLI_SHIM}"
    fi
}

remove_config() {
    if [[ "${KEEP_CONFIG}" == "true" ]]; then
        log "Preserving configuration files in ${CONFIG_DIR}"
        return
    fi
    
    log "Removing configuration files"
    
    if [[ -d "${CONFIG_DIR}" ]]; then
        # Create backup before removing
        local backup_name="config-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
        local backup_path="${BACKUP_DIR}/${backup_name}"
        
        mkdir -p "${BACKUP_DIR}"
        tar -czf "${backup_path}" -C "$(dirname ${CONFIG_DIR})" "$(basename ${CONFIG_DIR})" 2>/dev/null || true
        
        if [[ -f "${backup_path}" ]]; then
            log "Configuration backed up to ${backup_path}"
        fi
        
        rm -rf "${CONFIG_DIR}"
        log "Removed ${CONFIG_DIR}"
    fi
}

remove_sudoers() {
    log "Removing sudoers configuration"
    
    if [[ -f "/etc/sudoers.d/coopdoor-apply" ]]; then
        rm -f "/etc/sudoers.d/coopdoor-apply"
        log "Removed /etc/sudoers.d/coopdoor-apply"
    fi
}

remove_app_user() {
    log "Checking for application user"
    
    if id "coop" &>/dev/null; then
        # Check if user has any running processes
        if pgrep -u coop >/dev/null 2>&1; then
            log "Warning: User 'coop' still has running processes"
            log "Skipping user removal. Run 'sudo userdel coop' manually if desired."
        else
            read -p "Remove user 'coop'? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                userdel coop
                log "Removed user 'coop'"
            else
                log "Keeping user 'coop'"
            fi
        fi
    fi
}

cleanup_daemon_runtime() {
    log "Cleaning up daemon runtime files"
    
    # Remove daemon cache/runtime files
    local runtime_dirs=(
        "/run/coopdoor"
        "/home/coop/.cache/coopdoor"
    )
    
    for dir in "${runtime_dirs[@]}"; do
        if [[ -d "${dir}" ]]; then
            rm -rf "${dir}"
            log "Removed ${dir}"
        fi
    done
}

print_summary() {
    cat <<EOF

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   CoopDoor has been uninstalled                              ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

What was removed:
  ✓ Application files (${SYSTEM_APP_DIR})
  ✓ Systemd services (including coopdoor-daemon.service)
  ✓ CLI shim (${CLI_SHIM})
  ✓ Sudoers configuration
  ✓ Runtime files and caches

EOF

    if [[ "${KEEP_CONFIG}" == "true" ]]; then
        cat <<EOF
Configuration preserved:
  • ${CONFIG_DIR}

EOF
    else
        cat <<EOF
Configuration removed:
  • ${CONFIG_DIR}
  • Backup saved in ${BACKUP_DIR}

EOF
    fi

    cat <<EOF
Still present (if created):
  • Backups: ${BACKUP_DIR}
  • User 'coop' (if not removed)

To reinstall:
  sudo ./install.sh

EOF
}

confirm_uninstall() {
    cat <<EOF

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ⚠️  CoopDoor Uninstallation                                 ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

This will remove:
  • All services (including persistent daemon)
  • Application files
  • Python virtual environment
  • CLI tools

EOF

    if [[ "${KEEP_CONFIG}" == "true" ]]; then
        echo "Configuration will be PRESERVED in ${CONFIG_DIR}"
    else
        echo "Configuration will be REMOVED (backed up to ${BACKUP_DIR})"
    fi

    echo ""
    read -p "Are you sure you want to uninstall CoopDoor? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Uninstallation cancelled"
        exit 0
    fi
}

main() {
    log "Starting CoopDoor uninstallation (Improved Architecture)"
    
    check_root
    parse_args "$@"
    confirm_uninstall
    
    stop_services
    remove_systemd_services
    cleanup_daemon_runtime
    remove_app_files
    remove_sudoers
    remove_config
    remove_app_user
    
    print_summary
    
    log "Uninstallation complete"
}

main "$@"
