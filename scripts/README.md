# CoopDoor Scripts

This directory contains all management scripts for CoopDoor. Each script is self-contained and uses the shared `config.sh` for DRY principles.

## Scripts Overview

| Script | Purpose | Usage |
|--------|---------|-------|
| **config.sh** | Shared configuration | Sourced by other scripts |
| **install.sh** | Install CoopDoor | `sudo ./install.sh` |
| **uninstall.sh** | Remove CoopDoor | `sudo ./uninstall.sh [options]` |

## Quick Reference

### Installation
```bash
# Standard installation
cd coopdoor-unified
sudo ./scripts/install.sh
```

### Uninstall
```bash
# Full uninstall with confirmation
sudo ./scripts/uninstall.sh

# Keep configuration for later reinstall
sudo ./scripts/uninstall.sh --keep-config

# Keep user account
sudo ./scripts/uninstall.sh --keep-user

# Uninstall without prompts
sudo ./scripts/uninstall.sh --yes
```

## config.sh (Shared Configuration)

This file is sourced by all other scripts and contains:
- **Device defaults** (MAC, adapter, timeouts, pulses)
- **System paths** (/opt/coopdoor, /etc/coopdoor, etc.)
- **Service names** (list of systemd services)
- **Helper functions** (log, die, need_cmd, etc.)

### DRY Principle
All constants are defined once in `config.sh`. To change defaults:
1. Edit `config.sh`
2. All scripts automatically use new values

Example:
```bash
# Edit this in config.sh once:
readonly MAC_DEFAULT="00:80:E1:22:EE:F2"

# All scripts use it:
# - install.sh creates config with this MAC
# - backup.sh backs up this value
# - restore.sh restores it
```

## install.sh

**Purpose:** Install all CoopDoor components

**What it does:**
1. Checks prerequisites (Python, systemctl, etc.)
2. Creates system user (`coop`)
3. Sets up Python virtual environment
4. Copies application files to /opt/coopdoor
5. Copies UI files to /opt/coopdoor/ui
6. Installs CLI shim to /usr/local/bin/coop-door
7. Writes default configuration
8. Installs systemd services
9. Configures sudoers
10. Optionally sets up Tailscale

**Usage:**
```bash
sudo ./scripts/install.sh
```

**Environment Variables:**
- `TAILSCALE_ENABLE_SERVE=0` - Disable Tailscale serve setup

**Where it installs:**
```
/opt/coopdoor/          # Application
├── .venv/              # Python environment
├── coopd.py            # BLE daemon
├── coopctl.py          # CLI controller
├── coopdoor_api.py     # Web API
├── schedule_apply.py   # Scheduler
└── ui/                 # Web interface

/etc/coopdoor/          # Configuration
├── config.json         # Device settings
└── automation.json     # Schedule (created on first save)

/usr/local/bin/
└── coop-door           # CLI shim

/etc/systemd/system/    # Services
├── coopdoor-api.service
├── coopdoor-apply-schedule.service
└── coopdoor-apply-schedule.timer

/etc/sudoers.d/
└── coopdoor-apply      # Sudoers rule
```

## uninstall.sh

**Purpose:** Remove CoopDoor cleanly

**What it does:**
1. Confirms with user (unless --yes)
2. Stops all services
3. Disables services
4. Removes systemd files
5. Removes application files
6. Removes configuration (unless --keep-config)
7. Removes user (unless --keep-user)
8. Cleans up Tailscale configuration

**Options:**
- `--keep-config` - Preserve configuration for reinstall
- `--keep-user` - Don't remove the `coop` user
- `--yes` - Skip confirmation prompt
- `--help` - Show help

**Usage:**
```bash
# Full removal
sudo ./scripts/uninstall.sh

# Keep config for later reinstall
sudo ./scripts/uninstall.sh --keep-config

# Multiple options
sudo ./scripts/uninstall.sh --keep-config --keep-user --yes
```

