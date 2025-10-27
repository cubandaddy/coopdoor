#!/usr/bin/env bash
set -euo pipefail

# =====================================================
# CoopDoor Backup Utility v3.3
# =====================================================
# Backs up all configuration and state
# Creates timestamped archive
# =====================================================

# Get script directory and source shared config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

# Backup settings
BACKUP_NAME="coopdoor-backup-${BACKUP_DATE}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# ========== BACKUP FUNCTIONS ==========

create_backup_dir() {
    log "Creating backup directory"
    mkdir -p "${BACKUP_PATH}"/{config,systemd,runtime}
}

backup_system_config() {
    log "Backing up system configuration"
    
    if [[ -d "${SYSTEM_CONF_DIR}" ]]; then
        cp -r "${SYSTEM_CONF_DIR}"/* "${BACKUP_PATH}/config/" 2>/dev/null || true
        log "  Backed up ${SYSTEM_CONF_DIR}"
    else
        warn "System config directory not found: ${SYSTEM_CONF_DIR}"
    fi
}

backup_user_config() {
    log "Backing up user configuration"
    
    local real_home=$(get_real_home)
    local user_conf="${real_home}/.config/coopdoor"
    
    if [[ -d "${user_conf}" ]]; then
        cp -r "${user_conf}"/* "${BACKUP_PATH}/config/" 2>/dev/null || true
        log "  Backed up ${user_conf}"
    else
        log "  No user config found (${user_conf})"
    fi
}

backup_runtime_data() {
    log "Backing up runtime data"
    
    local real_home=$(get_real_home)
    local user_cache="${real_home}/.cache/coopdoor"
    
    if [[ -d "${user_cache}" ]]; then
        # Backup logs but not sockets/pids
        [[ -f "${user_cache}/coopd.log" ]] && cp "${user_cache}/coopd.log" "${BACKUP_PATH}/runtime/" 2>/dev/null || true
        log "  Backed up runtime data"
    fi
}

backup_systemd_overrides() {
    log "Backing up systemd service overrides"
    
    for service in "${SERVICES[@]}"; do
        local service_file="${SYSTEMD_DIR}/${service}"
        if [[ -f "${service_file}" ]]; then
            cp "${service_file}" "${BACKUP_PATH}/systemd/" 2>/dev/null || true
        fi
        
        # Check for dropins
        local dropin_dir="${SYSTEMD_DIR}/${service}.d"
        if [[ -d "${dropin_dir}" ]]; then
            cp -r "${dropin_dir}" "${BACKUP_PATH}/systemd/" 2>/dev/null || true
        fi
    done
    
    log "  Backed up systemd files"
}

backup_metadata() {
    log "Creating backup metadata"
    
    cat > "${BACKUP_PATH}/backup-info.txt" <<EOF
CoopDoor Backup Information
===========================
Date: ${BACKUP_DATE}
Hostname: $(hostname)
User: $(get_real_user)
System: $(uname -a)

Backed up from:
  - ${SYSTEM_CONF_DIR}
  - ~/.config/coopdoor
  - ~/.cache/coopdoor
  - ${SYSTEMD_DIR}

To restore this backup:
  sudo ${SCRIPT_DIR}/restore.sh "${BACKUP_PATH}"

EOF
}

create_archive() {
    log "Creating compressed archive"
    
    local archive="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
    cd "${BACKUP_DIR}"
    tar -czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}/" 2>/dev/null
    rm -rf "${BACKUP_PATH}"
    
    log "  Archive created: ${archive}"
    log "  Size: $(du -h "${archive}" | cut -f1)"
}

# ========== USAGE ==========

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Creates a timestamped backup of all CoopDoor configuration and state.

Options:
  --no-archive     Don't compress, keep as directory
  --output PATH    Backup to specific directory (default: ${BACKUP_DIR})
  -h, --help       Show this help message

Examples:
  # Standard backup
  sudo $(basename "$0")
  
  # Backup to custom location
  sudo $(basename "$0") --output /mnt/backups
  
  # Keep as directory (no tar.gz)
  sudo $(basename "$0") --no-archive

The backup includes:
  - Device configuration (MAC address, settings)
  - Automation configuration (schedules, modes)
  - Systemd service files and overrides
  - Runtime logs

EOF
    exit 0
}

# ========== MAIN ==========

main() {
    local no_archive=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-archive)
                no_archive=true
                shift
                ;;
            --output)
                BACKUP_DIR="$2"
                BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"
                shift 2
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
    
    log "CoopDoor Backup Utility v3.3"
    log "============================"
    log ""
    log "Backup name: ${BACKUP_NAME}"
    log "Backup path: ${BACKUP_DIR}"
    log ""
    
    create_backup_dir
    backup_system_config
    backup_user_config
    backup_runtime_data
    backup_systemd_overrides
    backup_metadata
    
    if [[ "${no_archive}" == "false" ]]; then
        create_archive
    fi
    
    log ""
    log "=============================="
    log "Backup Complete!"
    log "=============================="
    log ""
    
    if [[ "${no_archive}" == "false" ]]; then
        log "Backup archive: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
        log ""
        log "To restore:"
        log "  sudo ${SCRIPT_DIR}/restore.sh ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
    else
        log "Backup directory: ${BACKUP_PATH}"
        log ""
        log "To restore:"
        log "  sudo ${SCRIPT_DIR}/restore.sh ${BACKUP_PATH}"
    fi
    
    log ""
}

main "$@"
