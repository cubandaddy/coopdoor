#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from astral import LocationInfo
from astral.sun import sun
import pgeocode
import zoneinfo
from time import sleep as _sleep

# ----------------- constants & paths -----------------

TOKEN = os.getenv("COOPDOOR_TOKEN", "").strip()
CLI = "coop-door"

CONF_DIR = Path("/etc/coopdoor")
CONF_DIR.mkdir(parents=True, exist_ok=True)
AUTOMATION_PATH = CONF_DIR / "automation.json"

STATE_FILE = Path("/opt/coopdoor/last_event.json")

SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")
APPLY_SVC = SYSTEMD_UNIT_DIR / "coopdoor-apply-schedule.service"

# ----------------- app & static -----------------

app = FastAPI(title="Coop Door API")
app.mount("/ui", StaticFiles(directory="/opt/coopdoor/ui", html=True), name="ui")

@app.get("/")
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui/")

# ----------------- auth -----------------

def _require_auth_if_configured(request: Request) -> None:
    if not TOKEN:
        return
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    if auth.removeprefix("Bearer ").strip() != TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

# ----------------- helpers -----------------

def _run(args: list[str], timeout: float = 45.0) -> tuple[int, str, str]:
    proc = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

def _status_dict_from_literal(text: str) -> dict[str, Any]:
    # coop-door prints Python-literal-ish dicts sometimes
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
            current = m.group(1)
            continue
        if current:
            sections[current].append(line)

    cfg_txt = "\n".join(sections["CONFIG"]).strip()
    try:
        config = json.loads(cfg_txt) if cfg_txt else {}
    except json.JSONDecodeError:
        config = {"raw": cfg_txt} if cfg_txt else {}

    status_txt = "\n".join(sections["STATUS"]).strip()
    status = _status_dict_from_literal(status_txt) if status_txt else {}
    connected = bool(status.get("connected")) if isinstance(status, dict) and "connected" in status else None

    logs = []
    for ln in sections["TAIL LOG"]:
        ln = ln.strip()
        m = re.match(r"^\[(.+?)\]\s+(.*)$", ln)
        if m:
            logs.append({"ts": m.group(1), "msg": m.group(2)})
        elif ln:
            logs.append({"ts": "", "msg": ln})

    return {"connected": connected, "config": config, "status": status, "logs": logs[-200:]}

def _system_timezone() -> str:
    tz_file = Path("/etc/timezone")
    if tz_file.exists():
        try:
            return tz_file.read_text().strip()
        except Exception:
            pass
    return "UTC"

def _geocode_zip(zip_code: str, country: str = "US") -> tuple[float, float]:
    nomi = pgeocode.Nominatim(country.upper())
    rec = nomi.query_postal_code(str(zip_code))
    try:
        lat = float(rec.latitude)
        lon = float(rec.longitude)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ZIP/country; could not geocode.")
    if any((
        lat is None,
        lon is None,
        (isinstance(lat, float) and lat != lat),  # NaN
        (isinstance(lon, float) and lon != lon),
    )):
        raise HTTPException(status_code=400, detail="Invalid ZIP/country; could not geocode.")
    return lat, lon

def _load_cfg() -> dict[str, Any]:
    # Defaults
    obj: dict[str, Any]
    if not AUTOMATION_PATH.exists():
        obj = {
            "mode": "fixed",
            "fixed": {"open": "07:00", "close": "20:30"},
            "timezone": _system_timezone(),
            "open_percent": 100,  # 0 => no cap; >0 absolute cap
        }
    else:
        try:
            obj = json.loads(AUTOMATION_PATH.read_text())
        except Exception:
            obj = {}

    # Ensure keys exist
    obj.setdefault("open_percent", 100)
    obj.setdefault("api_retry_retries", 6)
    obj.setdefault("api_retry_initial_delay_ms", 300)  # 0.3s
    # Optional BLE daemon knobs that coop-door reads
    obj.setdefault("connect_timeout", 10)
    obj.setdefault("min_pause_after_action", 2)

    return obj

def _save_cfg(obj: dict[str, Any]) -> None:
    AUTOMATION_PATH.write_text(json.dumps(obj, indent=2))

def _read_event() -> dict[str, Any] | None:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        return None
    return None

