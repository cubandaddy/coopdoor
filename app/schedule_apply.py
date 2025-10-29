#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from astral import LocationInfo
from astral.sun import sun
import zoneinfo

# Import shared modules (DRY)
from shared_config import (
    CONF_DIR, AUTOMATION_PATH, SYSTEMD_DIR,
    system_timezone, run_command
)

OPEN_SVC = SYSTEMD_DIR / "coopdoor-open.service"
CLOSE_SVC = SYSTEMD_DIR / "coopdoor-close.service"
APPLY_SVC = SYSTEMD_DIR / "coopdoor-apply-schedule.service"
APPLY_TIMER = SYSTEMD_DIR / "coopdoor-apply-schedule.timer"
OPEN_TIMER = SYSTEMD_DIR / "coopdoor-open.timer"
CLOSE_TIMER = SYSTEMD_DIR / "coopdoor-close.timer"

def write_if_changed(path: Path, content: str) -> None:
    old = path.read_text() if path.exists() else None
    if old != content:
        path.write_text(content)

def ensure_action_services() -> None:
    open_service = """[Unit]
Description=Open Coop Door (API)
After=coopdoor-api.service
[Service]
Type=oneshot
ExecStart=curl -sS -X POST http://127.0.0.1:8080/open
"""
    close_service = """[Unit]
Description=Close Coop Door (API)
After=coopdoor-api.service
[Service]
Type=oneshot
ExecStart=curl -sS -X POST http://127.0.0.1:8080/close
"""
    write_if_changed(OPEN_SVC, open_service)
    write_if_changed(CLOSE_SVC, close_service)

def ensure_apply_timer() -> None:
    apply_service = """[Unit]
Description=Apply Coop Door schedule (recompute timers)
After=coopdoor-api.service
[Service]
Type=oneshot
ExecStart=/opt/coopdoor/.venv/bin/python3 /opt/coopdoor/schedule_apply.py
"""
    apply_timer = """[Unit]
Description=Daily schedule apply at 00:05
[Timer]
OnCalendar=*-*-* 00:05:00
Persistent=true
Unit=coopdoor-apply-schedule.service
[Install]
WantedBy=timers.target
"""
    write_if_changed(APPLY_SVC, apply_service)
    write_if_changed(APPLY_TIMER, apply_timer)
    run_command(["systemctl", "daemon-reload"])
    run_command(["systemctl", "enable", "--now", "coopdoor-apply-schedule.timer"])

def set_fixed(open_hm: str, close_hm: str, tz: str) -> None:
    open_timer = f"""[Unit]
Description=Daily open door ({open_hm} {tz})
[Timer]
OnCalendar=*-*-* {open_hm}:00
Persistent=true
Unit=coopdoor-open.service
[Install]
WantedBy=timers.target
"""
    close_timer = f"""[Unit]
Description=Daily close door ({close_hm} {tz})
[Timer]
OnCalendar=*-*-* {close_hm}:00
Persistent=true
Unit=coopdoor-close.service
[Install]
WantedBy=timers.target
"""
    write_if_changed(OPEN_TIMER, open_timer)
    write_if_changed(CLOSE_TIMER, close_timer)
    run_command(["systemctl", "daemon-reload"])
    ensure_action_services()
    run_command(["systemctl", "enable", "--now", "coopdoor-open.timer", "coopdoor-close.timer"])

def set_solar(lat: float, lon: float, tz: str, sr_off: int, ss_off: int) -> None:
    tzinfo = zoneinfo.ZoneInfo(tz)
    loc = LocationInfo(latitude=lat, longitude=lon, timezone=tz)
    s = sun(loc.observer, date=date.today(), tzinfo=tzinfo)
    open_hm = (s["sunrise"] + timedelta(minutes=sr_off)).astimezone(tzinfo).strftime("%H:%M")
    close_hm = (s["sunset"] + timedelta(minutes=ss_off)).astimezone(tzinfo).strftime("%H:%M")
    set_fixed(open_hm, close_hm, tz)

def main() -> None:
    ensure_apply_timer()
    ensure_action_services()
    tz = system_timezone()

    if not AUTOMATION_PATH.exists():
        set_fixed("07:00", "20:30", tz)
        print("applied: default fixed 07:00/20:30")
        return

    cfg = json.loads(AUTOMATION_PATH.read_text())
    mode = cfg.get("mode", "fixed")
    tz = cfg.get("timezone", tz) or tz
    if mode == "fixed":
        fx = cfg.get("fixed", {})
        set_fixed(fx["open"], fx["close"], tz)
        print(f"applied: fixed open {fx['open']} close {fx['close']} {tz}")
    elif mode == "solar":
        loc = cfg.get("location", {})
        sol = cfg.get("solar", {})
        set_solar(float(loc["lat"]), float(loc["lon"]), tz,
                  int(sol.get("sunrise_offset_min", 0)), int(sol.get("sunset_offset_min", 0)))
        print("applied: solar schedule")
    else:
        raise SystemExit("invalid mode")

if __name__ == "__main__":
    main()