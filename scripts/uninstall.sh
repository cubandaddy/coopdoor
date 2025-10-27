#!/usr/bin/env bash
set -euo pipefail

# =====================================================
# CoopDoor Uninstaller v3.3
# =====================================================
# Safely removes all CoopDoor components
# Optionally preserves configuration
# =====================================================

# Get script directory and source shared config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

# Flags
KEEP_CONFIG=false
KEEP_USER=true
SKIP_CONFIRM=false

# ========== CONFIRMATION ==========

confirm_uninstall() {
    if [[ "${SKIP_CONFIRM}" == "true" ]]; then
        return 0
    fi
    
    log "This will remove:"
    log "  - Application files (${SYSTEM_APP_DIR})"
    log "  - CLI command (${CLI_SHIM})"
    log "  - Systemd services"
    log "  - Sudoers rules"
    
    if [[ "${KEEP_CONFIG}" == "false" ]]; then
        log "  - Configuration files (${SYSTEM_CONF_DIR}, ~/.config/coopdoor)"
    else
        log "  - Configuration will be PRESERVED"
    fi
    
    if [[ "${KEEP_USER}" == "false" ]]; then
        log "  - User account (${APP_USER})"
    else
        log "  - User account will be PRESERVED"
    fi
    
    log ""
    read -p "Continue with uninstall? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Uninstall cancelled"
        exit 0
    fi
}

# ========== STOP SERVICES ==========

stop_services() {
    log "Stopping services"
    
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "${service}" 2>/dev/null; then
            log "  Stopping ${service}"
            systemctl stop "${service}" 2>/dev/null || warn "Failed to stop ${service}"
        fi
        
        if systemctl is-enabled --quiet "${service}" 2>/dev/null; then
            log "  Disabling ${service}"
            systemctl disable "${service}" 2>/dev/null || warn "Failed to disable ${service}"
        fi
    done
}

# ========== REMOVE FILES ==========

remove_systemd_files() {
    log "Removing systemd files"
    
    for service in "${SERVICES[@]}"; do
        local service_file="${SYSTEMD_DIR}/${service}"
        if [[ -f "${service_file}" ]]; then
            log "  Removing ${service}"
            rm -f "${service_file}"
        fi
    done
    
    systemctl daemon-reload
}

remove_application_files() {
    log "Removing application files"
    
    if [[ -d "${SYSTEM_APP_DIR}" ]]; then
        log "  Removing ${SYSTEM_APP_DIR}"
        rm -rf "${SYSTEM_APP_DIR}"
    fi
    
    if [[ -f "${CLI_SHIM}" ]]; then
        log "  Removing ${CLI_SHIM}"
        rm -f "${CLI_SHIM}"
    fi
    
    if [[ -f "${SUDOERS_FILE}" ]]; then
        log "  Removing ${SUDOERS_FILE}"
        rm -f "${SUDOERS_FILE}"
    fi
}

remove_configuration() {
    if [[ "${KEEP_CONFIG}" == "true" ]]; then
        log "Preserving configuration (--keep-config)"
        return 0
    fi
    
    log "Removing configuration files"
    
    if [[ -d "${SYSTEM_CONF_DIR}" ]]; then
        log "  Removing ${SYSTEM_CONF_DIR}"
        rm -rf "${SYSTEM_CONF_DIR}"
    fi
    
    # Remove user configs
    if [[ -n "${SUDO_USER:-}" ]]; then
        local real_home=$(get_real_home)
        local user_conf="${real_home}/.config/coopdoor"
        local user_cache="${real_home}/.cache/coopdoor"
        
        if [[ -d "${user_conf}" ]]; then
            log "  Removing ${user_conf}"
            sudo -u "${SUDO_USER}" rm -rf "${user_conf}"
        fi
        
        if [[ -d "${user_cache}" ]]; then
            log "  Removing ${user_cache}"
            sudo -u "${SUDO_USER}" rm -rf "${user_cache}"
        fi
    fi
}

remove_user() {
    if [[ "${KEEP_USER}" == "true" ]]; then
        log "Preserving user account (--keep-user)"
        return 0
    fi
    
    if id "${APP_USER}" >/dev/null 2>&1; then
        log "Removing user: ${APP_USER}"
        userdel "${APP_USER}" 2>/dev/null || warn "Failed to remove user ${APP_USER}"
    fi
}

# ========== CLEANUP TAILSCALE ==========

cleanup_tailscale() {
    if command -v tailscale >/dev/null 2>&1; then
        log "Removing Tailscale configuration"
        tailscale serve off 2>/dev/null || log "  No Tailscale serve configuration found"
    fi
}

# ========== USAGE ==========

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --keep-config    Preserve configuration files
  --keep-user      Preserve ${APP_USER} user account
  --yes            Skip confirmation prompt
  -h, --help       Show this help message

Examples:
  # Full uninstall with confirmation
  sudo $(basename "$0")
  
  # Keep configs for reinstall
  sudo $(basename "$0") --keep-config
  
  # Uninstall without prompts
  sudo $(basename "$0") --yes

EOF
    exit 0
}

# ========== MAIN ==========

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --keep-config)
                KEEP_CONFIG=true
                shift
                ;;
            --keep-user)
                KEEP_USER=true
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
    
    log "CoopDoor Uninstaller v3.3"
    log "========================="
    log ""
    
    confirm_uninstall
    
    log ""
    log "Beginning uninstall..."
    log ""
    
    stop_services
    remove_systemd_files
    cleanup_tailscale
    remove_application_files
    remove_configuration
    remove_user
    
    log ""
    log "=============================="
    log "Uninstall Complete!"
    log "=============================="
    log ""
    
    if [[ "${KEEP_CONFIG}" == "true" ]]; then
        log "Configuration preserved at:"
        log "  ${SYSTEM_CONF_DIR}"
        log "  ~/.config/coopdoor"
        log ""
        log "To reinstall with same settings:"
        log "  sudo ${SCRIPT_DIR}/install.sh"
    fi
    
    log "Note: Config backups in /var/lib/coopdoor-backups are always preserved"
    log "and survive uninstallation. You can restore them after reinstalling."
    log ""
}

main "$@"
