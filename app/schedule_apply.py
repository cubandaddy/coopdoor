#!/usr/bin/env python3
"""
schedule_apply_improved.py - Apply automation schedule with PERSISTENT systemd timers

IMPROVEMENTS OVER ORIGINAL:
- Uses persistent timer files instead of transient systemd-run timers
- Timers survive reboots and systemd reloads
- Better error handling and logging
- State tracking for execution verification
- Comprehensive validation

This version creates actual .timer and .service files in /etc/systemd/system/
instead of using transient timers via systemd-run.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

# Configuration
try:
    from shared_config import AUTOMATION_PATH
    CONFIG_FILE = str(AUTOMATION_PATH)
except:
    CONFIG_FILE = "/opt/coopdoor/automation.json"

# Try to import optional dependencies
try:
    from astral import LocationInfo
    from astral.sun import sun
    import pytz
    SOLAR_AVAILABLE = True
except ImportError:
    SOLAR_AVAILABLE = False
    print("Warning: Solar mode dependencies not available (astral, pytz)")

try:
    import pgeocode
    GEOCODE_AVAILABLE = True
except ImportError:
    GEOCODE_AVAILABLE = False
    print("Warning: pgeocode not available for ZIP code lookup")

try:
    import timezonefinder
    TIMEZONE_FINDER_AVAILABLE = True
except ImportError:
    TIMEZONE_FINDER_AVAILABLE = False
    print("Warning: timezonefinder not available for auto-detection")


COOP_DOOR_CMD = "/usr/local/bin/coop-door"
TIMER_DIR = "/etc/systemd/system"
STATE_FILE = "/var/lib/coopdoor/schedule_state.json"
LOG_FILE = "/var/log/coopdoor/schedule.log"


def log_message(message):
    """Write log message to both console and log file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(log_line + '\n')
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}")


def validate_config(config):
    """Validate configuration values"""
    mode = config.get('mode')
    
    if mode not in ['solar', 'fixed']:
        raise ValueError(f"Invalid mode: {mode}. Must be 'solar' or 'fixed'")
    
    if mode == 'solar':
        solar = config.get('solar', {})
        sunrise_offset = solar.get('sunrise_offset_min', 0)
        sunset_offset = solar.get('sunset_offset_min', 0)
        
        if not -180 <= sunrise_offset <= 180:
            raise ValueError(f"sunrise_offset_min must be between -180 and 180 minutes")
        if not -180 <= sunset_offset <= 180:
            raise ValueError(f"sunset_offset_min must be between -180 and 180 minutes")
        
        if 'zip' not in config and ('location' not in config or 'lat' not in config['location']):
            raise ValueError("Solar mode requires either 'zip' or 'location' with lat/lon")
    
    if mode == 'fixed':
        fixed = config.get('fixed', {})
        if 'open' not in fixed or 'close' not in fixed:
            raise ValueError("Fixed mode requires both 'open' and 'close' times")
        
        try:
            datetime.strptime(fixed['open'], '%H:%M')
            datetime.strptime(fixed['close'], '%H:%M')
        except ValueError as e:
            raise ValueError(f"Invalid time format (use HH:MM): {e}")
    
    return True


