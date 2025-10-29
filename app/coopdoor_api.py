#!/usr/bin/env python3
from __future__ import annotations

import ast, json, os, re, time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from astral import LocationInfo
from astral.sun import sun
import pgeocode
import zoneinfo

# Import shared modules (DRY)
from shared_config import (
    CONF_DIR, AUTOMATION_PATH, DEVICE_CONFIG_PATH, UI_CONFIG_PATH,
    BACKUP_DIR, SYSTEMD_DIR, system_timezone, run_command
)
from door_state import (
    percent_to_pulses, save_last_action, get_last_action,
    get_door_state, update_door_position, reset_door_position
)

TOKEN = os.getenv("COOPDOOR_TOKEN", "").strip()
CLI = "coop-door"

# Ensure directories exist
CONF_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

OPEN_SVC  = SYSTEMD_DIR / "coopdoor-open.service"
CLOSE_SVC = SYSTEMD_DIR / "coopdoor-close.service"
APPLY_SVC = SYSTEMD_DIR / "coopdoor-apply-schedule.service"
APPLY_TIMER = SYSTEMD_DIR / "coopdoor-apply-schedule.timer"

app = FastAPI(title="Coop Door API")
app.mount("/ui", StaticFiles(directory="/opt/coopdoor/ui", html=True), name="ui")

@app.get("/")
def _root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")

def _require_auth_if_configured(request: Request) -> None:
    if not TOKEN: return
    auth = request.headers.get("authorization","")
    if not auth.startswith("Bearer "): raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    if auth.removeprefix("Bearer ").strip() != TOKEN: raise HTTPException(status_code=403, detail="Forbidden")

def _status_dict_from_literal(text: str) -> dict[str, Any]:
    try:
        val = ast.literal_eval(text)
        return val if isinstance(val, dict) else {"raw": text}
    except Exception:
        return {"raw": text}

def _parse_diag(output: str) -> dict[str, Any]:
    sections: dict[str, list[str]] = {"CONFIG": [], "STATUS": [], "TAIL LOG": []}
    current: str | None = None
    for line in output.splitlines():
        m = re.match(r"^==\s*(CONFIG|STATUS|TAIL LOG)\s*==\s*$", line.strip())
        if m:
            current = m.group(1); continue
        if current: sections[current].append(line)
    cfg_txt = "\n".join(sections["CONFIG"]).strip()
    try: config = json.loads(cfg_txt) if cfg_txt else {}
    except json.JSONDecodeError: config = {"raw": cfg_txt} if cfg_txt else {}
    status_txt = "\n".join(sections["STATUS"]).strip()
    status = _status_dict_from_literal(status_txt) if status_txt else {}
    connected = bool(status.get("connected")) if isinstance(status, dict) and "connected" in status else None
    logs = []
    for ln in sections["TAIL LOG"]:
        ln = ln.strip()
        m = re.match(r"^\[(.+?)\]\s+(.*)$", ln)
        if m: logs.append({"ts": m.group(1), "msg": m.group(2)})
        elif ln: logs.append({"ts": "", "msg": ln})
    return {"connected": connected, "config": config, "status": status, "logs": logs[-100:]}

def _geocode_zip(zip_code: str, country: str = "US") -> tuple[float, float]:
    nomi = pgeocode.Nominatim(country.upper())
    rec = nomi.query_postal_code(str(zip_code))
    try: lat = float(rec.latitude); lon = float(rec.longitude)
    except Exception: raise HTTPException(status_code=400, detail="Invalid ZIP/country; could not geocode.")
    if any(map(lambda x: x is None or (isinstance(x,float) and (x != x)), (lat,lon))):
        raise HTTPException(status_code=400, detail="Invalid ZIP/country; could not geocode.")
    return lat, lon

def _load_cfg() -> dict[str, Any]:
    if not AUTOMATION_PATH.exists():
        return {"mode":"fixed","fixed":{"open":"07:00","close":"20:30"},"timezone":system_timezone(),"open_percent":100}
    try: obj = json.loads(AUTOMATION_PATH.read_text())
    except Exception: obj = {}
    if "open_percent" not in obj: obj["open_percent"] = 100
    return obj

