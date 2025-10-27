# CoopDoor v3.3.1

**Automatic Chicken Coop Door Controller with Scheduling**

CoopDoor is a Raspberry Pi-based automation system that controls a Bluetooth Low Energy (BLE) chicken coop door opener/closer. Set your chickens' schedule once, and the door opens and closes automatically every day—no more rushing home before sunset or waking up early to let them out.

---

## What is CoopDoor?

CoopDoor connects your Raspberry Pi to a BLE-enabled automatic chicken coop door (like the Chickcozy or similar brands) and provides:

- 🌅 **Automatic sunrise/sunset scheduling** - Door opens at dawn, closes at dusk
- ⏰ **Fixed time scheduling** - Set specific times like 7:00 AM / 8:30 PM  
- 🎛️ **Manual control** - Open/close via web interface or command line
- 📱 **Web UI** - Control from your phone, tablet, or computer (works as a PWA)
- 📊 **Status monitoring** - See connection status, last operation, and schedule
- 🔧 **Flexible configuration** - Partial opening percentages, timezone support, offset adjustments

### The Problem It Solves

If you have chickens, you know the daily routine:
- **Morning:** Let them out of the coop when it gets light
- **Evening:** Close them in before dark (for safety from predators)

Miss the evening closing? Your chickens are vulnerable. Wake up late? They're waiting impatiently.

**CoopDoor automates this completely.** Set your schedule once, and your chickens are protected every day, automatically.

---

## How It Works

### System Architecture

```
┌─────────────────┐         BLE          ┌──────────────────┐
│  Raspberry Pi   │ ◄──────────────────► │   Coop Door      │
│                 │      Bluetooth        │   (BLE Device)   │
│  - CoopDoor API │                       │                  │
│  - BLE Daemon   │                       │  - Motor         │
│  - Scheduler    │                       │  - Battery       │
└─────────────────┘                       └──────────────────┘
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

### Key Components

1. **BLE Daemon (`coopd.py`)** - Maintains Bluetooth connection to your coop door device
   - Automatically reconnects if connection drops
   - Sends open/close commands via BLE
   - Handles partial opening (25%, 50%, 75%, 100%)

2. **Web API (`coopdoor_api.py`)** - FastAPI server providing:
   - REST API endpoints for control
   - Web interface for configuration
   - Status monitoring
   - Schedule management

3. **Scheduler (`schedule_apply.py`)** - Runs daily to:
   - Calculate today's sunrise/sunset (if in solar mode)
   - Apply fixed times (if in fixed mode)
   - Set up systemd timers for automatic open/close

4. **CLI Tool (`coopctl.py`)** - Command-line interface for:
   - Manual door control
   - Quick status checks
   - Configuration management
   - Diagnostics

### How Scheduling Works

**Solar Mode** (Sunrise/Sunset):
1. You provide your ZIP code
2. CoopDoor calculates today's sunrise and sunset times
3. Optional offsets: open 30 min after sunrise, close 30 min before sunset
4. Schedule updates automatically each day (accounts for seasonal changes)

**Fixed Mode** (Set Times):
1. You set specific times (e.g., 7:00 AM and 8:30 PM)
2. CoopDoor opens/closes at those times every day
3. Timezone-aware (handles daylight saving time)

**Automation Flow:**
```
Daily at 00:30 → Calculate times → Set timers → Open at time 1 → Close at time 2
```

---

## Hardware Requirements

### What You Need

1. **Raspberry Pi** (any model with Bluetooth)
   - Raspberry Pi 3/4/5 (built-in Bluetooth) ✅ Recommended
   - Raspberry Pi Zero W/2W (built-in Bluetooth) ✅ Works great
   - Older Pi + USB Bluetooth adapter (also works)

2. **BLE Chicken Coop Door Opener**
   - Tested with: Chickcozy, and similar BLE-enabled door openers
   - Requirements: Must support Bluetooth Low Energy (BLE)
   - Battery or solar powered

3. **Network Connection** (for web access)
   - WiFi or Ethernet
   - Only needed for the web interface (door control still works offline)

### Finding Your Door's BLE MAC Address

Before installation, you need to find your door's Bluetooth MAC address:

```bash
# Install Bluetooth tools
sudo apt-get install bluetooth bluez