def load_config():
    """Load and validate configuration"""
    if not os.path.exists(CONFIG_FILE):
        log_message(f"Error: Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    
    validate_config(config)
    return config


def get_coordinates_from_zip(zip_code, country="US"):
    """Get lat/lon from ZIP code"""
    if not GEOCODE_AVAILABLE:
        return None, None
    
    nomi = pgeocode.Nominatim(country)
    location = nomi.query_postal_code(zip_code)
    
    if location is None or location.latitude != location.latitude:
        return None, None
    
    return location.latitude, location.longitude


def get_timezone_from_coords(lat, lon):
    """Auto-detect timezone from coordinates"""
    if not TIMEZONE_FINDER_AVAILABLE:
        return 'America/New_York'
    
    try:
        tf = timezonefinder.TimezoneFinder()
        tz_name = tf.timezone_at(lat=lat, lng=lon)
        return tz_name if tz_name else 'America/New_York'
    except:
        return 'America/New_York'


def calculate_solar_times(config, tz):
    """Calculate today's sunrise and sunset times"""
    if not SOLAR_AVAILABLE:
        log_message("Error: Solar calculations not available")
        return None, None
    
    # Get location
    if 'location' in config and 'lat' in config['location']:
        lat = config['location']['lat']
        lon = config['location']['lon']
    elif 'zip' in config:
        lat, lon = get_coordinates_from_zip(config['zip'], config.get('country', 'US'))
        if lat is None:
            log_message(f"Error: Could not get coordinates for ZIP")
            return None, None
    else:
        log_message("Error: No location information")
        return None, None
    
    # Calculate sun times
    location = LocationInfo(latitude=lat, longitude=lon, timezone=tz.zone)
    s = sun(location.observer, date=datetime.now(tz).date(), tzinfo=tz)
    
    sunrise = s['sunrise']
    sunset = s['sunset']
    
    # Apply offsets
    solar_config = config.get('solar', {})
    sunrise_offset = solar_config.get('sunrise_offset_min', 0)
    sunset_offset = solar_config.get('sunset_offset_min', 0)
    
    open_time = sunrise + timedelta(minutes=sunrise_offset)
    close_time = sunset + timedelta(minutes=sunset_offset)
    
    # Sanity checks
    now = datetime.now(tz)
    
    if not (4 <= open_time.hour <= 10):
        log_message(f"⚠️  WARNING: Open time {open_time.strftime('%H:%M')} outside 4-10 AM range")
        open_time = tz.localize(datetime.combine(now.date(), time(7, 0)))
    
    if not (16 <= close_time.hour <= 22):
        log_message(f"⚠️  WARNING: Close time {close_time.strftime('%H:%M')} outside 4-10 PM range")
        close_time = tz.localize(datetime.combine(now.date(), time(19, 0)))
    
    if close_time <= open_time:
        log_message(f"⚠️  WARNING: Close time before open time!")
        open_time = tz.localize(datetime.combine(now.date(), time(7, 0)))
        close_time = tz.localize(datetime.combine(now.date(), time(19, 0)))
    
    return open_time, close_time


def remove_existing_timers():
    """Remove existing timer files"""
    log_message("Removing existing timers...")
    
    for timer_name in ["coopdoor-open", "coopdoor-close"]:
        # Stop and disable
        subprocess.run(["sudo", "systemctl", "stop", f"{timer_name}.timer"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "disable", f"{timer_name}.timer"], capture_output=True)
        
        # Remove files
        timer_file = f"{TIMER_DIR}/{timer_name}.timer"
        service_file = f"{TIMER_DIR}/{timer_name}.service"
        
        for file in [timer_file, service_file]:
            if os.path.exists(file):
                subprocess.run(["sudo", "rm", "-f", file], capture_output=True)
    
    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=False)
    log_message("✓ Cleanup complete")


def create_persistent_timer(timer_name, when_dt, command, now):
    """Create a PERSISTENT systemd timer"""
    
    if when_dt <= now:
        log_message(f"  ⚠️  Skipping {timer_name}: time has passed")
        return False
    
    time_until = when_dt - now
    hours = time_until.total_seconds() / 3600
    
    if hours > 24:
        log_message(f"  ⚠️  Skipping {timer_name}: >24 hours away")
        return False
    
    when_str = when_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    log_message(f"  Creating persistent timer: {timer_name}")
    log_message(f"    Scheduled for: {when_str} (in {hours:.1f} hours)")
    
    # Determine API endpoint and command
    if "open" in timer_name:
        api_endpoint = "http://localhost:8080/open"
        # Extract percentage from command like "coop-door open 100"
        percent = command.split()[-1] if len(command.split()) > 2 else "100"
        curl_cmd = f'/usr/bin/curl -s -X POST -H \\"Content-Type: application/json\\" -d \'{{"percent": {percent}}}\' {api_endpoint}'
        log_message(f"    Action: Open door to {percent}%")
    else:
        api_endpoint = "http://localhost:8080/close"
        curl_cmd = f'/usr/bin/curl -s -X POST {api_endpoint}'
        log_message(f"    Action: Close door")
    
    # Timer file content
    timer_content = f"""[Unit]
Description=CoopDoor {timer_name} timer

[Timer]
OnCalendar={when_str}
Persistent=false

[Install]
WantedBy=timers.target
"""
    
    # Service file content with proper logging
    service_content = f"""[Unit]
Description=CoopDoor {timer_name} action

[Service]
Type=oneshot
User=coop
ExecStart=/bin/bash -c "{curl_cmd}"
StandardOutput=journal
StandardError=journal
SyslogIdentifier=coopdoor-{timer_name}
"""
    
    try:
        # Write files to /tmp first, then move with sudo
        timer_file = f"{TIMER_DIR}/{timer_name}.timer"
        service_file = f"{TIMER_DIR}/{timer_name}.service"
        
        with open(f"/tmp/{timer_name}.timer", 'w') as f:
            f.write(timer_content)
        with open(f"/tmp/{timer_name}.service", 'w') as f:
            f.write(service_content)
        
        subprocess.run(["sudo", "mv", f"/tmp/{timer_name}.timer", timer_file], check=True)
        subprocess.run(["sudo", "mv", f"/tmp/{timer_name}.service", service_file], check=True)
        subprocess.run(["sudo", "chmod", "644", timer_file, service_file], check=True)
        
        # Reload, enable, start
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        subprocess.run(["sudo", "systemctl", "enable", f"{timer_name}.timer"], check=True)
        subprocess.run(["sudo", "systemctl", "start", f"{timer_name}.timer"], check=True)
        
        log_message(f"  ✓ Persistent timer created: {timer_file}")
        return True
        
    except Exception as e:
        log_message(f"  ✗ Error creating timer: {e}")
        return False


