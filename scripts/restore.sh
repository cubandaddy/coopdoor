#!/usr/bin/env bash
set -euo pipefail

# =====================================================
# CoopDoor Restore Utility v3.3
# =====================================================
# Restores configuration from backup
# Maintains service state
# =====================================================

# Get script directory and source shared config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

# Restore settings
BACKUP_SOURCE=""
TEMP_EXTRACT_DIR=""
SKIP_CONFIRM=false
RESTART_SERVICES=true

# ========== CLEANUP ==========

cleanup() {
    if [[ -n "${TEMP_EXTRACT_DIR}" && -d "${TEMP_EXTRACT_DIR}" ]]; then
        rm -rf "${TEMP_EXTRACT_DIR}"
    fi
}

trap cleanup EXIT

# ========== VALIDATION ==========

validate_backup() {
    local backup="$1"
    
    if [[ ! -e "${backup}" ]]; then
        die "Backup not found: ${backup}"
    fi
    
    # Check if it's an archive or directory
    if [[ -f "${backup}" ]]; then
        if [[ "${backup}" =~ \.tar\.gz$ ]]; then
            log "Detected archive: ${backup}"
            
            # Extract to temp directory
            TEMP_EXTRACT_DIR=$(mktemp -d)
            log "Extracting archive..."
            tar -xzf "${backup}" -C "${TEMP_EXTRACT_DIR}"
            
            # Find the backup directory inside
            local extracted=$(find "${TEMP_EXTRACT_DIR}" -mindepth 1 -maxdepth 1 -type d | head -1)
            if [[ -z "${extracted}" ]]; then
                die "Invalid backup archive: no backup directory found"
            fi
            
            BACKUP_SOURCE="${extracted}"
        else
            die "Unsupported backup format. Expected .tar.gz archive or directory"
        fi
    elif [[ -d "${backup}" ]]; then
        log "Detected backup directory: ${backup}"
        BACKUP_SOURCE="${backup}"
    else
        die "Invalid backup: not a file or directory"
    fi
    
    # Validate backup structure
    if [[ ! -d "${BACKUP_SOURCE}/config" ]]; then
        die "Invalid backup: missing config directory"
    fi
    
    log "Backup validated successfully"
}

# ========== CONFIRMATION ==========

confirm_restore() {
    if [[ "${SKIP_CONFIRM}" == "true" ]]; then
        return 0
    fi
    
    log ""
    log "This will restore configuration from:"
    log "  ${BACKUP_SOURCE}"
    log ""
    log "Current configuration will be OVERWRITTEN:"
    log "  - ${SYSTEM_CONF_DIR}"
    log "  - ~/.config/coopdoor"
    
    if [[ "${RESTART_SERVICES}" == "true" ]]; then
        log "  - Services will be RESTARTED"
    fi
    
    log ""
    
    # Show backup info if available
    if [[ -f "${BACKUP_SOURCE}/backup-info.txt" ]]; then
        log "Backup information:"
        head -n 10 "${BACKUP_SOURCE}/backup-info.txt" | sed 's/^/  /'
        log ""
    fi
    
    read -p "Continue with restore? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Restore cancelled"
        exit 0
    fi
}

# ========== RESTORE FUNCTIONS ==========

stop_services_for_restore() {
    if [[ "${RESTART_SERVICES}" == "false" ]]; then
        return 0
    fi
    
    log "Stopping services"
    
    for service in "coopdoor-api.service" "coopdoor-apply-schedule.timer"; do
        if systemctl is-active --quiet "${service}" 2>/dev/null; then
            log "  Stopping ${service}"
            systemctl stop "${service}" 2>/dev/null || warn "Failed to stop ${service}"
        fi
    done
}