# Scan for BLE devices (door must be powered on)
sudo hcitool lescan

# Look for your door device (usually shows as unknown or with device name)
# Example output:
# 00:80:E1:22:EE:F2 (unknown)
```

Save this MAC address - you'll need it during setup.

---

## Quick Start

### Installation

```bash
# 1. Clone or download CoopDoor
git clone https://github.com/yourusername/coopdoor.git
cd coopdoor

# 2. Run the installer
sudo ./install.sh

# 3. Edit config to set your door's MAC address
sudo nano /etc/coopdoor/config.json
# Change "mac": "00:80:E1:22:EE:F2" to your door's address

# 4. Restart the API
sudo systemctl restart coopdoor-api
```

### First-Time Setup

1. **Open the web interface:**
   ```
   http://your-pi-ip:8080
   ```

2. **Go to Config tab and set your schedule:**
   
   **For Solar Mode:**
   - Select "Sunrise / Sunset"
   - Enter your ZIP code (e.g., 33411)
   - Set offsets if desired (e.g., +30 min sunrise, -30 min sunset)
   - Click Save
   
   **For Fixed Mode:**
   - Select "Fixed"
   - Set open time (e.g., 07:00)
   - Set close time (e.g., 20:30)
   - Click Save

3. **Click "Apply Now"** to activate the schedule

4. **Test it:**
   - Go back to Control/Status tab
   - Click "Open 100%" to fully open the door
   - Wait a few seconds, then click "Close"
   - Verify the door responds correctly

### Verify It's Working

```bash
# Check the schedule is active
coop-door diag

# See today's calculated times
curl http://localhost:8080/schedule/preview

# Check systemd timers are set
systemctl list-timers | grep coopdoor
```

You should see two timers: one for opening and one for closing.

---

## What's New in v3.3.1

### Fixes:
- ✅ **Status Display Fixed**: Operations now correctly show "Succeeded" instead of "Failed"
- ✅ **Mode Display Fixed**: Shows "solar" or "fixed" instead of "Unknown"
- ✅ **Config Save Fixed**: Added unified `/config` endpoint for proper UI configuration saving
- ✅ **Permission Fix**: Installer creates `/var/lib/coopdoor-backups` with proper ownership

### What Was Fixed:
1. API now returns `last_event` object for `/open` and `/close` endpoints
2. `/schedule/preview` includes `mode` field for UI display
3. "Save failed: Not Found" error resolved with unified config endpoint
4. Permission denied errors on backup directory resolved

All services run as the `coop` user with proper permissions throughout.

---

## Architecture & Design

This is the **DRY (Don't Repeat Yourself)** version of CoopDoor. Instead of embedding all code inside a monolithic installer script, each component exists as a separate file that the installer copies into place.

### Why This Matters

**Before (Monolithic):** 1,100+ lines of installer with embedded code  
**After (DRY):** ~250 lines of installer + separate component files

Benefits:
- ✅ Easy to edit individual components
- ✅ Can test components independently
- ✅ Better version control (track each file separately)
- ✅ Single source of truth for each component
- ✅ Much easier to maintain and customize

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

---

## Detailed Installation

The installer automatically sets up everything you need. Here's what happens:
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

## Daily Usage

Once configured, CoopDoor runs automatically. You don't need to do anything!

### Automatic Operation

**Every day at 00:30 (12:30 AM):**
1. CoopDoor calculates today's open/close times
2. Sets systemd timers for those times
3. Door opens automatically at calculated time
4. Door closes automatically at calculated time

**You can monitor this via:**
- Web UI: Check "Last Action" to see latest operation
- Logs: `journalctl -u coopdoor-apply-schedule -f`
- CLI: `coop-door diag`

### Manual Control

#### Web Interface

Browse to: `http://[raspberry-pi-ip]:8080/`

