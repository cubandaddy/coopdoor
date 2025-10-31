#!/usr/bin/env python3
"""
schedule_apply.py - Apply automation schedule by creating systemd timers

This script reads automation config and creates systemd timers for 
scheduled door open/close operations.

FIXED VERSION: 
- Addresses permission issues with sudo
- Fixes midnight timer bug by validating future times
- Proper systemd-run calendar format
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
    """Remove existing timer and service files - FIXED VERSION with sudo"""
    print("Removing existing timers...")
    
    # Stop and disable any running timers first
    for timer_name in ["coopdoor-open", "coopdoor-close"]:
        # Try to stop the timer unit (may not exist, that's ok)
        subprocess.run(
            ["sudo", "systemctl", "stop", f"{timer_name}.timer"],
            capture_output=True,
            check=False
        )
        subprocess.run(
            ["sudo", "systemctl", "stop", f"{timer_name}.service"],
            capture_output=True,
            check=False
        )
    
    # Remove timer and service files from /etc/systemd/system/
    timer_file = "/etc/systemd/system/coopdoor-open.timer"
    service_file = "/etc/systemd/system/coopdoor-open.service"
    close_timer = "/etc/systemd/system/coopdoor-close.timer"
    close_service = "/etc/systemd/system/coopdoor-close.service"
    
    for file in [timer_file, service_file, close_timer, close_service]:
        if os.path.exists(file):
            try:
                print(f"  Removing {file}")
                result = subprocess.run(
                    ["sudo", "rm", "-f", file],
                    capture_output=True,
                    text=True,
                    check=True
                )
            except subprocess.CalledProcessError as e:
                print(f"  Warning: Could not remove {file}: {e.stderr}")
    
    # Also clean up any transient timers that systemd-run might have created
    print("  Cleaning up transient timers...")
    result = subprocess.run(
        ["systemctl", "list-units", "--all", "--no-pager"],
        capture_output=True,
        text=True
    )
    for line in result.stdout.split('\n'):
        if 'coopdoor-open' in line or 'coopdoor-close' in line:
            unit_name = line.split()[0]
            print(f"  Stopping transient unit: {unit_name}")
            subprocess.run(
                ["sudo", "systemctl", "stop", unit_name],
                capture_output=True,
                check=False
            )
    
    # Reload systemd daemon
    print("  Reloading systemd daemon...")
    subprocess.run(
        ["sudo", "systemctl", "daemon-reload"],
        check=False
    )
    
    print("✓ Cleanup complete")


def create_timer(timer_name, when_dt, command, now):
    """
    Create a systemd timer using systemd-run
    
    CRITICAL FIX: Validates that the time is in the future before creating timer
    and uses proper systemd calendar format.
    
    Args:
        timer_name: Name for the timer unit
        when_dt: datetime object for when to run (must be timezone-aware)
        command: Full command string to execute
        now: Current datetime (timezone-aware) for validation
    
    Returns:
        True if timer created successfully, False otherwise
    """
    
    # CRITICAL: Validate time is in the future
    if when_dt <= now:
        print(f"  ⚠ Skipping {timer_name}: time {when_dt.strftime('%H:%M:%S')} has already passed")
        return False
    
    time_until = when_dt - now
    hours = time_until.total_seconds() / 3600
    
    # Additional safety: don't create timers for times more than 24 hours away
    if hours > 24:
        print(f"  ⚠ Skipping {timer_name}: time is more than 24 hours away")
        return False
    
    # Format for systemd OnCalendar: "YYYY-MM-DD HH:MM:SS"
    # This is the ISO format that systemd expects
    when_str = when_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"  Creating timer: {timer_name}")
    print(f"    Scheduled for: {when_str} (in {hours:.1f} hours)")
    print(f"    Command: {command}")
    
    # Use systemd-run to create a transient timer
    # --uid=coop ensures command runs as coop user
    # --on-calendar specifies when to run
    # --timer-property=RemainAfterElapse=no cleans up after execution
    cmd_args = [
        "sudo", "systemd-run",
        "--uid=coop",
        f"--on-calendar={when_str}",
        "--timer-property=RemainAfterElapse=no",
        f"--unit={timer_name}"
    ]
    
    # Add the actual command to execute
    cmd_args.extend(command.split())
    
    try:
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"  ✓ Timer created successfully")
        if result.stdout:
            print(f"    {result.stdout.strip()}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error creating timer: {e.stderr}")
        return False


def apply_schedule(config):
    """Apply the automation schedule - FULLY FIXED VERSION"""
    mode = config.get('mode', 'solar')
    tz_name = config.get('timezone', 'America/New_York')
    
    # Get timezone
    try:
        tz = pytz.timezone(tz_name)
    except:
        print(f"Invalid timezone: {tz_name}, using America/New_York")
        tz = pytz.timezone('America/New_York')
    
    # Get current time - CRITICAL: must be timezone-aware
    now = datetime.now(tz)
    
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Mode: {mode}")
    
    # Calculate times based on mode
    if mode == 'solar':
        print("Calculating solar times...")
        open_time, close_time = calculate_solar_times(config)
        if open_time is None:
            print("✗ Failed to calculate solar times")
            return False
    else:  # fixed mode
        print("Using fixed times...")
        fixed = config.get('fixed', {})
        open_str = fixed.get('open', '07:00')
        close_str = fixed.get('close', '20:00')
        
        # Parse times
        try:
            open_t = datetime.strptime(open_str, '%H:%M').time()
            close_t = datetime.strptime(close_str, '%H:%M').time()
        except ValueError as e:
            print(f"✗ Error parsing times: {e}")
            return False
        
        # Create datetime objects for today - MUST be timezone-aware
        open_time = tz.localize(datetime.combine(now.date(), open_t))
        close_time = tz.localize(datetime.combine(now.date(), close_t))
        
        # If open time has passed today, schedule for tomorrow
        if open_time <= now:
            print(f"  Open time {open_str} has passed, scheduling for tomorrow")
            open_time = open_time + timedelta(days=1)
        
        # If close time has passed today, schedule for tomorrow
        if close_time <= now:
            print(f"  Close time {close_str} has passed, scheduling for tomorrow")
            close_time = close_time + timedelta(days=1)
    
    # Get open percentage
    open_percent = config.get('open_percent', 100)
    if open_percent == 0:
        open_percent = 100  # 0 means no cap
    
    print(f"\nSchedule for today:")
    print(f"  Open:  {open_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Close: {close_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Open %: {open_percent}")
    
    # CRITICAL VALIDATION: Ensure times are timezone-aware
    if open_time.tzinfo is None or close_time.tzinfo is None:
        print("✗ ERROR: Times are not timezone-aware!")
        return False
    
    # Remove existing timers
    remove_existing_timers()
    
    # Create new timers - passing now for validation
    print("\nCreating new timers...")
    open_created = create_timer(
        "coopdoor-open",
        open_time,
        f"{COOP_DOOR_CMD} open {open_percent}",
        now
    )
    
    close_created = create_timer(
        "coopdoor-close",
        close_time,
        f"{COOP_DOOR_CMD} close",
        now
    )
    
    # Verify timers were created
    print("\nVerifying timers...")
    result = subprocess.run(
        ["systemctl", "list-timers", "--all", "--no-pager"],
        capture_output=True,
        text=True
    )
    
    found_open = False
    found_close = False
    
    for line in result.stdout.split('\n'):
        if 'coopdoor-open' in line:
            print(f"  ✓ Open timer: {line.strip()}")
            found_open = True
        if 'coopdoor-close' in line:
            print(f"  ✓ Close timer: {line.strip()}")
            found_close = True
    
    if not found_open and open_created:
        print("  ⚠ Warning: Open timer created but not found in list")
    if not found_close and close_created:
        print("  ⚠ Warning: Close timer created but not found in list")
    
    success = (open_created or close_created)
    return success


def main():
    print("=" * 50)
    print("CoopDoor Schedule Apply (FULLY FIXED)")
    print(f"Running at: {datetime.now()}")
    print("=" * 50)
    print()
    
    # Load config
    try:
        config = load_config()
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        sys.exit(1)
    
    # Apply schedule
    try:
        success = apply_schedule(config)
    except Exception as e:
        print(f"\n✗ Exception while applying schedule: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    if success:
        print("\n" + "=" * 50)
        print("✓ Schedule applied successfully")
        print("=" * 50)
        sys.exit(0)
    else:
        print("\n" + "=" * 50)
        print("✗ Failed to apply schedule")
        print("=" * 50)
        sys.exit(1)


if __name__ == "__main__":
    main()