def _save_cfg(obj: dict[str, Any]) -> None:
    AUTOMATION_PATH.write_text(json.dumps(obj, indent=2))

def _effective_open_percent(requested: int | None) -> tuple[int, int]:
    cfg = _load_cfg()
    cap = int(cfg.get("open_percent", 100))
    if cap <= 0:
        req = 100 if requested is None else requested
        eff = max(0, min(100, int(req)))
        return eff, 0
    eff = max(0, min(100, cap))
    return eff, eff

def _compute_today_times(cfg: dict[str, Any]) -> tuple[str, str, str]:
    tz = (cfg.get("timezone") or system_timezone()) or "UTC"
    tzinfo = zoneinfo.ZoneInfo(tz)
    if cfg.get("mode") == "solar":
        loc = cfg.get("location")
        if not loc: raise HTTPException(status_code=400, detail="Solar mode requires saving ZIP first.")
        sr_off = int((cfg.get("solar") or {}).get("sunrise_offset_min", 0))
        ss_off = int((cfg.get("solar") or {}).get("sunset_offset_min", 0))
        li = LocationInfo(latitude=float(loc["lat"]), longitude=float(loc["lon"]), timezone=tz)
        s = sun(li.observer, date=date.today(), tzinfo=tzinfo)
        return (s["sunrise"] + timedelta(minutes=sr_off)).strftime("%H:%M"), (s["sunset"] + timedelta(minutes=ss_off)).strftime("%H:%M"), tz
    fx = cfg.get("fixed") or {"open": "07:00", "close": "20:30"}
    return str(fx["open"]), str(fx["close"]), tz

@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str: return "ok"