**Control Tab:**
- Click preset buttons: 25%, 50%, 75%, 100%
- Click "Close" to close the door
- Click "Status" to refresh connection status
- View last action and automation schedule

**Config Tab:**
- Switch between Fixed and Solar modes
- Adjust times and offsets
- Save configuration
- Click "Apply Now" to activate immediately

**Diagnostics Tab:**
- View real-time logs
- Check connection status
- See configuration details

#### Command Line

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

### When to Use Manual Control

**Typical scenarios:**
- **Testing:** Verify door works after initial setup
- **Override:** Need door open/closed outside schedule (cleaning, sick chicken, etc.)
- **Maintenance:** Adjusting door position, checking battery
- **Emergency:** Weather event, predator in area, need immediate control

**For daily operation:** Just let it run automatically! The schedule handles everything.

### Understanding Door Percentages

The door uses a "pulse" system to control opening:
- **Each pulse** opens the door by approximately 7% (14 pulses = 100%)
- **25%** = ~4 pulses = Door opens slightly (chicks only)
- **50%** = ~7 pulses = Door half open
- **75%** = ~10 pulses = Door mostly open
- **100%** = 14 pulses = Fully open (all chickens)

**Pro tip:** Set `open_percent` cap in config to limit maximum opening (e.g., 75% for smaller chickens).

---

## Web Interface Features
- Real-time connection status
- Manual control with presets (25%, 50%, 75%, 100%)
- Custom percentage input
- Automation scheduling:
  - **Fixed Mode**: Set specific times (e.g., 7:00 AM / 8:30 PM)
  - **Solar Mode**: Automatic sunrise/sunset with offsets
- Schedule preview
- Full diagnostics

---

## Common Use Cases

### Scenario 1: Basic Sunrise/Sunset (Most Common)

**Goal:** Door opens at sunrise, closes at sunset. Simple and natural.

**Configuration:**
```json
{
  "mode": "solar",
  "zip": "33411",
  "country": "US",
  "solar": {
    "sunrise_offset_min": 0,
    "sunset_offset_min": 0
  },
  "open_percent": 100
}
```

**When to use:** You want your chickens to have daylight hours available automatically.

---

### Scenario 2: Late Open, Early Close (Maximum Safety)

**Goal:** Open 30 min after sunrise (when it's fully light), close 30 min before sunset (before dusk predators).

**Configuration:**
```json
{
  "mode": "solar",
  "zip": "33411",
  "solar": {
    "sunrise_offset_min": 30,    ← Opens AFTER sunrise
    "sunset_offset_min": -30     ← Closes BEFORE sunset
  },
  "open_percent": 100
}
```

**When to use:** Extra predator protection, or if your run isn't fully secure at dusk.

---

### Scenario 3: Work Schedule (Fixed Times)

**Goal:** Door opens before you leave for work (7 AM), closes when you're home (7 PM).

**Configuration:**
```json
{
  "mode": "fixed",
  "fixed": {
    "open": "07:00",
    "close": "19:00"
  },
  "timezone": "America/New_York",
  "open_percent": 100
}
```

**When to use:** You prefer consistent times regardless of season, or you have a specific routine.

---

### Scenario 4: Partial Opening for Small Birds

**Goal:** Limit door opening to 75% (younger/smaller chickens).

**Configuration:**
```json
{
  "mode": "solar",
  "zip": "33411",
  "solar": {
    "sunrise_offset_min": 0,
    "sunset_offset_min": 0
  },
  "open_percent": 75              ← Maximum opening limited
}
```

**When to use:** Chicks, bantams, or you want to restrict how far the door opens.

---

### Scenario 5: Winter Hours (Late Open, Early Close)

**Goal:** Fixed times that work well in winter when daylight is limited.

**Configuration:**
```json
{
  "mode": "fixed",
  "fixed": {
    "open": "08:00",              ← Later open (it's dark at 7 AM)
    "close": "17:00"              ← Earlier close (dark by 5 PM)
  },
  "timezone": "America/New_York",
  "open_percent": 100
}
```

**When to use:** You prefer manual seasonal adjustments over solar automation.

---

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