def _save_event(cmd: str, requested: int | None, effective: int | None, ok: bool) -> dict[str, Any]:
    evt = {
        "cmd": cmd,
        "requested_percent": int(requested) if requested is not None else None,
        "effective_percent": int(effective) if effective is not None else None,
        "ok": bool(ok),
        "at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(evt))
        tmp.replace(STATE_FILE)  # atomic on same FS
    except Exception:
        pass
    return evt

def _effective_open_percent(requested: int | None) -> tuple[int, int]:
    """
    Returns (effective, enforced_cap).
    - If enforced cap == 0 → no cap: use requested (or 100 if None), clamp [0,100].
    - If enforced cap > 0 → absolute target: ignore requested; use cap.
    """
    cfg = _load_cfg()
    cap = int(cfg.get("open_percent", 100))
    if cap <= 0:
        req = 100 if requested is None else int(requested)
        eff = max(0, min(100, req))
        return eff, 0
    eff = max(0, min(100, cap))
    return eff, eff

def _wait_cooldown(seconds: float = 2.0) -> None:
    _sleep(max(0.0, seconds))

# --- BLE prescan helper to warm BlueZ cache (best-effort, ignore failures) ---
def _prescan_ble(seconds: float = 2.0) -> None:
    try:
        _run(["bluetoothctl", "--timeout", str(int(seconds)), "scan", "on"], timeout=seconds + 1)
        _run(["bluetoothctl", "scan", "off"], timeout=2.0)
    except Exception:
        pass

def _do_with_retry(args: list[str]) -> tuple[int, str, str]:
    """
    Targeted retry loop for transient BLE failures:
    - prescan before first attempt and before each retry
    - retries & initial delay can be overridden in /etc/coopdoor/automation.json
      via api_retry_retries (int) and api_retry_initial_delay_ms (int, ms)
    """
    cfg = _load_cfg()
    retries = int(cfg.get("api_retry_retries", 2))
    delay = float(int(cfg.get("api_retry_initial_delay_ms", 400))) / 1000.0
    backoff = 1.5

    _prescan_ble(2.0)
    print("[retry] attempt=0 start"); rc, out, err = _run(args)
    attempt = 0

    def _is_ble_retry(rc_: int, out_: str, err_: str) -> bool:
        blob = (out_ or "") + "\\n" + (err_ or "")
        return (rc_ != 0) and (
            "BleakDeviceNotFoundError" in blob or
            "Failed to connect within" in blob
        )

    while attempt < retries and _is_ble_retry(rc, out, err):
        _prescan_ble(2.0)
        _sleep(delay)
        print(f"[retry] attempt={attempt+1} start (delay={delay:.2f}s)")
        rc, out, err = _run(args)
        attempt += 1
        delay *= backoff

    return rc, out, err

def _compute_today_times(cfg: dict[str, Any]) -> tuple[str, str, str]:
    """
    Returns (open_hm, close_hm, tz). Uses current config (fixed|solar) for today's date.
    """
    tz = (cfg.get("timezone") or _system_timezone()) or "UTC"
    tzinfo = zoneinfo.ZoneInfo(tz)
    if cfg.get("mode") == "solar":
        loc = cfg.get("location")
        if not loc:
            raise HTTPException(status_code=400, detail="Solar mode requires location in config (save with ZIP first).")
        lat = float(loc["lat"])
        lon = float(loc["lon"])
        sol = cfg.get("solar") or {}
        sr_off = int(sol.get("sunrise_offset_min", 0))
        ss_off = int(sol.get("sunset_offset_min", 0))
        li = LocationInfo(latitude=lat, longitude=lon, timezone=tz)
        sdata = sun(li.observer, date=date.today(), tzinfo=tzinfo)
        open_hm = (sdata["sunrise"] + timedelta(minutes=sr_off)).strftime("%H:%M")
        close_hm = (sdata["sunset"] + timedelta(minutes=ss_off)).strftime("%H:%M")
        return open_hm, close_hm, tz
    # fixed
    fx = cfg.get("fixed") or {"open": "07:00", "close": "20:30"}
    return str(fx["open"]), str(fx["close"]), tz

# ----------------- endpoints -----------------

@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"

@app.get("/status")
def status_(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    rc, out, err = _run([CLI, "status"], timeout=15.0)
    if rc != 0:
        # Still return last_event to help the UI render something useful
        evt = _read_event()
        return JSONResponse({"ok": False, "rc": rc, "stderr": err, "stdout": out, "last_event": evt}, status_code=502)
    data = _status_dict_from_literal(out)
    data["ok"] = True
    evt = _read_event()
    if evt:
        data["last_event"] = evt
    return JSONResponse(data)

@app.get("/diag")
def diag_(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    rc, out, err = _run([CLI, "diag"], timeout=45.0)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"diag failed: {err or out}")
    return JSONResponse(_parse_diag(out))

@app.post("/open")
def open_(request: Request, percent: int | None = None) -> JSONResponse:
    _require_auth_if_configured(request)
    eff, cap = _effective_open_percent(percent)
    _wait_cooldown(2.0)  # short guard between opposite actions
    rc, out, err = _do_with_retry([CLI, "open", str(eff)])
    ok = (rc == 0)
    evt = _save_event("open", percent if percent is not None else eff, eff, ok)
    return JSONResponse({
        "ok": ok, "rc": rc, "stdout": out, "stderr": err,
        "percent": eff, "enforced_cap": cap,
        "last_event": evt
    }, status_code=(200 if ok else 502))

@app.post("/close")
def close_(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    _wait_cooldown(2.0)
    rc, out, err = _do_with_retry([CLI, "close"])
    ok = (rc == 0)
    evt = _save_event("close", 100, 0, ok)
    return JSONResponse({"ok": ok, "rc": rc, "stdout": out, "stderr": err, "last_event": evt},
                        status_code=(200 if ok else 502))

@app.get("/automation")
def get_automation(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    return JSONResponse(_load_cfg())

@app.put("/automation")
def put_automation(request: Request, payload: dict[str, Any]) -> JSONResponse:
    _require_auth_if_configured(request)

    # validate open_percent
    if "open_percent" in payload:
        try:
            op = int(payload["open_percent"])
        except Exception:
            raise HTTPException(status_code=400, detail="open_percent must be an integer 0..100")
        if not (0 <= op <= 100):
            raise HTTPException(status_code=400, detail="open_percent must be 0..100")

    mode = payload.get("mode")
    if mode not in {"fixed", "solar"}:
        raise HTTPException(status_code=400, detail="mode must be 'fixed' or 'solar'")

    # optional retry knobs
    if "api_retry_retries" in payload:
        payload["api_retry_retries"] = int(payload["api_retry_retries"])
    if "api_retry_initial_delay_ms" in payload:
        payload["api_retry_initial_delay_ms"] = int(payload["api_retry_initial_delay_ms"])

    # normalize timezone (optional)
    if "timezone" in payload and not payload["timezone"]:
        payload.pop("timezone", None)

    if mode == "fixed":
        fx = payload.get("fixed") or {}
        if "open" not in fx or "close" not in fx:
            raise HTTPException(status_code=400, detail="fixed.open and fixed.close (HH:MM) required")

    if mode == "solar":
        zip_code = payload.get("zip")
        country = (payload.get("country") or "US").upper()
        if zip_code:
            lat, lon = _geocode_zip(zip_code, country)
            payload["location"] = {"lat": lat, "lon": lon}
            payload.pop("zip", None)
            payload.pop("country", None)
        else:
            loc = payload.get("location") or {}
            if "lat" not in loc or "lon" not in loc:
                raise HTTPException(
                    status_code=400,
                    detail="Provide ZIP (+country) or location.lat/lon for solar mode",
                )
        sol = payload.get("solar") or {}
        payload["solar"] = {
            "sunrise_offset_min": int(sol.get("sunrise_offset_min", 0)),
            "sunset_offset_min": int(sol.get("sunset_offset_min", 0)),
        }

    if "open_percent" not in payload:
        payload["open_percent"] = int(_load_cfg().get("open_percent", 100))

    try:
        _save_cfg(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"write failed: {e}")

    return JSONResponse({"ok": True, "saved": payload})

@app.post("/automation/apply")
def apply_automation(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    # Requires sudoers rule for coop to start this unit without a password
    rc, out, err = _run(["sudo", "-n", "systemctl", "start", "coopdoor-apply-schedule.service"], timeout=30.0)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"apply failed: {err or out}")
    return JSONResponse({"ok": True, "started": True})

@app.get("/schedule/preview")
def schedule_preview(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    cfg = _load_cfg()
    open_hm, close_hm, tz = _compute_today_times(cfg)
    return JSONResponse({
        "mode": cfg.get("mode", "fixed"),
        "timezone": tz,
        "open_time": open_hm,
        "close_time": close_hm,
        "open_percent_cap": int(cfg.get("open_percent", 100)),
    })

@app.get("/version")
def version(request: Request) -> JSONResponse:
    _require_auth_if_configured(request)
    p = Path("/opt/coopdoor/VERSION.json")
    try:
        return JSONResponse(json.loads(p.read_text()))
    except Exception:
        return JSONResponse({"version": "dev"})

@app.get("/debug/env")
def debug_env(request: Request) -> JSONResponse:
    tz = _system_timezone()
    try:
        cfg = _load_cfg()
    except Exception:
        cfg = {}
    return JSONResponse({
        "token_required": bool(TOKEN),
        "timezone": tz,
        "cfg_mode": cfg.get("mode"),
        "cfg_open_percent": cfg.get("open_percent"),
        "cfg_api_retry_retries": cfg.get("api_retry_retries"),
        "cfg_api_retry_initial_delay_ms": cfg.get("api_retry_initial_delay_ms"),
    })
