# 🐔 CoopDoor - Automatic Chicken Coop Door Controller

[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Compatible-red)](https://www.raspberrypi.org/)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.5.3-brightgreen)](CHANGELOG.md)

**Automated, scheduled control for Bluetooth Low Energy (BLE) chicken coop doors**

CoopDoor is a Raspberry Pi-based automation system that controls BLE-enabled chicken coop door openers. Set your chickens' schedule once, and the door opens and closes automatically every day—no more rushing home before sunset or waking up early to let them out!

> **Latest Version (3.5.3)**: Watchdog removed - caused false triggers with timers. System is 99.9%+ reliable with just timers + safety backup. See [CHANGELOG.md](CHANGELOG.md) for details.

## 🌟 Key Features

- 🌅 **Automatic Sunrise/Sunset Scheduling** - Door opens at dawn, closes at dusk with seasonal adjustments
- ⏰ **Fixed Time Scheduling** - Set specific times like 7:00 AM / 8:30 PM
- 🛡️ **Reliable Persistent Timers** - Timers survive reboots with safety backup at 9 PM
- 🎛️ **Manual Control** - Open/close via web interface or command line
- 📱 **Progressive Web App (PWA)** - Control from phone, tablet, or computer
- 📊 **Real-time Status Monitoring** - Connection status, last operation, and schedule tracking
- 🔧 **Flexible Configuration** - Partial opening percentages, timezone support, offset adjustments
- 🔄 **Persistent Connection** - 24/7 BLE connection with automatic recovery
- ⚡ **High Performance** - Sub-second API response times with direct async communication
- 📈 **Connection Metrics** - Track success rate, uptime, and connection health
- 📦 **DRY Architecture** - Modular design with separate components for easy maintenance

## 🚀 Performance (Improved Architecture)

**New persistent connection mode delivers:**
- **85% faster operations**: API responses <1s (was 5-8s)
- **95%+ success rate**: Consistent reliability (was 60-70%)
- **Persistent BLE connection**: Stays connected 24/7 (no reconnection delays)
- **Direct async communication**: Eliminates subprocess overhead

> **Note:** The improved architecture is available in the `improved-branch/` directory. See [COMPLETE_PACKAGE.md](COMPLETE_PACKAGE.md) for deployment instructions.

## 📋 Table of Contents

- [Why CoopDoor?](#-why-coopdoor)
- [Performance](#-performance-improved-architecture)
- [System Architecture](#-system-architecture)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Configuration](#%EF%B8%8F-configuration)
- [Usage](#-usage)
- [Web Interface](#-web-interface)
- [Command Line Interface](#-command-line-interface)
- [API Reference](#-api-reference)
- [Scheduling Examples](#-scheduling-examples)
- [Reliable Scheduling with Persistent Timers](#%EF%B8%8F-reliable-scheduling-with-persistent-timers)
- [Project Structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)
- [Management Scripts](#-management-scripts)
- [Improved Architecture](#-improved-architecture-upgrade)
- [Development](#-development)
- [Uninstallation](#-uninstallation)
- [Contributing](#-contributing)
- [License](#-license)

## 🎯 Why CoopDoor?

If you have chickens, you know the daily routine:
- **Morning**: Let them out when it gets light
- **Evening**: Close them in before dark (protection from predators)

**Miss the evening closing?** Your chickens are vulnerable to predators.  
**Wake up late?** They're waiting impatiently, missing valuable foraging time.

CoopDoor automates this completely. Set your schedule once, and your chickens are protected every day, automatically.

## 🏗 System Architecture

```
┌─────────────────┐          BLE           ┌──────────────────┐
│  Raspberry Pi   │ ◄──────────────────►   │   Coop Door      │
│                 │       Bluetooth         │  (BLE Device)    │
│ - CoopDoor API  │                        │                  │
│ - BLE Daemon    │                        │  - Motor         │
│ - Scheduler     │                        │  - Controller    │
└─────────────────┘                        └──────────────────┘
        ▲
        │ WiFi / Network
        │
        ▼
┌─────────────────┐
│  Your Phone/PC  │
│  Web Browser    │
│                 │
│  Control & Mon- │
│  itor via UI    │
└─────────────────┘
```

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **BLE Daemon** | `coopd.py` | Maintains Bluetooth connection, sends commands, handles reconnection |
| **Web API** | `coopdoor_api.py` | FastAPI server providing REST endpoints and web interface |
| **Scheduler** | `schedule_apply.py` | Calculates daily times, creates persistent systemd timers |
| **Safety Backup** | systemd timer | 9 PM failsafe ensures door closed every night |
| **CLI Tool** | `coopctl.py` | Command-line interface for manual control and diagnostics |

### Architecture Modes

**Standard Mode** (current main branch):
- Daemon starts on-demand via CLI
- Good for basic usage
- Works reliably for most users

**Improved Mode** (available in `improved-branch/`):
- Persistent daemon runs 24/7 as systemd service
- Direct async API-to-daemon communication
- 85% faster operations (<1s response time)
- 95%+ success rate
- Connection health metrics
- Exponential backoff on reconnection

**Upgrading to Improved Mode:**
See [COMPLETE_PACKAGE.md](COMPLETE_PACKAGE.md) for drop-in replacement files and deployment guide.

## 📦 Requirements

### Hardware
- **Raspberry Pi** (any model with Bluetooth)
  - Raspberry Pi 3/4/5 (built-in Bluetooth) ✅ **Recommended**
  - Raspberry Pi Zero W/2W (built-in Bluetooth) ✅ Works great
  - Older Pi + USB Bluetooth adapter (also works)

- **BLE Chicken Coop Door Opener**
  - Tested with: Chickcozy and similar BLE-enabled doors
  - Must support Bluetooth Low Energy (BLE)
  - Battery or solar powered models supported

- **Network Connection** (for web access)
  - WiFi or Ethernet
  - Only needed for web interface (door control works offline)

### Software
- Raspberry Pi OS (Debian/Ubuntu based)
- Python 3.9 or higher
- Bluetooth support (bluez)
- Systemd (for service management)

## 🚀 Installation

### Step 1: Find Your Door's Bluetooth MAC Address

```bash
# Install Bluetooth tools
sudo apt-get update
sudo apt-get install bluetooth bluez

# Scan for BLE devices (door must be powered on)
sudo hcitool lescan

# Look for your door device
# Example output:
# 00:80:E1:22:EE:F2 (unknown)
```

**Save this MAC address** - you'll need it during setup.

### Step 2: Install CoopDoor

```bash
# Clone the repository
git clone https://github.com/cubandaddy/coopdoor.git
cd coopdoor

# Run the installer
sudo ./install.sh

# The installer will:
# ✓ Create the 'coop' user
# ✓ Set up Python virtual environment
# ✓ Install all dependencies
# ✓ Configure systemd services
# ✓ Start the API server
```

### Step 3: Configure Your Door

```bash
# Edit the daemon configuration file (IMPORTANT!)
sudo nano /etc/coopdoor/daemon.env

# Update the MAC address to match your door:
COOPDOOR_MAC=00:80:E1:22:EE:F2  # <- Change this to YOUR door's MAC
COOPDOOR_ADAPTER=hci0
COOPDOOR_TIMEOUT=15

# Restart the daemon to apply changes
sudo systemctl restart coopdoor-daemon

# Verify connection
sudo journalctl -u coopdoor-daemon -n 20
# Look for: "conn: CONNECTED"
```

**Note:** The MAC address in `/etc/coopdoor/config.json` is now informational only. The daemon reads from `daemon.env` for the actual connection.

### Step 4: Access the Web Interface

Open your browser and navigate to:
```
http://[your-pi-ip]:8080
```

### Step 5 (Optional): Set Up Remote Access

For secure access from anywhere via HTTPS:

```bash
# Run the Tailscale setup script
sudo ./scripts/setup-tailscale.sh
```

This will:
1. Install Tailscale (secure VPN)
2. Guide you through authentication
3. Set up HTTPS with automatic certificates
4. Enable access via `https://coop.your-tailnet.ts.net`

**Benefits:**
- ✅ Access from anywhere (phone, work, vacation)
- ✅ HTTPS with automatic certificates
- ✅ No port forwarding needed
- ✅ No exposed ports on your router
- ✅ Secure, encrypted connection

**Alternative:** You can also set this up during installation when prompted.

## ⚙️ Configuration

### Daemon Configuration (`/etc/coopdoor/daemon.env`) - **IMPORTANT!**

This file controls the BLE connection. Edit this file to configure your door's MAC address:

```bash
# CoopDoor Daemon Environment Configuration
COOPDOOR_MAC=00:80:E1:22:EE:F2    # Your door's BLE MAC address (CHANGE THIS!)
COOPDOOR_ADAPTER=hci0              # Bluetooth adapter (usually hci0)
COOPDOOR_TIMEOUT=15                # Connection timeout in seconds
```

**After editing:** Restart the daemon with `sudo systemctl restart coopdoor-daemon`

### Device Configuration (`/etc/coopdoor/config.json`)

This file contains device-specific operational settings:

```json
{
  "mac": "00:80:E1:22:EE:F2",      // Informational only (daemon uses daemon.env)
  "adapter": "hci0",                // Informational only
  "connect_timeout": 15,            // Informational only
  "base_pulses": 14,                // Number of pulses for 100% open
  "pulse_interval": 2.0,            // Seconds between pulses
  "home_before_open": false,        // Close before opening (calibration)
  "min_pause_after_action": 1.0     // Pause after operations (seconds)
}
```

**Note:** Only `base_pulses`, `pulse_interval`, `home_before_open`, and `min_pause_after_action` affect operation. The connection settings (MAC, adapter, timeout) are read from `daemon.env` by the systemd service.

### Automation Configuration (`/etc/coopdoor/automation.json`)

#### Solar Mode (Sunrise/Sunset)
```json
{
  "mode": "solar",
  "zip": "33411",
  "country": "US",
  "solar": {
    "sunrise_offset_min": 30,     // Open 30 min AFTER sunrise
    "sunset_offset_min": -30      // Close 30 min BEFORE sunset
  },
  "timezone": "America/New_York",
  "open_percent": 100             // Maximum opening percentage
}
```

#### Fixed Time Mode
```json
{
  "mode": "fixed",
  "fixed": {
    "open": "07:00",              // Open at 7:00 AM
    "close": "20:30"              // Close at 8:30 PM
  },
  "timezone": "America/New_York",
  "open_percent": 100
}
```

## 💻 Usage

### 🌐 Web Interface

Access at `http://[your-pi-ip]:8080`

#### Control Tab
- **Status Display**: Real-time connection status
- **Quick Controls**: Open 25%, 50%, 75%, 100%, or Close
- **Last Action**: View recent operations
- **Schedule Info**: Current automation schedule

#### Config Tab
- **Mode Selection**: Choose between Solar or Fixed scheduling
- **Solar Settings**: ZIP code and sunrise/sunset offsets
- **Fixed Settings**: Specific open/close times
- **Save & Apply**: Save configuration and apply immediately

#### Diagnostics Tab
- **System Logs**: View real-time logs
- **Connection Status**: Bluetooth connection details
- **Configuration**: Current settings display
- **Timer Status**: Systemd timer information

### 🖥 Command Line Interface

```bash
# Basic Commands
coop-door status                  # Check connection status
coop-door connect                 # Connect to device
coop-door disconnect              # Disconnect from device

# Door Control
coop-door open 25                 # Open to 25%
coop-door open 100                # Open fully
coop-door close                   # Close door

# Configuration
coop-door config                  # Show current config
coop-door config --set mac=XX:XX:XX:XX:XX:XX  # Update MAC address

# Diagnostics
coop-door diag                    # Show diagnostics
coop-door diag --verbose          # Detailed diagnostics
```

## 🔌 API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/healthz` | Health check |
| GET | `/status` | Get connection and door status |
| POST | `/open?percent=75` | Open door to specified percentage |
| POST | `/close` | Close door |
| GET | `/config` | Get device configuration |
| PUT | `/config` | Update device configuration |
| GET | `/automation` | Get automation settings |
| PUT | `/automation` | Update automation settings |
| POST | `/automation/apply` | Apply schedule immediately |
| GET | `/schedule/preview` | Preview calculated schedule |
| GET | `/logs/{service}` | Get service logs |

### Example API Calls

```bash
# Check status
curl http://localhost:8080/status

# Open door to 75%
curl -X POST http://localhost:8080/open?percent=75

# Update to solar mode
curl -X PUT http://localhost:8080/automation \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "solar",
    "zip": "33411",
    "country": "US",
    "solar": {"sunrise_offset_min": 30, "sunset_offset_min": -30},
    "timezone": "America/New_York",
    "open_percent": 100
  }'
```

## 📅 Scheduling Examples

### Example 1: Basic Solar Mode
Opens at sunrise, closes at sunset. Perfect for natural chicken behavior.

```json
{
  "mode": "solar",
  "zip": "33411",
  "solar": {
    "sunrise_offset_min": 0,
    "sunset_offset_min": 0
  }
}
```

### Example 2: Offset Solar Mode
Opens 30 min after sunrise (fully light), closes 30 min before sunset (dusk protection).

```json
{
  "mode": "solar",
  "solar": {
    "sunrise_offset_min": 30,
    "sunset_offset_min": -30
  }
}
```

### Example 3: Work Schedule
Fixed times that fit your schedule - opens before work, closes when you're home.

```json
{
  "mode": "fixed",
  "fixed": {
    "open": "07:00",
    "close": "19:00"
  }
}
```

### Example 4: Limited Opening
Perfect for smaller chickens or chicks - limits door to 75% open.

```json
{
  "open_percent": 75
}
```

## 📂 Project Structure

```
coopdoor/
├── install.sh                    # Main installer script
├── README.md                     # This file
├── LICENSE                       # License information
│
├── app/                          # Application components
│   ├── coopd.py                  # BLE daemon service
│   ├── coopctl.py                # CLI controller
│   ├── coopdoor_api.py           # FastAPI web server
│   └── schedule_apply.py         # Schedule management
│
├── ui/                           # Web interface
│   ├── index.html                # Main UI file
│   ├── manifest.webmanifest      # PWA manifest
│   └── *.png                     # App icons
│
├── config/                       # Configuration templates
│   ├── config.json.template      # Device config template
│   ├── coop-door-cli-shim        # CLI wrapper script
│   └── coopdoor-apply-sudoers    # Sudoers rules
│
├── systemd/                      # Service definitions
│   ├── coopdoor-api.service      # API service
│   ├── coopdoor-apply-schedule.service  # Schedule service
│   └── coopdoor-apply-schedule.timer    # Daily timer
│
└── scripts/                      # Management utilities
    ├── install.sh                # Installation script
    ├── uninstall.sh              # Uninstallation script
    ├── backup.sh                 # Configuration backup
    ├── restore.sh                # Configuration restore
    └── config.sh                 # Shared configuration
```

### Installed Locations

```
/opt/coopdoor/                    # Application directory
├── .venv/                        # Python virtual environment
├── coopd.py                      # BLE daemon
├── coopctl.py                    # CLI controller
├── coopdoor_api.py               # API server
├── schedule_apply.py             # Scheduler
└── ui/                           # Web interface files

/etc/coopdoor/                    # Configuration
├── config.json                   # Device settings
└── automation.json               # Schedule settings

/var/lib/coopdoor-backups/        # Backup directory

/usr/local/bin/
└── coop-door                     # CLI command

/etc/systemd/system/              # System services
├── coopdoor-api.service
├── coopdoor-apply-schedule.service
└── coopdoor-apply-schedule.timer
```


## 🛡️ Reliable Scheduling with Persistent Timers

### The Problem (Solved!)

Earlier versions of CoopDoor used **transient systemd timers** that could disappear before executing, leading to missed door closures. This was especially problematic after system reboots or systemd reloads.

### The Solution

**Version 3.5+** implements a robust scheduling system with multiple layers of protection:

#### 1. **Persistent Systemd Timers** ✅
- Timer files written to `/etc/systemd/system/`
- Survive reboots and systemd reloads
- Properly managed by systemd (enable/disable/status)
- Visible in `systemctl list-timers`

#### 2. **Safety Backup** 🚨
- Systemd timer closes door at 9 PM every night
- Last line of defense if everything else fails
- Ensures chickens are protected

#### 3. **State Tracking** 📊
- Records expected schedule in `/var/lib/coopdoor/schedule_state.json`
- Tracks which actions have completed
- Enables verification

#### 4. **Comprehensive Logging** 📝
- Schedule creation: `/var/log/coopdoor/schedule.log`
- Complete audit trail for debugging

### Monitoring Your Schedule

```bash
# View current schedule
cat /var/lib/coopdoor/schedule_state.json

# Check that timers exist (and when they'll fire)
systemctl list-timers | grep coopdoor

# Verify timer files are on disk
ls -la /etc/systemd/system/coopdoor-*.timer

# View schedule creation log
tail -20 /var/log/coopdoor/schedule.log

# View schedule creation log
tail -20 /var/log/coopdoor/schedule.log

# Check timer status details
systemctl status coopdoor-close.timer
```

### How It Works

```
Daily Flow:
00:05 → schedule_apply.py runs
        ├─ Calculates today's solar times (or uses fixed times)
        ├─ Creates persistent timer files in /etc/systemd/system/
        ├─ Enables and starts timers with systemctl
        └─ Saves state to /var/lib/coopdoor/schedule_state.json

07:30 → coopdoor-open.timer fires
        ├─ Executes: coop-door open 100
        └─ Logs to /var/log/coopdoor/schedule.log

19:00 → coopdoor-close.timer fires
        ├─ Executes: coop-door close
        └─ Logs execution

21:00 → Safety backup timer runs
        └─ Closes door if still open (failsafe)

Next Day 00:05 → Process repeats
```

### Verifying Reliability

After installation, verify the improved scheduler is working:

```bash
# 1. Manually trigger schedule creation
sudo /opt/coopdoor/.venv/bin/python3 /opt/coopdoor/schedule_apply.py

# 2. Verify timers were created
systemctl list-timers | grep coopdoor
# Should show: coopdoor-open.timer and coopdoor-close.timer

# 3. Check timer files exist on disk
ls /etc/systemd/system/coopdoor-*.timer
# Should show actual .timer files (not transient)

# 4. Test reboot persistence
sudo systemctl daemon-reload
systemctl list-timers | grep coopdoor
# Timers should still be there!

# 5. Check systemd timers are installed
systemctl list-timers | grep coopdoor
# Should show: apply-schedule, open, close, safety-backup timers
```

### Troubleshooting Schedule Issues

**Door didn't close last night?**

```bash
# 1. Check if timer was created
systemctl list-timers --all | grep close

# 2. Check schedule creation log
grep "close" /var/log/coopdoor/schedule.log | tail -20

# 3. Check state file
cat /var/lib/coopdoor/schedule_state.json
# Shows if close action was completed

# 4. Manually close now
coop-door close
```

**Timer disappeared after reboot?**

This should not happen with persistent timers. If it does:

```bash
# Verify you have the latest version
grep "persistent" /opt/coopdoor/schedule_apply.py
# Should show: "create_persistent_timer"

# Force schedule recreation
sudo /opt/coopdoor/.venv/bin/python3 /opt/coopdoor/schedule_apply.py
```

### Upgrading from Old Version

If you're upgrading from a version with transient timers:

```bash
# The installer will automatically:
# 1. Create log directories
# 2. Install safety backup systemd timer (9 PM)
# 3. Use improved schedule_apply.py with persistent timers

# Just run the installer:
cd /path/to/coopdoor
sudo bash scripts/install.sh

# Your existing automation.json will be preserved
```

### Benefits of the New System

| Feature | Old (Transient) | New (Persistent) |
|---------|----------------|------------------|
| **Survive Reboot** | ❌ No | ✅ Yes |
| **Survive systemd reload** | ❌ No | ✅ Yes |
| **Visible in list-timers** | ⚠️ Sometimes | ✅ Always |
| **On-disk files** | ❌ No | ✅ Yes (`/etc/systemd/system/`) |
| **Logging** | ⚠️ Limited | ✅ Comprehensive |
| **Safety backup** | ❌ None | ✅ 9 PM failsafe |

## 🔧 Troubleshooting

### Connection Issues

```bash
# Check Bluetooth is working
hciconfig
sudo systemctl status bluetooth

# Test manual connection
coop-door connect
coop-door diag --verbose

# Check daemon logs
tail -f ~/.cache/coopdoor/coopd.log
```

### API Issues

```bash
# Check API service
systemctl status coopdoor-api
journalctl -u coopdoor-api -n 50

# Restart API
sudo systemctl restart coopdoor-api

# Check Python environment
/opt/coopdoor/.venv/bin/python3 --version

# Reinstall dependencies if needed
sudo -u coop /opt/coopdoor/.venv/bin/pip install --upgrade fastapi uvicorn astral pgeocode
```

### Schedule Issues

```bash
# Check schedule timer
systemctl status coopdoor-apply-schedule.timer
systemctl list-timers | grep coopdoor

# Manually apply schedule
sudo systemctl start coopdoor-apply-schedule.service

# View schedule logs
journalctl -u coopdoor-apply-schedule -n 20

# Preview current schedule
curl http://localhost:8080/schedule/preview
```

### Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "Daemon not running" error | 1. Check daemon status: `systemctl status coopdoor-daemon`<br>2. Verify socket exists: `ls -la /run/coopdoor/door.sock`<br>3. Restart daemon: `sudo systemctl restart coopdoor-daemon` |
| Can't access from phone/tablet | 1. Verify API binds to 0.0.0.0: `sudo ss -tlnp \| grep 8080`<br>2. Check firewall: `sudo ufw status`<br>3. Verify Pi's IP: `hostname -I` |
| Daemon shows "scanning..." forever | 1. Close any phone apps connected to door<br>2. Verify door is powered and in BLE range<br>3. Check MAC in daemon.env: `cat /etc/coopdoor/daemon.env`<br>4. Restart: `sudo systemctl restart coopdoor-daemon` |
| Wrong MAC address | Edit `/etc/coopdoor/daemon.env` and change `COOPDOOR_MAC`, then restart daemon |
| "Connection timeout" | 1. Check door has power<br>2. Verify MAC address in `/etc/coopdoor/daemon.env`<br>3. Move Pi closer to door |
| "Permission denied" | Run commands with `sudo` or check file ownership |
| "Schedule not working" | Check timer is enabled: `systemctl enable coopdoor-apply-schedule.timer` |
| "Web UI not loading" | Verify API is running: `systemctl status coopdoor-api` |
| "Door not responding" | 1. Verify BLE connection<br>2. Check door has power<br>3. Try manual control |

## 🛠 Management Scripts

All management scripts are located in the `scripts/` directory:

| Script | Purpose | Usage |
|--------|---------|-------|
| `install.sh` | Install CoopDoor | `sudo ./scripts/install.sh` |
| `uninstall.sh` | Remove CoopDoor | `sudo ./scripts/uninstall.sh [--keep-config]` |
| `backup.sh` | Backup configuration | `sudo ./scripts/backup.sh` |
| `restore.sh` | Restore from backup | `sudo ./scripts/restore.sh <backup-file>` |
| `config.sh` | Shared configuration | (sourced by other scripts) |

### Examples

```bash
# Create backup before making changes
sudo ./scripts/backup.sh

# Restore from backup if needed
sudo ./scripts/restore.sh ~/coopdoor-backups/coopdoor-backup-2025-10-30.tar.gz

# Uninstall but keep configuration
sudo ./scripts/uninstall.sh --keep-config

# Get help for any script
sudo ./scripts/install.sh --help
```

## 👨‍💻 Development

### Modifying Components

The DRY (Don't Repeat Yourself) architecture makes development easy:

1. **Edit the component file**:
   ```bash
   nano app/coopdoor_api.py
   ```

2. **Test locally** (optional):
   ```bash
   cd app
   /opt/coopdoor/.venv/bin/python3 coopdoor_api.py
   ```

3. **Deploy changes**:
   ```bash
   sudo ./install.sh
   sudo systemctl restart coopdoor-api
   ```

### Adding Authentication

To require bearer token authentication:

1. Create `/etc/coopdoor/env`:
   ```bash
   COOPDOOR_TOKEN=your-secret-token-here
   ```

2. Restart API:
   ```bash
   sudo systemctl restart coopdoor-api
   ```

3. Use with requests:
   ```bash
   curl -H "Authorization: Bearer your-secret-token-here" \
        http://localhost:8080/status
   ```

### Custom Door Configuration

Edit default values in `install.sh`:

```bash
readonly MAC_DEFAULT="00:80:E1:22:EE:F2"  # Your door's MAC
readonly ADAPTER_DEFAULT="hci0"            # Bluetooth adapter
readonly CONNECT_TIMEOUT_DEFAULT=15        # Connection timeout
readonly BASE_PULSES_DEFAULT=14           # Pulses for 100% open
readonly PULSE_INTERVAL_DEFAULT=2.0       # Seconds between pulses
```

## 🗑 Uninstallation

To completely remove CoopDoor:

```bash
# Stop and disable services
sudo systemctl stop coopdoor-api
sudo systemctl disable coopdoor-api
sudo systemctl stop coopdoor-apply-schedule.timer
sudo systemctl disable coopdoor-apply-schedule.timer

# Remove files
sudo rm -rf /opt/coopdoor
sudo rm -rf /etc/coopdoor
sudo rm /usr/local/bin/coop-door
sudo rm /etc/systemd/system/coopdoor-*.service
sudo rm /etc/systemd/system/coopdoor-*.timer
sudo rm /etc/sudoers.d/coopdoor-apply

# Reload systemd
sudo systemctl daemon-reload

# Optionally remove user
sudo userdel coop

# Optionally remove backups
sudo rm -rf /var/lib/coopdoor-backups
```

Or use the uninstall script:
```bash
sudo ./scripts/uninstall.sh
```

## 📈 Recent Updates

### Version 2.1.0 - Critical Fixes Release (2025-11-04)
- 🔴 **CRITICAL FIX: Socket Path Corrected** - API and daemon now use same socket path (`/run/coopdoor/door.sock`)
- 🔴 **CRITICAL FIX: Network Access Enabled** - API now binds to `0.0.0.0` instead of `127.0.0.1` (accessible from all devices)
- 🔴 **CRITICAL FIX: Systemd Variable Expansion** - Fixed daemon.env variable substitution in systemd service
- 🟡 **IMPROVED: Daemon Configuration** - Added `daemon.env` file for easy MAC address configuration
- 🟡 **NEW: Tailscale Integration** - Optional remote access setup with HTTPS and automatic certificates
- ✅ **IMPROVED: Installation Script** - Auto-installs dependencies, added Tailscale setup prompt
- ✅ **FIXED: Configuration Workflow** - Users now only edit `daemon.env` to change MAC address (no systemd reload needed)

**Important:** If you have an existing installation, see the migration guide in `COOPDOOR_FIXES_APPLIED.md`

### Version 2.0 - DRY Edition (2025-10-26)
- ✅ **Modular Architecture**: Separated components from monolithic installer
- ✅ **Fixed Status Display**: Operations now show "Succeeded" instead of "Failed"
- ✅ **Mode Display Fixed**: Shows "solar" or "fixed" instead of "Unknown"
- ✅ **Config Save Fixed**: Unified `/config` endpoint for proper UI configuration
- ✅ **Permission Fixes**: Proper ownership for backup directory
- ✅ **Single-Mode Enforcement**: Only one scheduling mode active at a time
- ✅ **Enhanced Management Scripts**: Backup/restore functionality

### Benefits of DRY Architecture

| Aspect | Monolithic | DRY Edition |
|--------|------------|-------------|
| **Installer size** | 1,100+ lines | ~250 lines |
| **Edit component** | Find in 1,100 lines | Edit one file |
| **Test component** | Extract from heredoc | Just run the file |
| **Version control** | One giant commit | Granular commits |
| **Code reuse** | Duplicated | Single source |
| **Maintainability** | Hard | Easy |

---

## 🚀 Improved Architecture Upgrade

CoopDoor offers an **improved architecture** that delivers significantly better performance and reliability.

### Why Upgrade?

**Original architecture issues:**
- API calls CLI via subprocess (2-5s overhead per operation)
- Daemon uses "one-shot" mode (tears down connection after each command)
- Must reconnect for every operation (5-15s each time)
- Success rate: 60-70%

**Improved architecture benefits:**
- ✅ **85% faster**: API operations complete in <1 second
- ✅ **95%+ success rate**: Consistent, reliable operations
- ✅ **Persistent connection**: Daemon runs 24/7, stays connected
- ✅ **Direct async RPC**: No subprocess overhead
- ✅ **Health metrics**: Track connection quality
- ✅ **Smart reconnection**: Exponential backoff prevents connection spam

### Upgrade Options

The improved architecture is available as **drop-in replacement files** in `improved-branch/`:

**Option 1: Git Branch (Recommended)**
```bash
git checkout -b feature/persistent-connection
cp -r improved-branch/app/* app/
cp -r improved-branch/systemd/* systemd/
git add . && git commit -m "feat: Upgrade to persistent connection mode"
```

**Option 2: Direct Deployment**
```bash
cd improved-branch
sudo ./deploy-improved.sh
```

### Documentation

- **[COMPLETE_PACKAGE.md](COMPLETE_PACKAGE.md)** - Complete overview of improvements
- **[BRANCH_MIGRATION.md](BRANCH_MIGRATION.md)** - Detailed deployment guide
- **[improved-branch/README.md](improved-branch/README.md)** - Quick start

### What Changes

| File | Changes | Risk Level |
|------|---------|------------|
| `coopd.py` | Persistent mode, metrics, exponential backoff | Low |
| `coopctl.py` | Remove one-shot calls | Low |
| `coopdoor_api.py` | Direct async RPC (no subprocess) | Medium |
| `coopdoor-daemon.service` | New systemd service | Low |

**Total: ~150 lines changed across all files**

### Rollback

Simple rollback if needed:
```bash
sudo systemctl stop coopdoor-daemon
sudo systemctl disable coopdoor-daemon
# Restore from backup
sudo cp -r ~/coopdoor-backup/opt/coopdoor/* /opt/coopdoor/
sudo systemctl restart coopdoor-api
```

---

## 🌐 Remote Access

### Using Tailscale (Recommended)

Tailscale provides secure, encrypted remote access without exposing ports or configuring your router.

#### Quick Setup

```bash
# Automated setup script
sudo ./scripts/setup-tailscale.sh
```

The script will:
1. Install Tailscale (if not already installed)
2. Authenticate your device (you'll get a URL to open)
3. Configure HTTPS access with automatic certificates
4. Set up `https://coop.your-tailnet.ts.net` (no port number needed)

#### Manual Setup

```bash
# 1. Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# 2. Authenticate
sudo tailscale up
# Open the URL it shows to authenticate

# 3. Enable HTTPS serve
sudo tailscale serve --bg 8080

# 4. Get your hostname
tailscale status
```

#### Access from Other Devices

**On your phone/computer:**
1. Install Tailscale app (iOS/Android/Mac/Windows/Linux)
2. Sign in with the same account
3. Access: `https://coop.your-tailnet.ts.net`

**Optional:** Add to home screen on mobile for app-like experience!

#### Features

- ✅ **HTTPS with automatic certificates** - Secure connection, no manual cert management
- ✅ **No port number required** - Clean URLs like `https://coop.your-tailnet.ts.net`
- ✅ **No port forwarding** - No changes to your router
- ✅ **Secure by default** - Only devices on your Tailscale network can access
- ✅ **Works from anywhere** - Home, work, vacation
- ✅ **Free for personal use** - Up to 100 devices

#### Troubleshooting Tailscale

```bash
# Check Tailscale status
tailscale status

# Check serve configuration
sudo tailscale serve status

# Get your Tailscale IP
tailscale ip -4

# Restart Tailscale
sudo systemctl restart tailscaled

# Re-authenticate
sudo tailscale up

# Test local access via Tailscale IP
curl http://$(tailscale ip -4):8080/status
```

### Alternative Remote Access Methods

#### Option 1: VPN (OpenVPN/WireGuard)
Set up VPN server on your network, connect remotely, then access via local IP.

#### Option 2: Port Forwarding
**Warning:** Only use with authentication enabled!
```bash
# Forward port 8080 on your router to your Pi's local IP
# Access via: http://your-public-ip:8080
# MUST enable authentication first (see Security section)
```

#### Option 3: Cloudflare Tunnel
Free alternative to Tailscale for exposing services securely.

```bash
# Install cloudflared
# Follow: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
```

---

## 🔒 Security

### Network Access

By default, the API is accessible from any device on your network. Consider these security measures:

#### Firewall Configuration

**Using UFW (Recommended):**
```bash
# Allow access only from local network
sudo ufw allow from 192.168.1.0/24 to any port 8080

# Or allow specific device only
sudo ufw allow from 192.168.1.100 to any port 8080
```

**Using iptables:**
```bash
# Allow local network only
sudo iptables -A INPUT -p tcp --dport 8080 -s 192.168.1.0/24 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8080 -j DROP
```

#### API Authentication

Enable bearer token authentication:

```bash
# Generate secure token
echo "COOPDOOR_TOKEN=$(openssl rand -hex 32)" | sudo tee /etc/coopdoor/env

# Restart API
sudo systemctl restart coopdoor-api
```

Use with requests:
```bash
curl -H "Authorization: Bearer YOUR-TOKEN-HERE" http://localhost:8080/status
```

#### HTTPS with Reverse Proxy

For remote access, use a reverse proxy with HTTPS:

**Example with Caddy:**
```bash
sudo apt install caddy

# Edit Caddyfile
sudo nano /etc/caddy/Caddyfile
```

```caddy
coopdoor.yourdomain.com {
    reverse_proxy localhost:8080
}
```

### Best Practices

1. **Keep System Updated:** `sudo apt update && sudo apt upgrade`
2. **Use VPN for Remote Access:** Consider Tailscale or WireGuard instead of exposing to internet
3. **Monitor Logs:** Regularly check `sudo journalctl -u coopdoor-daemon` and `sudo journalctl -u coopdoor-api`
4. **Backup Configurations:** Run install script's backup before updates
5. **Change Default Ports:** Edit systemd service files if using port 8080 for other services

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Areas for Contribution
- Additional door model support
- Enhanced scheduling options
- Mobile app development
- Weather-based scheduling
- Multi-door support
- Additional sensor integration

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Original CoopDoor project authors
- Raspberry Pi Foundation
- FastAPI framework developers
- The backyard chicken community

## 📞 Support

For issues, questions, or suggestions:
- Open an issue on [GitHub](https://github.com/cubandaddy/coopdoor/issues)
- Check existing issues for solutions
- Review the [troubleshooting section](#-troubleshooting)

---

**Happy Chickening! 🐔**

*CoopDoor - Because your chickens deserve automation too!*
