#!/usr/bin/env python3
"""
Recomputes and installs today's timers/services for open/close.
Run on boot and daily (via systemd timer).
"""
from __future__ import annotations
import json, subprocess, sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from astral import LocationInfo
from astral.sun import sun
import zoneinfo

CONF_DIR = Path("/etc/coopdoor")
CONF_DIR.mkdir(parents=True, exist_ok=True)
CONF = CONF_DIR / "automation.json"

SYSTEMD = Path("/etc/systemd/system")
OPEN_SVC = SYSTEMD / "coopdoor-open.service"
CLOSE_SVC = SYSTEMD / "coopdoor-close.service"
APPLY_SVC = SYSTEMD / "coopdoor-apply-schedule.service"
APPLY_TIMER = SYSTEMD / "coopdoor-apply-schedule.timer"
OPEN_TIMER = SYSTEMD / "coopdoor-open.timer"
CLOSE_TIMER = SYSTEMD / "coopdoor-close.timer"

def load_cfg() -> dict[str, Any]:
    if not CONF.exists():
        return {"mode":"fixed","fixed":{"open":"07:00","close":"20:30"},"timezone":"UTC","open_percent":100}
    try:
        return json.loads(CONF.read_text())
    except Exception:
        return {"mode":"fixed","fixed":{"open":"07:00","close":"20:30"},"timezone":"UTC","open_percent":100}

def sys_tz() -> str:
    try: return Path("/etc/timezone").read_text().strip()
    except Exception: return "UTC"

def compute_today(cfg: dict[str, Any]) -> tuple[str,str,str]:
    tz = (cfg.get("timezone") or sys_tz()) or "UTC"
    tzinfo = zoneinfo.ZoneInfo(tz)
    if cfg.get("mode") == "solar":
        loc = cfg.get("location")
        if not loc: raise SystemExit("solar mode requires cfg.location")
        li = LocationInfo(latitude=float(loc["lat"]), longitude=float(loc["lon"]), timezone=tz)
        sol = cfg.get("solar") or {}
        s = sun(li.observer, date=date.today(), tzinfo=tzinfo)
        open_hm = (s["sunrise"] + timedelta(minutes=int(sol.get("sunrise_offset_min",0)))).strftime("%H:%M")
        close_hm = (s["sunset"] + timedelta(minutes=int(sol.get("sunset_offset_min",0)))).strftime("%H:%M")
        return open_hm, close_hm, tz
    fx = cfg.get("fixed") or {"open":"07:00","close":"20:30"}
    return str(fx["open"]), str(fx["close"]), tz

def write_if_changed(path: Path, content: str) -> None:
    old = path.read_text() if path.exists() else None
    if old != content:
        path.write_text(content)

def ensure_action_services():
    open_service = "[Unit]\nDescription=Open Coop Door (API)\nAfter=coopdoor-api.service\n[Service]\nType=oneshot\nExecStart=curl -sS -X POST http://127.0.0.1:8080/open\n"
    close_service = "[Unit]\nDescription=Close Coop Door (API)\nAfter=coopdoor-api.service\n[Service]\nType=oneshot\nExecStart=curl -sS -X POST http://127.0.0.1:8080/close\n"
    write_if_changed(OPEN_SVC, open_service)
    write_if_changed(CLOSE_SVC, close_service)

def ensure_apply_timer():
    apply_service = "[Unit]\nDescription=Apply Coop Door schedule (recompute timers)\nAfter=coopdoor-api.service\n[Service]\nType=oneshot\nExecStart=/opt/coopdoor/.venv/bin/python3 /opt/coopdoor/schedule_apply.py\n"
    apply_timer = "[Unit]\nDescription=Daily schedule apply at 00:05\n[Timer]\nOnCalendar=*-*-* 00:05:00\nPersistent=true\nUnit=coopdoor-apply-schedule.service\n[Install]\nWantedBy=timers.target\n"
    write_if_changed(APPLY_SVC, apply_service)
    write_if_changed(APPLY_TIMER, apply_timer)

def install_timers(open_hm: str, close_hm: str) -> None:
    open_timer = f"[Unit]\nDescription=Open Coop Door at {open_hm}\n[Timer]\nOnCalendar=*-*-* {open_hm}:00\nPersistent=true\nUnit=coopdoor-open.service\n[Install]\nWantedBy=timers.target\n"
    close_timer = f"[Unit]\nDescription=Close Coop Door at {close_hm}\n[Timer]\nOnCalendar=*-*-* {close_hm}:00\nPersistent=true\nUnit=coopdoor-close.service\n[Install]\nWantedBy=timers.target\n"
    write_if_changed(OPEN_TIMER, open_timer)
    write_if_changed(CLOSE_TIMER, close_timer)

def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)

def reload_systemd():
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "coopdoor-apply-schedule.timer")
    run("systemctl", "enable", "--now", "coopdoor-open.timer")
    run("systemctl", "enable", "--now", "coopdoor-close.timer")

def main():
    cfg = load_cfg()
    ensure_action_services()
    ensure_apply_timer()
    open_hm, close_hm, tz = compute_today(cfg)
    install_timers(open_hm, close_hm)
    reload_systemd()
    print(json.dumps({"ok":True,"open":open_hm,"close":close_hm,"tz":tz}))

if __name__ == "__main__":
    main()
