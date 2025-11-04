#!/usr/bin/env bash
set -euo pipefail

# CoopDoor Tailscale Setup Script
# Sets up secure remote access via Tailscale

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

install_tailscale() {
    log "Installing Tailscale"
    
    # Check if already installed
    if command -v tailscale >/dev/null 2>&1; then
        log "Tailscale is already installed"
        tailscale version
        return 0
    fi
    
    # Install Tailscale
    log "Downloading and installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
    
    log "✓ Tailscale installed successfully"
}

authenticate_tailscale() {
    log "Authenticating Tailscale"
    
    # Check if already authenticated
    if tailscale status >/dev/null 2>&1; then
        log "Tailscale is already authenticated"
        tailscale status | head -3
        return 0
    fi
    
    cat <<EOF

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   Tailscale Authentication Required                          ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

The next command will display a URL. You need to:
1. Open the URL in a browser
2. Sign in to your Tailscale account
3. Approve this device

Press ENTER when ready...
EOF
    read -r
    
    # Start Tailscale and show auth URL
    log "Starting Tailscale authentication..."
    tailscale up
    
    # Wait for authentication
    log "Waiting for authentication..."
    local max_wait=300  # 5 minutes
    local waited=0
    while [[ $waited -lt $max_wait ]]; do
        if tailscale status >/dev/null 2>&1; then
            log "✓ Tailscale authenticated successfully!"
            break
        fi
        sleep 5
        waited=$((waited + 5))
    done
    
    if [[ $waited -ge $max_wait ]]; then
        error "Authentication timeout. Please run 'sudo tailscale up' manually."
    fi
}

setup_tailscale_serve() {
    log "Setting up Tailscale Serve (HTTPS access)"
    
    # Get Tailscale hostname
    local ts_hostname=$(tailscale status --json 2>/dev/null | grep -o '"DNSName":"[^"]*"' | cut -d'"' -f4 | head -1 | sed 's/\.$//')
    
    if [[ -z "$ts_hostname" ]]; then
        log "Warning: Could not determine Tailscale hostname"
        ts_hostname="<your-hostname>.ts.net"
    fi
    
    cat <<EOF

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   Setting up HTTPS access                                    ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

This will configure Tailscale to serve your CoopDoor interface via HTTPS
without requiring a port number.

EOF
    
    # Set up tailscale serve
    log "Configuring Tailscale serve..."
    tailscale serve --bg 8080
    
    # Verify it's running
    log "Verifying configuration..."
    sleep 2
    tailscale serve status
    
    log "✓ Tailscale serve configured successfully!"
    
    cat <<EOF

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ✓ Tailscale Setup Complete!                               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

Access your CoopDoor from anywhere via:
  https://${ts_hostname}

Features enabled:
  ✓ HTTPS with automatic certificates
  ✓ No port number needed
  ✓ Secure access from any device on your Tailscale network
  ✓ Access from phone, tablet, laptop

Next steps:
1. Install Tailscale on your phone/computer:
   - iOS: App Store → Search "Tailscale"
   - Android: Play Store → Search "Tailscale"
   - Mac/Windows/Linux: https://tailscale.com/download

2. Sign in with the same account

3. Access your coop:
   https://${ts_hostname}

4. Optional: Add to home screen on phone for app-like experience

Troubleshooting:
  - Check Tailscale status: tailscale status
  - View serve config: sudo tailscale serve status
  - Check CoopDoor logs: sudo journalctl -u coopdoor-api -n 20

EOF
}

verify_coopdoor_running() {
    log "Verifying CoopDoor is running"
    
    if ! systemctl is-active --quiet coopdoor-api; then
        error "CoopDoor API is not running. Install CoopDoor first with: sudo ./scripts/install.sh"
    fi
    
    if ! curl -s http://localhost:8080/status >/dev/null 2>&1; then
        error "CoopDoor API is not responding. Check: sudo systemctl status coopdoor-api"
    fi
    
    log "✓ CoopDoor is running"
}

main() {
    cat <<EOF

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   CoopDoor Tailscale Setup                                   ║
║   Secure Remote Access Configuration                         ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

This script will:
1. Install Tailscale (if not already installed)
2. Authenticate your device with Tailscale
3. Configure HTTPS access (no port number needed)

EOF
    
    check_root
    verify_coopdoor_running
    install_tailscale
    authenticate_tailscale
    setup_tailscale_serve
    
    log "Setup complete!"
}

main "$@"