restore_system_config() {
    log "Restoring system configuration"
    
    if [[ -d "${BACKUP_SOURCE}/config" ]]; then
        mkdir -p "${SYSTEM_CONF_DIR}"
        cp -r "${BACKUP_SOURCE}/config"/* "${SYSTEM_CONF_DIR}/" 2>/dev/null || true
        chown -R "${APP_USER}:${APP_USER}" "${SYSTEM_CONF_DIR}"
        log "  Restored ${SYSTEM_CONF_DIR}"
    else
        warn "No config directory in backup"
    fi
}

restore_user_config() {
    log "Restoring user configuration"
    
    local real_home=$(get_real_home)
    local real_user=$(get_real_user)
    local user_conf="${real_home}/.config/coopdoor"
    
    if [[ -d "${BACKUP_SOURCE}/config" ]]; then
        sudo -u "${real_user}" mkdir -p "${user_conf}"
        sudo -u "${real_user}" cp -r "${BACKUP_SOURCE}/config"/* "${user_conf}/" 2>/dev/null || true
        log "  Restored ${user_conf}"
    fi
}

restore_systemd_overrides() {
    log "Restoring systemd service overrides"
    
    if [[ -d "${BACKUP_SOURCE}/systemd" ]]; then
        # Only restore if user wants to overwrite systemd files
        log "  Found systemd files in backup"
        log "  Note: Service files are managed by installer"
        log "  Skipping systemd restore (use installer to update services)"
    fi
}

start_services_after_restore() {
    if [[ "${RESTART_SERVICES}" == "false" ]]; then
        return 0
    fi
    
    log "Starting services"
    
    systemctl daemon-reload
    
    for service in "coopdoor-api.service" "coopdoor-apply-schedule.timer"; do
        if systemctl is-enabled --quiet "${service}" 2>/dev/null; then
            log "  Starting ${service}"
            systemctl start "${service}" 2>/dev/null || warn "Failed to start ${service}"
        fi
    done
}

# ========== USAGE ==========

usage() {
    cat <<EOF
Usage: $(basename "$0") BACKUP [OPTIONS]

Restores CoopDoor configuration from a backup.

Arguments:
  BACKUP          Path to backup archive (.tar.gz) or directory

Options:
  --no-restart    Don't restart services after restore
  --yes           Skip confirmation prompt
  -h, --help      Show this help message

Examples:
  # Restore from archive
  sudo $(basename "$0") ~/coopdoor-backups/coopdoor-backup-20241026-120000.tar.gz
  
  # Restore from directory
  sudo $(basename "$0") ~/coopdoor-backups/coopdoor-backup-20241026-120000
  
  # Restore without restarting services
  sudo $(basename "$0") backup.tar.gz --no-restart
  
  # Restore without confirmation
  sudo $(basename "$0") backup.tar.gz --yes

The restore includes:
  - Device configuration (MAC address, settings)
  - Automation configuration (schedules, modes)
  - User configuration files

Note: Application files are NOT restored. Run the installer to update code.

EOF
    exit 0
}

# ========== MAIN ==========

main() {
    # Parse arguments
    if [[ $# -eq 0 ]]; then
        usage
    fi
    
    local backup_arg="$1"
    shift
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-restart)
                RESTART_SERVICES=false
                shift
                ;;
            --yes|-y)
                SKIP_CONFIRM=true
                shift
                ;;
            -h|--help)
                usage
                ;;
            *)
                die "Unknown option: $1. Use --help for usage."
                ;;
        esac
    done
    
    need_root
    
    log "CoopDoor Restore Utility v3.3"
    log "============================="
    log ""
    
    validate_backup "${backup_arg}"
    confirm_restore
    
    log ""
    log "Beginning restore..."
    log ""
    
    stop_services_for_restore
    restore_system_config
    restore_user_config
    restore_systemd_overrides
    start_services_after_restore
    
    log ""
    log "=============================="
    log "Restore Complete!"
    log "=============================="
    log ""
    log "Configuration has been restored from:"
    log "  ${backup_arg}"
    log ""
    
    if [[ "${RESTART_SERVICES}" == "true" ]]; then
        log "Services have been restarted"
        log ""
        log "Check status:"
        log "  systemctl status coopdoor-api"
        log "  coop-door status"
    else
        log "Services were NOT restarted (--no-restart)"
        log ""
        log "To apply changes, restart services:"
        log "  sudo systemctl restart coopdoor-api"
    fi
    
    log ""
}

main "$@"