def save_schedule_state(open_time, close_time, mode):
    """Save schedule state for monitoring"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        # Bug #11 fix: Use date from scheduled open_time, not current date
        # This ensures the date field matches the actual scheduled date
        state = {
            "date": open_time.date().isoformat(),
            "mode": mode,
            "open_time": open_time.isoformat(),
            "close_time": close_time.isoformat(),
            "open_completed": False,
            "close_completed": False,
            "created_at": datetime.now().isoformat()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        log_message(f"✓ State saved to {STATE_FILE}")
    except Exception as e:
        log_message(f"Warning: Could not save state: {e}")


def apply_schedule(config):
    """Apply the schedule using PERSISTENT timers"""
    mode = config.get('mode', 'solar')
    
    # Determine timezone
    tz_name = config.get('timezone')
    if not tz_name:
        if mode == 'solar':
            if 'location' in config and 'lat' in config['location']:
                lat = config['location']['lat']
                lon = config['location']['lon']
                tz_name = get_timezone_from_coords(lat, lon)
            elif 'zip' in config:
                lat, lon = get_coordinates_from_zip(config['zip'])
                if lat:
                    tz_name = get_timezone_from_coords(lat, lon)
                else:
                    tz_name = 'America/New_York'
            else:
                tz_name = 'America/New_York'
        else:
            tz_name = 'America/New_York'
    
    try:
        tz = pytz.timezone(tz_name)
    except:
        tz = pytz.timezone('America/New_York')
    
    now = datetime.now(tz)
    
    log_message(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log_message(f"Mode: {mode}")
    
    # Calculate times
    if mode == 'solar':
        log_message("Calculating solar times...")
        open_time, close_time = calculate_solar_times(config, tz)
        if open_time is None:
            log_message("✗ Failed to calculate solar times")
            return False
    else:  # fixed mode
        log_message("Using fixed times...")
        fixed = config.get('fixed', {})
        open_str = fixed.get('open', '07:00')
        close_str = fixed.get('close', '20:00')
        
        open_t = datetime.strptime(open_str, '%H:%M').time()
        close_t = datetime.strptime(close_str, '%H:%M').time()
        
        open_time = tz.localize(datetime.combine(now.date(), open_t))
        close_time = tz.localize(datetime.combine(now.date(), close_t))
        
        if open_time <= now:
            open_time = open_time + timedelta(days=1)
        if close_time <= now:
            close_time = close_time + timedelta(days=1)
    
    open_percent = config.get('open_percent', 100) or 100
    
    log_message(f"\nSchedule:")
    log_message(f"  Open:  {open_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log_message(f"  Close: {close_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log_message(f"  Open %: {open_percent}")
    
    # Remove existing timers
    remove_existing_timers()
    
    # Create new PERSISTENT timers
    log_message("\nCreating persistent timers...")
    open_created = create_persistent_timer(
        "coopdoor-open",
        open_time,
        f"{COOP_DOOR_CMD} open {open_percent}",
        now
    )
    
    close_created = create_persistent_timer(
        "coopdoor-close",
        close_time,
        f"{COOP_DOOR_CMD} close",
        now
    )
    
    # Save state
    save_schedule_state(open_time, close_time, mode)
    
    # Verify timers
    log_message("\nVerifying timers...")
    result = subprocess.run(
        ["systemctl", "list-timers", "--all", "--no-pager"],
        capture_output=True,
        text=True
    )
    
    for line in result.stdout.split('\n'):
        if 'coopdoor-open' in line:
            log_message(f"  ✓ Open timer: {line.strip()}")
        if 'coopdoor-close' in line:
            log_message(f"  ✓ Close timer: {line.strip()}")
    
    # Verify files
    for timer_name in ["coopdoor-open", "coopdoor-close"]:
        timer_file = f"{TIMER_DIR}/{timer_name}.timer"
        if os.path.exists(timer_file):
            log_message(f"  ✓ Timer file exists: {timer_file}")
        else:
            log_message(f"  ✗ Timer file missing: {timer_file}")
    
    return (open_created or close_created)


def main():
    log_message("=" * 60)
    log_message("CoopDoor Schedule Apply (PERSISTENT TIMER VERSION)")
    log_message(f"Running at: {datetime.now()}")
    log_message("=" * 60)
    
    try:
        config = load_config()
    except Exception as e:
        log_message(f"✗ Failed to load config: {e}")
        sys.exit(1)
    
    try:
        success = apply_schedule(config)
    except Exception as e:
        log_message(f"\n✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    if success:
        log_message("\n" + "=" * 60)
        log_message("✓ PERSISTENT timers created successfully")
        log_message("  Timers will survive reboots!")
        log_message("=" * 60)
        sys.exit(0)
    else:
        log_message("\n" + "=" * 60)
        log_message("✗ Failed to apply schedule")
        log_message("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
