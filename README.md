# CoopDoor v3.3.1

### Fixes in v3.3.1:
- ✅ **Config Save Fixed**: Added unified `/config` endpoint to API for proper UI configuration saving
- ✅ **Permission Fix**: Installer now creates `/var/lib/coopdoor-backups` with proper `coop` user ownership
- ✅ **Multi-section Config**: Supports automation, BLE, and UI settings in a unified structure

### What Was Fixed:
1. **"Save failed: Not Found" error** - The UI was calling `/config` endpoint but API only had `/automation`
2. **Permission denied on backup directory** - API couldn't create backups at startup
3. **Config structure mismatch** - UI expected unified config, API had separate endpoints

All services now run as the `coop` user with proper permissions throughout.

This is the **DRY (Don't Repeat Yourself)** version of the CoopDoor installer. Instead of embedding all code inside the installer script, each component exists as a separate file that the installer copies into place.

## Directory Structure

```
coopdoor-unified/
├── install.sh                          # Main installer script
├── app/                                # Application components
│   ├── coopd.py                       # BLE daemon (connect to door)
│   ├── coopctl.py                     # CLI controller
│   ├── coopdoor_api.py                # FastAPI web server
│   └── schedule_apply.py              # Schedule management
├── ui/                                 # Web interface
│   ├── index.html                     # Main UI
│   ├── *.png                          # App icons
│   └── manifest.webmanifest           # PWA manifest
├── config/                             # Configuration templates
│   ├── config.json.template           # Device config template
│   ├── coop-door-cli-shim             # CLI wrapper script
│   └── coopdoor-apply-sudoers         # Sudoers rule
└── systemd/                            # Systemd service files
    ├── coopdoor-api.service           # API service
    ├── coopdoor-apply-schedule.service # Apply schedule service
    └── coopdoor-apply-schedule.timer   # Daily timer
```

## Why This Is Better (DRY Principles)

### Before (Monolithic Installer):
- **1,100+ lines** of installer script with everything embedded
- Hard to edit individual components
- Duplicate code between installer and running system
- Can't test components independently
- Version control sees one giant file

### After (DRY Components):
- **~250 lines** of installer script (just copies files)
- Each component in its own file
- Easy to edit: change `coopd.py` → done!
- Can test each component separately
- Version control tracks each file individually
- **True single source of truth** for each component

## Installation

### Quick Start

```bash
# Extract the coopdoor-unified directory
cd coopdoor-unified

# Run the installer
sudo ./install.sh
```

That's it! The installer will:
1. Check prerequisites
2. Create the `coop` user if needed
3. Set up Python virtual environment
4. Copy all application files
5. Install systemd services
6. Configure everything
7. Start the services

### What Gets Installed

```
/opt/coopdoor/              # Application directory
├── .venv/                  # Python virtual environment
├── coopd.py                # ← Copied from app/coopd.py
├── coopctl.py              # ← Copied from app/coopctl.py
├── coopdoor_api.py         # ← Copied from app/coopdoor_api.py
├── schedule_apply.py       # ← Copied from app/schedule_apply.py
└── ui/                     # ← Copied from ui/
    ├── index.html
    └── ...

/etc/coopdoor/              # Configuration
├── config.json             # ← Generated from template + defaults
└── automation.json         # Created on first config save

/usr/local/bin/
└── coop-door               # ← Copied from config/coop-door-cli-shim

/etc/systemd/system/        # Services
├── coopdoor-api.service                # ← Copied from systemd/
├── coopdoor-apply-schedule.service     # ← Copied from systemd/
└── coopdoor-apply-schedule.timer       # ← Copied from systemd/

/etc/sudoers.d/
└── coopdoor-apply          # ← Copied from config/coopdoor-apply-sudoers
```

## Customization

### Changing Defaults

Edit the top of `install.sh`:
```bash
readonly MAC_DEFAULT="00:80:E1:22:EE:F2"      # Your BLE MAC address
readonly ADAPTER_DEFAULT="hci0"                # Bluetooth adapter
readonly CONNECT_TIMEOUT_DEFAULT=15            # Connection timeout
readonly BASE_PULSES_DEFAULT=14                # Pulses for 100% open
readonly PULSE_INTERVAL_DEFAULT=2.0            # Seconds between pulses
```

### Modifying Components

Want to change how the daemon works?
1. Edit `app/coopd.py`
2. Run `sudo ./install.sh` again
3. Done! New version copied to `/opt/coopdoor/`

Want to change the UI?
1. Edit `ui/index.html`
2. Run `sudo ./install.sh` again
3. Refresh browser!

### Testing Components

Since each component is separate, you can test them independently:

```bash
# Test the daemon directly
cd app
python3 coopd.py --mac XX:XX:XX:XX:XX:XX --adapter hci0 --sock /tmp/test.sock

# Test the CLI controller
cd app
python3 coopctl.py status

# Test the API server
cd app
uvicorn coopdoor_api:app --reload
```

## Usage

### CLI Commands

```bash
coop-door status          # Check connection status
coop-door connect         # Connect to device
coop-door disconnect      # Disconnect
coop-door open 25         # Open to 25%
coop-door open 100        # Open fully
coop-door close           # Close door
coop-door config          # Show config
coop-door config --set mac=XX:XX:XX:XX:XX:XX
coop-door diag            # Show diagnostics
coop-door diag --verbose  # Detailed diagnostics
```

### Web Interface

Browse to: `http://[raspberry-pi-ip]:8080/`

**Features:**
- Real-time connection status
- Manual control with presets (25%, 50%, 75%, 100%)
- Custom percentage input
- Automation scheduling:
  - **Fixed Mode**: Set specific times (e.g., 7:00 AM / 8:30 PM)
  - **Solar Mode**: Automatic sunrise/sunset with offsets
- Schedule preview
- Full diagnostics

### API Endpoints

```bash
# Health check
curl http://localhost:8080/healthz

# Get status
curl http://localhost:8080/status

# Open door to 75%
curl -X POST http://localhost:8080/open?percent=75

# Close door
curl -X POST http://localhost:8080/close

# Get automation config
curl http://localhost:8080/automation

# Update config (Fixed mode)
curl -X PUT http://localhost:8080/automation \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "fixed",
    "fixed": {"open": "07:00", "close": "20:30"},
    "timezone": "America/New_York",
    "open_percent": 100
  }'

# Update config (Solar mode)
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

# Apply schedule now
curl -X POST http://localhost:8080/automation/apply

# Preview schedule
curl http://localhost:8080/schedule/preview
```

## Single-Mode Enforcement

The UI and API now enforce that **only one mode** (solar OR fixed) is active:

### How It Works:

1. **UI Level**: Radio buttons show only one panel at a time
2. **Save Logic**: Only the selected mode's data is sent to the API
3. **Validation**: Solar mode requires ZIP code; Fixed mode requires times
4. **Storage**: Config file only contains active mode's settings

### Example:

**Fixed Mode Config:**
```json
{
  "mode": "fixed",
  "fixed": {"open": "07:00", "close": "20:30"},
  "timezone": "America/New_York",
  "open_percent": 100
}
```
Note: No `solar` key exists

**Solar Mode Config:**
```json
{
  "mode": "solar",
  "solar": {"sunrise_offset_min": 30, "sunset_offset_min": -30},
  "location": {"lat": 26.7, "lon": -80.1, "zip": "33411", "country": "US"},
  "timezone": "America/New_York",
  "open_percent": 100
}
```
Note: No `fixed` key exists

## System Management

### Check Services

```bash
# API service
systemctl status coopdoor-api

# Schedule timer
systemctl status coopdoor-apply-schedule.timer

# View all timers
systemctl list-timers | grep coopdoor
```

### View Logs

```bash
# API logs
journalctl -u coopdoor-api -f

# Schedule apply logs
journalctl -u coopdoor-apply-schedule -f

# Daemon logs (CLI operations)
tail -f ~/.cache/coopdoor/coopd.log
```

### Restart Services

```bash
# Restart API
sudo systemctl restart coopdoor-api

# Manually apply schedule
sudo systemctl start coopdoor-apply-schedule.service
```

## Development Workflow

### Making Changes

1. **Edit the component file:**
   ```bash
   nano app/coopdoor_api.py
   ```

2. **Test locally (optional):**
   ```bash
   cd app
   uvicorn coopdoor_api:app --reload
   ```

3. **Deploy the change:**
   ```bash
   sudo ./install.sh
   sudo systemctl restart coopdoor-api
   ```

### Version Control

Each component can be tracked separately:
```bash
git add app/coopd.py
git commit -m "Fix: Handle connection timeout better"

git add ui/index.html
git commit -m "UI: Add dark mode toggle"
```

## Advantages Over Monolithic Installer

| Aspect | Monolithic | DRY Edition |
|--------|-----------|-------------|
| **Installer size** | 1,100+ lines | ~250 lines |
| **Edit a component** | Find heredoc in 1,100 lines | Edit one file |
| **Test a component** | Extract from heredoc first | Just run the file |
| **Version control** | One giant commit | Granular commits |
| **Code reuse** | Duplicate (embedded + runtime) | Single source |
| **Maintainability** | Hard | Easy |
| **Customization** | Edit installer script | Edit component files |
| **Debugging** | Hard to isolate | Test each component |

## Configuration Reference

### Device Settings (`/etc/coopdoor/config.json`)

```json
{
  "mac": "00:80:E1:22:EE:F2",           // BLE MAC address
  "adapter": "hci0",                     // Bluetooth adapter
  "connect_timeout": 15,                 // Seconds to wait for connection
  "base_pulses": 14,                     // Pulses for 100% open
  "pulse_interval": 2.0,                 // Seconds between pulses
  "home_before_open": false,             // Close before opening (calibration)
  "min_pause_after_action": 1.0          // Pause after operations (seconds)
}
```

### Automation Settings (`/etc/coopdoor/automation.json`)

**Fixed Mode:**
```json
{
  "mode": "fixed",
  "fixed": {
    "open": "07:00",
    "close": "20:30"
  },
  "timezone": "America/New_York",
  "open_percent": 100
}
```

**Solar Mode:**
```json
{
  "mode": "solar",
  "solar": {
    "sunrise_offset_min": 30,      // Open 30 min AFTER sunrise
    "sunset_offset_min": -30       // Close 30 min BEFORE sunset
  },
  "location": {
    "lat": 26.7,
    "lon": -80.1,
    "zip": "33411",
    "country": "US"
  },
  "timezone": "America/New_York",
  "open_percent": 100               // 0-100, or 0 for no cap
}
```

## Troubleshooting

### Service won't start
```bash
# Check logs
journalctl -u coopdoor-api -n 50

# Check Python environment
/opt/coopdoor/.venv/bin/python3 --version

# Reinstall dependencies
sudo -u coop /opt/coopdoor/.venv/bin/pip install --upgrade fastapi uvicorn astral pgeocode
```

### Can't connect to device
```bash
# Check Bluetooth
hciconfig
systemctl status bluetooth

# Test connection
coop-door connect
coop-door diag --verbose

# Check daemon logs
tail -f ~/.cache/coopdoor/coopd.log
```

### Schedule not applying
```bash
# Manually apply
sudo systemctl start coopdoor-apply-schedule.service

# Check timer
systemctl list-timers | grep coopdoor

# View logs
journalctl -u coopdoor-apply-schedule -n 20
```

## Authentication (Optional)

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

## Uninstallation

```bash
# Stop services
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
```

## Credits

- Original install.sh and install_web.sh authors
- DRY unified installer created 2025-10-26
- Single-mode enforcement added
- Component separation implemented

## License

Same as the original CoopDoor project

## Scripts Directory

All management scripts are in the `scripts/` directory:

| Script | Purpose |
|--------|---------|
| **install.sh** | Install CoopDoor |
| **uninstall.sh** | Remove CoopDoor |
| **backup.sh** | Backup configuration |
| **restore.sh** | Restore from backup |
| **config.sh** | Shared configuration (sourced by all scripts) |

See [scripts/README.md](scripts/README.md) for detailed documentation.

### Quick Examples

```bash
# Install
sudo ./scripts/install.sh

# Backup before changes
sudo ./scripts/backup.sh

# Restore if needed
sudo ./scripts/restore.sh ~/coopdoor-backups/coopdoor-backup-*.tar.gz

# Uninstall (keep config)
sudo ./scripts/uninstall.sh --keep-config
```

All scripts support `--help` for full usage information.

