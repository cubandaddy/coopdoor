#!/usr/bin/env bash
set -euo pipefail

# CoopDoor Installation Script - v3.5.3
# Installs CoopDoor with persistent daemon and reliable scheduling
# NOTE: Watchdog removed in v3.5.3 - caused false triggers, system reliable without it

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEM_APP_DIR="/opt/coopdoor"
VENV_DIR="${SYSTEM_APP_DIR}/.venv"
CLI_SHIM="/usr/local/bin/coop-door"
APP_USER="coop"

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
    local packages=()
    
    # Check for required commands and map to package names
    if ! command -v python3 >/dev/null 2>&1; then
        missing+=("python3")
        packages+=("python3")
    fi
    
    if ! command -v pip3 >/dev/null 2>&1; then
        missing+=("pip3")
        packages+=("python3-pip")
    fi
    
    if ! command -v systemctl >/dev/null 2>&1; then
        missing+=("systemctl")
        packages+=("systemd")
    fi
    
    # Also check for optional but recommended packages
    local optional=()
    if ! command -v hciconfig >/dev/null 2>&1; then
        optional+=("bluez")
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log "Missing required dependencies: ${missing[*]}"
        log ""
        log "Installing missing packages: ${packages[*]}"
        log "This requires sudo access and may take a few minutes..."
        
        # Auto-install with apt
        if command -v apt-get >/dev/null 2>&1; then
            apt-get update || error "Failed to update package list"
            apt-get install -y "${packages[@]}" || error "Failed to install dependencies"
            log "✓ Successfully installed: ${packages[*]}"
        else
            error "apt-get not found. Please manually install: ${packages[*]}"
        fi
    fi
    
    # Install optional packages if missing
    if [[ ${#optional[@]} -gt 0 ]]; then
        log "Installing recommended packages: ${optional[*]}"
        if command -v apt-get >/dev/null 2>&1; then
            apt-get install -y "${optional[@]}" 2>/dev/null || log "Note: Could not install optional packages (${optional[*]})"
        fi
    fi
    
    # Verify python3-venv is available (needed for virtual environment)
    if ! python3 -m venv --help >/dev/null 2>&1; then
        log "Installing python3-venv (required for virtual environment)"
        if command -v apt-get >/dev/null 2>&1; then
            apt-get install -y python3-venv || log "Warning: Could not install python3-venv"
        fi
    fi
    
    # Check Python version (need 3.10+)
    local py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local py_version_num=$(echo "$py_version" | tr -d '.')
    if [[ $py_version_num -lt 310 ]]; then
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
    
    if [[ -f "${INSTALLER_DIR}/requirements.txt" ]]; then
        log "Installing from requirements.txt"
        log ""
        log "⚠️  NOTE: Installing pandas (required by pgeocode) may take 5-15 minutes"
        log "    on Raspberry Pi as it compiles from source. This is normal!"
        log "    Please be patient..."
        log ""
        "${VENV_DIR}/bin/pip" install -r "${INSTALLER_DIR}/requirements.txt"
    else
        error "requirements.txt not found at ${INSTALLER_DIR}/requirements.txt"
    fi
}

create_app_user() {
    log "Creating application user: ${APP_USER}"
    
    if ! id "${APP_USER}" &>/dev/null; then
        useradd -r -s /bin/false -d "${SYSTEM_APP_DIR}" -c "CoopDoor Service User" "${APP_USER}"
    else
        log "User ${APP_USER} already exists"
    fi
}

install_systemd_services() {
    log "Installing systemd services (improved architecture)"
    
    # Install persistent daemon service
    log "Installing coopdoor-daemon.service (persistent BLE connection)"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-daemon.service" "${SYSTEMD_DIR}/"
    
    # Install API service
    log "Installing coopdoor-api.service"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-api.service" "${SYSTEMD_DIR}/"
    
    # Install schedule timer and service
    log "Installing coopdoor-apply-schedule timer and service"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-apply-schedule.service" "${SYSTEMD_DIR}/"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-apply-schedule.timer" "${SYSTEMD_DIR}/"
    
    # Install safety backup timer and service (NEW - replaces cron)
    log "Installing coopdoor-safety-backup timer and service (9 PM failsafe)"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-safety-backup.service" "${SYSTEMD_DIR}/"
    install -m 0644 "${INSTALLER_DIR}/systemd/coopdoor-safety-backup.timer" "${SYSTEMD_DIR}/"
    
    systemctl daemon-reload
    
    # Enable and start daemon first
    log "Enabling and starting coopdoor-daemon service"
    systemctl enable coopdoor-daemon.service
    systemctl start coopdoor-daemon.service
    
    # Wait for daemon to connect
    log "Waiting for daemon to connect to BLE device..."
    local max_wait=30
    local waited=0
    while [[ $waited -lt $max_wait ]]; do
        if journalctl -u coopdoor-daemon.service --since "1 minute ago" -n 50 | grep -q "CONNECTED"; then
            log "✓ Daemon connected to BLE device"
            break
        fi
        sleep 2
        waited=$((waited + 2))
    done
    
    if [[ $waited -ge $max_wait ]]; then
        log "⚠ Daemon did not connect within ${max_wait}s. Check 'journalctl -u coopdoor-daemon' for details."
    fi
    
    log "Enabling and starting coopdoor-api service"
    systemctl enable coopdoor-api.service
    systemctl restart coopdoor-api.service
    
    log "Enabling coopdoor-apply-schedule timer"
    systemctl enable coopdoor-apply-schedule.timer
    systemctl start coopdoor-apply-schedule.timer
    
    log "Enabling coopdoor-safety-backup timer (9 PM failsafe)"
    systemctl enable coopdoor-safety-backup.timer
    systemctl start coopdoor-safety-backup.timer
}

setup_config() {
    log "Setting up configuration directories"
    
    mkdir -p "${CONFIG_DIR}"
    mkdir -p "${BACKUP_DIR}"
    
    # Create log directories for improved scheduler
    log "Setting up logging directories"
    mkdir -p /var/log/coopdoor
    mkdir -p /var/lib/coopdoor
    chown -R "${APP_USER}:${APP_USER}" /var/log/coopdoor
    chown -R "${APP_USER}:${APP_USER}" /var/lib/coopdoor
    # Bug #10 fix: Ensure state directory is writable by coop user
    chmod 775 /var/lib/coopdoor
    chmod 775 /var/log/coopdoor
    
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
    
    # Create daemon environment file if it doesn't exist
    if [[ ! -f "${CONFIG_DIR}/daemon.env" ]]; then
        log "Creating daemon environment file"
        # Extract MAC from config.json if available, otherwise use default
        local mac_addr="00:80:E1:22:EE:F2"
        if [[ -f "${CONFIG_DIR}/config.json" ]]; then
            mac_addr=$(python3 -c "import json; print(json.load(open('${CONFIG_DIR}/config.json')).get('mac', '00:80:E1:22:EE:F2'))" 2>/dev/null || echo "00:80:E1:22:EE:F2")
        fi
        cat > "${CONFIG_DIR}/daemon.env" <<EOF
# CoopDoor Daemon Environment Configuration
# Edit this file to change your BLE device settings
COOPDOOR_MAC=${mac_addr}
COOPDOOR_ADAPTER=hci0
COOPDOOR_TIMEOUT=15
EOF
    fi
    
    chown -R "${APP_USER}:${APP_USER}" "${CONFIG_DIR}"
    chown -R "${APP_USER}:${APP_USER}" "${BACKUP_DIR}"
    chmod 755 "${CONFIG_DIR}"
    chmod 755 "${BACKUP_DIR}"
}

setup_sudoers() {
    log "Configuring sudoers for schedule management"
    
    # Install sudoers file to allow coop user to manage schedule service
    install -m 0440 "${INSTALLER_DIR}/config/coopdoor-apply-sudoers" /etc/sudoers.d/coopdoor-apply
    
    # Validate sudoers syntax
    if ! visudo -c -f /etc/sudoers.d/coopdoor-apply; then
        error "Sudoers file validation failed"
    fi
}


print_success() {
    cat <<EOF

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ✓ CoopDoor Installation Complete!                          ║
║     (Improved Architecture with Persistent Connection)       ║
║     ⭐ Now with Reliable Persistent Timers!                  ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

Next Steps:

1. Check daemon is connected (must be within BLE range!):
   sudo systemctl status coopdoor-daemon
   sudo journalctl -u coopdoor-daemon -n 20
   
   Look for: "[TIMESTAMP] conn: CONNECTED"
   If stuck on "scanning...", move closer to your BLE device!
   
2. Configure your device if needed:
   sudo nano ${CONFIG_DIR}/daemon.env
   (Change COOPDOOR_MAC to your door's MAC address)
   Then restart daemon: sudo systemctl restart coopdoor-daemon
   
3. Test the API:
   curl http://localhost:8080/status
   Should show: {"connected": true, "door_state": {...}, ...}
   
4. Access the web interface:
   http://$(hostname -I | awk '{print $1}'):8080
   Door status will appear in the dashboard!
   
5. Set your automation schedule:
   sudo nano ${CONFIG_DIR}/automation.json

Services installed:
  ✓ coopdoor-daemon    - Persistent BLE connection (24/7)
  ✓ coopdoor-api       - Web API and dashboard  
  ✓ schedule timer     - Daily automation with PERSISTENT timers
  ✓ safety backup      - 9 PM door close failsafe (systemd timer)

🆕 Scheduling Improvements:
  ✓ Persistent systemd timers (survive reboots!)
  ✓ Complete audit trail in logs
  ✓ Safety backup closes door at 9 PM

Monitoring & Logs:
  sudo journalctl -u coopdoor-daemon -f      (live daemon logs)
  sudo journalctl -u coopdoor-api -f         (live API logs)
  tail -f /var/log/coopdoor/schedule.log     (scheduler logs)
  cat /var/lib/coopdoor/schedule_state.json  (current schedule)

Verify Persistent Timers:
  systemctl list-timers | grep coopdoor      (should show open/close timers)
  ls /etc/systemd/system/coopdoor-*.timer    (timer files on disk)

Troubleshooting:
  - Daemon won't connect? Check device is powered and in range
  - Device already connected? Close any phone apps
  - API shows disconnected? Check daemon logs with journalctl
  - Battery not showing? See /opt/coopdoor/docs/ for details
  - Door didn't close? Check /var/log/coopdoor/schedule.log

Configuration files:
  ${CONFIG_DIR}/daemon.env          - Daemon settings (MAC address, adapter)
  ${CONFIG_DIR}/config.json         - Device settings (pulses, intervals)
  ${CONFIG_DIR}/automation.json     - Schedule settings
  ${CONFIG_DIR}/door_state.json     - Current door state

EOF

    # Prompt for optional Tailscale setup
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "Optional: Remote Access Setup"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "Would you like to set up Tailscale for secure remote access?"
    echo "This enables HTTPS access from anywhere without port forwarding."
    echo ""
    echo "What it does:"
    echo "  ✓ Install Tailscale (secure VPN)"
    echo "  ✓ Set up HTTPS with automatic certificates"
    echo "  ✓ Access via https://coop.your-tailnet.ts.net (no port number!)"
    echo "  ✓ Connect from phone, tablet, computer"
    echo ""
    echo "Note: Requires interactive authentication (you'll need to open a URL)"
    echo ""
    read -p "Set up Tailscale now? (y/N): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Starting Tailscale setup..."
        if [[ -f "${INSTALLER_DIR}/setup-tailscale.sh" ]]; then
            bash "${INSTALLER_DIR}/setup-tailscale.sh"
        else
            log "Warning: setup-tailscale.sh not found, skipping"
            echo "You can set up Tailscale manually later with:"
            echo "  curl -fsSL https://tailscale.com/install.sh | sh"
            echo "  sudo tailscale up"
            echo "  sudo tailscale serve --bg 8080"
        fi
    else
        log "Skipping Tailscale setup"
        echo ""
        echo "You can set up Tailscale later by running:"
        echo "  sudo ${INSTALLER_DIR}/setup-tailscale.sh"
        echo ""
        echo "Or manually:"
        echo "  curl -fsSL https://tailscale.com/install.sh | sh"
        echo "  sudo tailscale up"
        echo "  sudo tailscale serve --bg 8080"
        echo ""
    fi
}

verify_installation() {
    log "Verifying installation..."
    
    # Check state directory permissions
    if [[ -d "/var/lib/coopdoor" ]]; then
        local owner=$(stat -c '%U' /var/lib/coopdoor 2>/dev/null || stat -f '%Su' /var/lib/coopdoor 2>/dev/null)
        if [[ "$owner" == "${APP_USER}" ]]; then
            log "✓ State directory owned by ${APP_USER}"
        else
            log "⚠  Warning: State directory not owned by ${APP_USER}, fixing..."
            chown -R "${APP_USER}:${APP_USER}" /var/lib/coopdoor
        fi
    fi
    
    # Check services exist
    if systemctl list-unit-files | grep -q "coopdoor-daemon.service"; then
        log "✓ Services installed"
    else
        log "⚠  Warning: Services may not be installed correctly"
    fi
}

main() {
    log "Starting CoopDoor installation (v3.5.3 - Watchdog Removed)"
    
    check_root
    check_dependencies
    create_app_user
    install_app_files
    setup_venv
    setup_config
    setup_sudoers
    install_systemd_services
    verify_installation
    
    print_success
}

main "$@"
