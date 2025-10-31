#!/usr/bin/env python3
"""
schedule_apply.py - Apply automation schedule by creating systemd timers

This script reads automation config and creates systemd timers for 
scheduled door open/close operations.

PATCHED VERSION: Includes sudo rm fix for proper file deletion permissions
"""

import json
import os
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

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


CONFIG_FILE = "/etc/coopdoor/automation.json"
COOP_DOOR_CMD = "/usr/local/bin/coop-door"


def load_config():
    """Load automation configuration"""
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def get_coordinates_from_zip(zip_code, country="US"):
    """Get lat/lon from ZIP code using pgeocode"""
    if not GEOCODE_AVAILABLE:
        print("Error: pgeocode not available for ZIP lookup")
        return None, None
    
    nomi = pgeocode.Nominatim(country)
    location = nomi.query_postal_code(zip_code)
    
    if location is None or location.latitude != location.latitude:  # NaN check
        return None, None
    
    return location.latitude, location.longitude


def calculate_solar_times(config):
    """Calculate today's sunrise and sunset times"""
    if not SOLAR_AVAILABLE:
        print("Error: Solar calculations not available (missing astral/pytz)")
        return None, None
    
    # Get location
    if 'location' in config and 'lat' in config['location'] and 'lon' in config['location']:
        lat = config['location']['lat']
        lon = config['location']['lon']
    elif 'zip' in config:
        zip_code = config['zip']
        country = config.get('country', 'US')
        lat, lon = get_coordinates_from_zip(zip_code, country)
        if lat is None:
            print(f"Error: Could not get coordinates for ZIP: {zip_code}")
            return None, None
    else:
        print("Error: No location information in config")
        return None, None
    
    # Get timezone
    tz_name = config.get('timezone', 'America/New_York')
    try:
        tz = pytz.timezone(tz_name)
    except:
        print(f"Invalid timezone: {tz_name}, using America/New_York")
        tz = pytz.timezone('America/New_York')
    
    # Calculate sun times
    location = LocationInfo(latitude=lat, longitude=lon, timezone=tz_name)
    s = sun(location.observer, date=datetime.now(tz).date(), tzinfo=tz)
    
    sunrise = s['sunrise']
    sunset = s['sunset']
    
    # Apply offsets
    solar_config = config.get('solar', {})
    sunrise_offset = solar_config.get('sunrise_offset_min', 0)
    sunset_offset = solar_config.get('sunset_offset_min', 0)
    
    open_time = sunrise + timedelta(minutes=sunrise_offset)
    close_time = sunset + timedelta(minutes=sunset_offset)
    
    return open_time, close_time


def remove_existing_timers():
    """Remove existing timer and service files"""
    timer_file = "/etc/systemd/system/coopdoor-open.timer"
    service_file = "/etc/systemd/system/coopdoor-open.service"
    
    for file in [timer_file, service_file]:
        if os.path.exists(file):
            try:
                # Stop and disable if it's a timer
                if file.endswith('.timer'):
                    subprocess.run(["systemctl", "stop", os.path.basename(file)], check=False)
                    subprocess.run(["systemctl", "disable", os.path.basename(file)], check=False)
                
                # Use sudo to remove the file (requires proper permissions)
                subprocess.run(["sudo", "rm", "-f", file], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error removing {file}: {e}")
    
    # Reload systemd daemon with sudo
    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=False)


def create_timer(timer_name, when, command):
    """Create a systemd timer using systemd-run"""
    # Use systemd-run to create a transient timer
    # This runs as root via sudo but executes command as coop user
    result = subprocess.run([
        "sudo", "systemd-run",
        "--uid=coop",
        f"--on-calendar={when}",
        "--timer-property=RemainAfterElapse=no",
        "--unit", timer_name,
        *command.split()
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error creating timer: {result.stderr}")
        return False
    
    print(f"Created timer: {timer_name} at {when}")
    return True


def apply_schedule(config):
    """Apply the automation schedule"""
    mode = config.get('mode', 'solar')
    tz_name = config.get('timezone', 'America/New_York')
    
    try:
        tz = pytz.timezone(tz_name)
    except:
        print(f"Invalid timezone: {tz_name}, using America/New_York")
        tz = pytz.timezone('America/New_York')
    
    now = datetime.now(tz)
    
    # Calculate times based on mode
    if mode == 'solar':
        open_time, close_time = calculate_solar_times(config)
        if open_time is None:
            print("Failed to calculate solar times")
            return False
    else:  # fixed mode
        fixed = config.get('fixed', {})
        open_str = fixed.get('open', '07:00')
        close_str = fixed.get('close', '20:00')
        
        # Parse times
        open_t = datetime.strptime(open_str, '%H:%M').time()
        close_t = datetime.strptime(close_str, '%H:%M').time()
        
        # Create datetime objects for today
        open_time = tz.localize(datetime.combine(now.date(), open_t))
        close_time = tz.localize(datetime.combine(now.date(), close_t))
    
    # Get open percentage
    open_percent = config.get('open_percent', 100)
    if open_percent == 0:
        open_percent = 100  # 0 means no cap
    
    print(f"Mode: {mode}")
    print(f"Calculated times for today:")
    print(f"  Open:  {open_time.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"  Close: {close_time.strftime('%Y-%m-%d %H:%M %Z')}")
    
    # Remove existing timers
    print("Removing existing timers...")
    remove_existing_timers()
    
    # Create new timers if times are in the future
    if open_time > now:
        when = open_time.strftime('%Y-%m-%d %H:%M:%S')
        create_timer(
            "coopdoor-open",
            when,
            f"{COOP_DOOR_CMD} open {open_percent}"
        )
    else:
        print(f"Skipping open timer (time has passed: {open_time.strftime('%H:%M')})")
    
    if close_time > now:
        when = close_time.strftime('%Y-%m-%d %H:%M:%S')
        create_timer(
            "coopdoor-close",
            when,
            f"{COOP_DOOR_CMD} close"
        )
    else:
        print(f"Skipping close timer (time has passed: {close_time.strftime('%H:%M')})")
    
    return True


def main():
    print("=" * 50)
    print("CoopDoor Schedule Apply (FIXED VERSION)")
    print(f"Running at: {datetime.now()}")
    print("=" * 50)
    
    # Load config
    config = load_config()
    
    # Apply schedule
    success = apply_schedule(config)
    
    if success:
        print("\n✓ Schedule applied successfully")
        sys.exit(0)
    else:
        print("\n✗ Failed to apply schedule")
        sys.exit(1)


if __name__ == "__main__":
    main()