**What gets removed:**
```
/opt/coopdoor/          # ✓ Removed
/etc/coopdoor/          # ✓ Removed (unless --keep-config)
/usr/local/bin/coop-door # ✓ Removed
/etc/systemd/system/coopdoor-* # ✓ Removed
/etc/sudoers.d/coopdoor-apply # ✓ Removed
~/.config/coopdoor      # ✓ Removed (unless --keep-config)
~/.cache/coopdoor       # ✓ Removed (unless --keep-config)
coop user               # ✓ Removed (unless --keep-user)
```

### New Installation
```bash
cd coopdoor
sudo ./scripts/install.sh
```


### Complete Removal
```bash
# Backup first (just in case)
sudo ./scripts/backup.sh

# Remove everything
sudo ./scripts/uninstall.sh
```

### Clean Reinstall (Keep Config)
```bash
# Uninstall but keep config
sudo ./scripts/uninstall.sh --keep-config

# Reinstall (uses existing config)
sudo ./scripts/install.sh
```

## Exit Codes

All scripts follow standard exit codes:
- `0` - Success
- `1` - Error (see error message)
- `2` - Invalid usage

Check exit code:
```bash
sudo ./scripts/install.sh
echo $?  # 0 = success, 1 = error
```

## Error Handling

Scripts use consistent error handling:
- `die()` - Fatal error, exit immediately
- `warn()` - Warning, continue execution
- `log()` - Informational message

Example output:
```
==> Installing application files     # log()
WARNING: Tailscale not installed     # warn()
ERROR: Missing required command      # die() + exit
```

## Logging

Scripts log to stdout/stderr:
- Standard messages: stdout
- Warnings: stderr
- Errors: stderr

Capture logs:
```bash
# Save output
sudo ./scripts/install.sh 2>&1 | tee install.log

# Only errors
sudo ./scripts/install.sh 2> errors.log

# Discard output
sudo ./scripts/install.sh >/dev/null 2>&1
```

## Testing Scripts

Before deploying, test in a VM or test system:

```bash
# Test install
sudo ./scripts/install.sh
coop-door status

# Test backup
sudo ./scripts/backup.sh
ls ~/coopdoor-backups/

# Test restore
sudo ./scripts/restore.sh ~/coopdoor-backups/coopdoor-backup-*.tar.gz

# Test uninstall
sudo ./scripts/uninstall.sh --keep-config
```

## Customization

### Change Default MAC Address
Edit `config.sh`:
```bash
readonly MAC_DEFAULT="YOUR:MAC:HERE"
```

### Add Custom Backup Location
Edit `backup.sh` or use `--output`:
```bash
sudo ./scripts/backup.sh --output /mnt/nas/coopdoor-backups
```

### Skip Tailscale Setup
```bash
TAILSCALE_ENABLE_SERVE=0 sudo ./scripts/install.sh
```

## Troubleshooting

### Script won't run
```bash
# Make executable
chmod +x scripts/*.sh

# Check shebang
head -1 scripts/install.sh  # Should be #!/usr/bin/env bash
```

### Permission denied
```bash
# Scripts require root
sudo ./scripts/install.sh
```

### Config not found
```bash
# Scripts must be run from scripts/ directory or parent
cd coopdoor-unified/scripts/
sudo ./install.sh

# Or with full path
sudo /path/to/coopdoor-unified/scripts/install.sh
```

## Best Practices

1. **Always backup before changes**
   ```bash
   sudo ./scripts/backup.sh
   ```

2. **Test in VM first**
   - Don't test on production Pi
   - Use snapshots

3. **Keep multiple backups**
   - Daily, weekly, monthly
   - Store off-device

4. **Document customizations**
   - Note changes to config.sh
   - Keep change log

5. **Use version control**
   ```bash
   git init
   git add scripts/
   git commit -m "Initial scripts"
   ```

## Support

For issues with scripts:
1. Check this README
2. Read script help: `./script.sh --help`
3. Check logs: `journalctl -u coopdoor-api`
4. Run with set -x: `bash -x scripts/install.sh`

## Credits

Scripts created for CoopDoor v3.3
Following DRY principles with shared config.sh
