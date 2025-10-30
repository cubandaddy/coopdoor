# 🐔 CoopDoor - Automatic Chicken Coop Door Controller

[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Compatible-red)](https://www.raspberrypi.org/)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**Automated, scheduled control for Bluetooth Low Energy (BLE) chicken coop doors**

CoopDoor is a Raspberry Pi-based automation system that controls BLE-enabled chicken coop door openers. Set your chickens' schedule once, and the door opens and closes automatically every day—no more rushing home before sunset or waking up early to let them out!

## 🌟 Key Features

- 🌅 **Automatic Sunrise/Sunset Scheduling** - Door opens at dawn, closes at dusk with seasonal adjustments
- ⏰ **Fixed Time Scheduling** - Set specific times like 7:00 AM / 8:30 PM
- 🎛️ **Manual Control** - Open/close via web interface or command line
- 📱 **Progressive Web App (PWA)** - Control from phone, tablet, or computer
- 📊 **Real-time Status Monitoring** - Connection status, last operation, and schedule tracking
- 🔧 **Flexible Configuration** - Partial opening percentages, timezone support, offset adjustments
- 🔄 **Auto-reconnection** - Maintains reliable BLE connection with automatic recovery
- 📦 **DRY Architecture** - Modular design with separate components for easy maintenance

## 📋 Table of Contents

- [Why CoopDoor?](#-why-coopdoor)
- [System Architecture](#-system-architecture)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Configuration](#%EF%B8%8F-configuration)
- [Usage](#-usage)
- [Web Interface](#-web-interface)
- [Command Line Interface](#-command-line-interface)
- [API Reference](#-api-reference)
- [Scheduling Examples](#-scheduling-examples)
- [Project Structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)
- [Management Scripts](#-management-scripts)
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
│ - Scheduler     │                        │  - Battery       │
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
| **Scheduler** | `schedule_apply.py` | Calculates daily times, manages systemd timers |
| **CLI Tool** | `coopctl.py` | Command-line interface for manual control and diagnostics |

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
# Edit the configuration file
sudo nano /etc/coopdoor/config.json

# Update the MAC address to match your door:
{
  "mac": "00:80:E1:22:EE:F2",  # <- Change this to YOUR door's MAC
  "adapter": "hci0",
  "connect_timeout": 15,
  "base_pulses": 14,
  "pulse_interval": 2.0
}

# Restart the API
sudo systemctl restart coopdoor-api
```

### Step 4: Access the Web Interface

Open your browser and navigate to:
```
http://[your-pi-ip]:8080
```

## ⚙️ Configuration

### Device Configuration (`/etc/coopdoor/config.json`)

```json
{
  "mac": "00:80:E1:22:EE:F2",      // BLE MAC address of your door
  "adapter": "hci0",                // Bluetooth adapter (usually hci0)
  "connect_timeout": 15,            // Connection timeout in seconds
  "base_pulses": 14,                // Number of pulses for 100% open
  "pulse_interval": 2.0,            // Seconds between pulses
  "home_before_open": false,        // Close before opening (calibration)
  "min_pause_after_action": 1.0     // Pause after operations (seconds)
}
```

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
| "Connection timeout" | 1. Check door has power<br>2. Verify MAC address<br>3. Move Pi closer to door |
| "Permission denied" | Run commands with `sudo` or check file ownership |
| "Schedule not working" | Check timer is enabled: `systemctl enable coopdoor-apply-schedule.timer` |
| "Web UI not loading" | Verify API is running: `systemctl status coopdoor-api` |
| "Door not responding" | 1. Check battery level<br>2. Verify BLE connection<br>3. Try manual control |

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