@app.get("/status")
def status_(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    rc, out, err = run_command([CLI,"status"], timeout=15.0)
    if rc != 0:
        return JSONResponse({
            "ok": False,
            "rc": rc,
            "stderr": err,
            "stdout": out,
            "door_state": get_door_state(),
            "last_action": get_last_action()
        }, status_code=502)
    data = _status_dict_from_literal(out)
    data["ok"] = True
    data["door_state"] = get_door_state()
    data["last_action"] = get_last_action()
    return JSONResponse(data)

@app.get("/diag")
def diag_(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    rc, out, err = run_command([CLI,"diag"], timeout=45.0)
    if rc != 0: raise HTTPException(status_code=500, detail=f"diag failed: {err or out}")
    return JSONResponse(_parse_diag(out))

@app.post("/open")
def open_(request: Request, percent: int | None = None) -> JSONResponse:
    _require_auth_if_configured(request)
    
    eff, cap = _effective_open_percent(percent)
    
    # Get current state for delta tracking
    current_state = get_door_state()
    base_pulses = 14  # Could load from config if needed
    new_pulses = percent_to_pulses(eff, base_pulses)
    
    rc, out, err = run_command([CLI,"open",str(eff)])
    success = (rc == 0)
    
    last_event = {
        "cmd": "open",
        "requested_percent": eff,
        "actual_pulses": new_pulses if success else 0,
        "delta_pulses": new_pulses - current_state.get("position_pulses", 0) if success else 0,
        "ok": success,
        "at": datetime.now(timezone.utc).isoformat(),
        "source": "api_manual",
        "error": err if not success else None
    }
    
    # PERSIST the action (this was missing - root cause of solar not showing!)
    save_last_action(last_event)
    if success:
        update_door_position(new_pulses, base_pulses)
    
    return JSONResponse({
        "ok": success,
        "rc": rc,
        "stdout": out,
        "stderr": err,
        "percent": eff,
        "enforced_cap": cap,
        "last_event": last_event,
        "door_state": get_door_state()
    })

@app.post("/close")
def close_(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    
    rc, out, err = run_command([CLI,"close"])
    success = (rc == 0)
    
    last_event = {
        "cmd": "close",
        "requested_percent": None,
        "actual_pulses": 0,
        "delta_pulses": 0,
        "ok": success,
        "at": datetime.now(timezone.utc).isoformat(),
        "source": "api_manual",
        "error": err if not success else None
    }
    
    # PERSIST the action (this was missing!)
    save_last_action(last_event)
    if success:
        update_door_position(0)
    
    return JSONResponse({
        "ok": success,
        "rc": rc,
        "stdout": out,
        "stderr": err,
        "last_event": last_event,
        "door_state": get_door_state()
    })

@app.get("/door/state")
def get_door_state_endpoint(request: Request) -> JSONResponse:
    """Get current door position and last action."""
    _require_auth_if_configured(request)
    return JSONResponse({
        "door_state": get_door_state(),
        "last_action": get_last_action()
    })

@app.post("/door/reset")
def reset_door_state_endpoint(request: Request) -> JSONResponse:
    """Reset door position to closed (after manual adjustment)."""
    _require_auth_if_configured(request)
    state = reset_door_position()
    return JSONResponse({
        "ok": True,
        "door_state": state,
        "message": "Door position reset to closed (0 pulses)"
    })

@app.get("/automation")
def get_automation(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    return JSONResponse(_load_cfg())

@app.put("/automation")
def put_automation(request: Request, payload: dict[str, Any]) -> JSONResponse:
    _require_auth_if_configured(request)
    if "open_percent" in payload:
        try: op = int(payload["open_percent"])
        except Exception: raise HTTPException(status_code=400, detail="open_percent must be integer")
        payload["open_percent"] = max(0, min(100, op))
    mode = payload.get("mode", "fixed")
    if mode not in ("fixed", "solar"):
        raise HTTPException(status_code=400, detail="mode must be 'fixed' or 'solar'")
    payload["mode"] = mode
    if mode == "solar":
        if "zip" in payload:
            z = str(payload["zip"]).strip()
            c = payload.get("country", "US")
            lat, lon = _geocode_zip(z, c)
            payload["location"] = {"lat": lat, "lon": lon, "zip": z, "country": c}
            del payload["zip"]
            if "country" in payload: del payload["country"]
    _save_cfg(payload)
    return JSONResponse({"ok": True, "config": payload})

@app.post("/automation/apply")
def apply_automation(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    rc, out, err = run_command(["sudo", "systemctl", "start", "coopdoor-apply-schedule.service"], timeout=30.0)
    if rc != 0: raise HTTPException(status_code=500, detail=f"Failed to apply: {err or out}")
    return JSONResponse({"ok": True, "stdout": out})

@app.get("/schedule/preview")
def preview_schedule(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    cfg = _load_cfg()
    try: o, c, tz = _compute_today_times(cfg)
    except HTTPException as e: return JSONResponse({"error": e.detail, "timezone": system_timezone(), "mode": cfg.get("mode", "fixed")}, status_code=400)
    except Exception as e: return JSONResponse({"error": str(e), "timezone": system_timezone(), "mode": cfg.get("mode", "fixed")}, status_code=500)
    return JSONResponse({"open_time": o, "close_time": c, "timezone": tz, "open_percent_cap": cfg.get("open_percent", 100), "mode": cfg.get("mode", "fixed")})

@app.get("/config/backups")
def list_backups(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    backups = []
    try:
        for f in sorted(BACKUP_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            backups.append({
                "name": f.stem,
                "timestamp": int(f.stat().st_mtime),
                "size": f.stat().st_size
            })
    except Exception as e:
        return JSONResponse({"error": str(e), "backups": []}, status_code=500)
    return JSONResponse({"backups": backups})

@app.post("/config/backup")
def create_backup(request: Request, payload: dict[str, Any]) -> JSONResponse:
    _require_auth_if_configured(request)
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Backup name is required")
    # Sanitize filename
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    if not name:
        raise HTTPException(status_code=400, detail="Invalid backup name")
    
    backup_path = BACKUP_DIR / f"{name}.json"
    try:
        cfg = _load_cfg()
        backup_path.write_text(json.dumps(cfg, indent=2))
        return JSONResponse({"ok": True, "name": name, "path": str(backup_path)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")

@app.post("/config/restore")
def restore_backup(request: Request, payload: dict[str, Any]) -> JSONResponse:
    _require_auth_if_configured(request)
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Backup name is required")
    
    # Sanitize filename
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    backup_path = BACKUP_DIR / f"{name}.json"
    
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    
    try:
        cfg = json.loads(backup_path.read_text())
        _save_cfg(cfg)
        return JSONResponse({"ok": True, "name": name, "config": cfg})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

@app.delete("/config/backup")
def delete_backup(request: Request, payload: dict[str, Any]) -> JSONResponse:
    _require_auth_if_configured(request)
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Backup name is required")
    
    # Sanitize filename
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    backup_path = BACKUP_DIR / f"{name}.json"
    
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    
    try:
        backup_path.unlink()
        return JSONResponse({"ok": True, "name": name})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

# Unified config endpoint for UI compatibility
def _load_device_config() -> dict[str, Any]:
    if not DEVICE_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(DEVICE_CONFIG_PATH.read_text())
    except Exception:
        return {}

def _save_device_config(cfg: dict[str, Any]) -> None:
    DEVICE_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))

def _load_ui_config() -> dict[str, Any]:
    if not UI_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(UI_CONFIG_PATH.read_text())
    except Exception:
        return {}

def _save_ui_config(cfg: dict[str, Any]) -> None:
    UI_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))

@app.get("/config")
def get_unified_config(request: Request) -> JSONResponse:
    """Get unified config with automation, ble, and ui settings"""
    _require_auth_if_configured(request)
    
    # Load automation config
    automation = _load_cfg()
    
    # Load device/BLE config and map to UI expected fields
    device_cfg = _load_device_config()
    ble = {
        "adapter": device_cfg.get("adapter", "hci0"),
        "mac": device_cfg.get("mac", ""),
        "connect_timeout": device_cfg.get("connect_timeout", 15),
        "min_pause_after_action": device_cfg.get("min_pause_after_action", 1.0),
        "retry_attempts": device_cfg.get("retry_attempts", 2),
        "retry_initial_delay_ms": device_cfg.get("retry_initial_delay_ms", 400)
    }
    
    # Load UI config
    ui = _load_ui_config()
    
    return JSONResponse({
        "automation": automation,
        "ble": ble,
        "ui": ui
    })

@app.put("/config")
def put_unified_config(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Save unified config with automation, ble, and ui settings"""
    _require_auth_if_configured(request)
    
    # Save automation config if present
    if "automation" in payload:
        auto = payload["automation"]
        if "open_percent" in auto:
            try:
                op = int(auto["open_percent"])
            except Exception:
                raise HTTPException(status_code=400, detail="open_percent must be integer")
            auto["open_percent"] = max(0, min(100, op))
        
        mode = auto.get("mode", "fixed")
        if mode not in ("fixed", "solar"):
            raise HTTPException(status_code=400, detail="mode must be 'fixed' or 'solar'")
        auto["mode"] = mode
        
        if mode == "solar" and "zip" in auto:
            z = str(auto["zip"]).strip()
            c = auto.get("country", "US")
            lat, lon = _geocode_zip(z, c)
            auto["location"] = {"lat": lat, "lon": lon, "zip": z, "country": c}
            del auto["zip"]
            if "country" in auto:
                del auto["country"]
        
        _save_cfg(auto)
    
    # Save BLE/device config if present
    if "ble" in payload:
        device_cfg = _load_device_config()
        ble = payload["ble"]
        
        # Map UI fields to device config fields
        if "adapter" in ble:
            device_cfg["adapter"] = ble["adapter"]
        if "mac" in ble:
            device_cfg["mac"] = ble["mac"]
        if "connect_timeout" in ble:
            device_cfg["connect_timeout"] = int(ble["connect_timeout"])
        if "min_pause_after_action" in ble:
            device_cfg["min_pause_after_action"] = float(ble["min_pause_after_action"])
        if "retry_attempts" in ble:
            device_cfg["retry_attempts"] = int(ble["retry_attempts"])
        if "retry_initial_delay_ms" in ble:
            device_cfg["retry_initial_delay_ms"] = int(ble["retry_initial_delay_ms"])
        
        _save_device_config(device_cfg)
    
    # Save UI config if present
    if "ui" in payload:
        _save_ui_config(payload["ui"])
    
    return JSONResponse({"ok": True, "saved": payload})