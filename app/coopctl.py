#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, socket, subprocess, sys, time
from pathlib import Path
from typing import Any, Optional

HOME = Path.home()
RUNTIME = HOME / ".cache" / "coopdoor"
SOCK = RUNTIME / "door.sock"
PID = RUNTIME / "coopd.pid"
LOG = RUNTIME / "coopd.log"
CFG_PATH = HOME / ".config" / "coopdoor" / "config.json"
DAEMON = Path("/opt/coopdoor/coopd.py")
VENV_PY = Path("/opt/coopdoor/.venv/bin/python3")

DEFAULT_CFG = {
  "mac": "00:80:E1:22:EE:F2",
  "adapter": "hci0",
  "connect_timeout": 15,
  "base_pulses": 14,
  "pulse_interval": 2.0,
  "home_before_open": False,
  "min_pause_after_action": 1.0
}

def load_cfg() -> dict:
    try:
        data = json.loads(CFG_PATH.read_text())
        for k, v in DEFAULT_CFG.items():
            data.setdefault(k, v)
        return data
    except Exception:
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CFG_PATH.write_text(json.dumps(DEFAULT_CFG, indent=2))
        return DEFAULT_CFG.copy()

def save_cfg(d: dict) -> None:
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CFG_PATH.write_text(json.dumps(d, indent=2))

def rpc(req: dict, timeout: float = 2.0) -> Optional[dict[str, Any]]:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(SOCK))
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            buf = s.recv(65536)
        return json.loads(buf.decode("utf-8"))
    except Exception:
        return None

def status_only() -> dict[str, Any]:
    return rpc({"cmd": "status"}) or {"connected": False}

def _reuse_existing_if_alive(connect_timeout: int) -> bool:
    try:
        if PID.exists():
            pid = int((PID.read_text().strip() or "0"))
            if pid > 0:
                os.kill(pid, 0)
                deadline = time.time() + int(connect_timeout)
                while time.time() < deadline:
                    st = status_only()
                    if st.get("connected"): return True
                    time.sleep(0.2)
                return False
    except Exception:
        pass
    return False

def start_daemon() -> bool:
    cfg = load_cfg()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if status_only().get("connected"):
        return True
    if _reuse_existing_if_alive(int(cfg.get("connect_timeout", 15))):
        return True
    cmd = [str(VENV_PY), str(DAEMON),
           "--mac", cfg["mac"],
           "--adapter", cfg.get("adapter","hci0"),
           "--connect-timeout", str(int(cfg.get("connect_timeout", 15))),
           "--sock", str(SOCK)]
    with open(LOG, "a") as lf:
        subprocess.Popen(cmd, stdout=lf, stderr=lf, close_fds=True, start_new_session=True)
    deadline = time.time() + int(cfg.get("connect_timeout", 15))
    while time.time() < deadline:
        st = status_only()
        if st.get("connected"):
            return True
        time.sleep(0.2)
    return False

def stop_daemon() -> None:
    _ = rpc({"cmd": "shutdown"}, timeout=1.0)
    deadline = time.time() + 3.0
    while time.time() < deadline and SOCK.exists():
        time.sleep(0.05)

def _open_percent(percent: float) -> None:
    cfg = load_cfg()
    print("Connecting to device...")
    if not start_daemon():
        print(f"Failed to connect within {cfg.get('connect_timeout',15)}s.")
        sys.exit(1)
    print("Connected")
    if bool(cfg.get("home_before_open", False)):
        _ = rpc({"cmd":"close", "one_shot": False}, timeout=4.0)
        time.sleep(float(cfg.get("min_pause_after_action", 1.0)))
    pct = max(0.0, min(100.0, float(percent)))
    base = int(cfg.get("base_pulses", 14))
    pint = float(cfg.get("pulse_interval", 2.0))
    pulses = max(1, int(round(base * (pct/100.0))))
    print(f"Opening {pct:.1f}% → {pulses} pulse(s) @ {pint:.2f}s")
    total = max(6.0, pulses*pint + 3.0)
    res = rpc({"cmd":"open_pulses", "pulses": pulses, "interval": pint, "one_shot": True}, timeout=total)
    if not res: print("Disconnected"); sys.exit(1)
    if res.get("started"): print("Started.")
    else: print(res)

def _open_pulses(n: int, interval: float | None) -> None:
    cfg = load_cfg()
    print("Connecting to device...")
    if not start_daemon():
        print(f"Failed to connect within {cfg.get('connect_timeout',15)}s.")
        sys.exit(1)
    print("Connected")
    pint = float(interval if interval is not None else cfg.get("pulse_interval", 2.0))
    n = max(1, int(n))
    print(f"Opening (raw) → {n} pulse(s) @ {pint:.2f}s")
    total = max(6.0, n*pint + 3.0)
    res = rpc({"cmd":"open_pulses", "pulses": n, "interval": pint, "one_shot": True}, timeout=total)
    if not res: print("Disconnected"); sys.exit(1)
    if res.get("started"): print("Started.")
    else: print(res)

def _close() -> None:
    cfg = load_cfg()
    print("Connecting to device...")
    if not start_daemon():
        print(f"Failed to connect within {cfg.get('connect_timeout',15)}s.")
        sys.exit(1)
    print("Connected")
    res = rpc({"cmd":"close", "one_shot": True}, timeout=5.0)
    if not res: print("Disconnected"); sys.exit(1)
    print("Close sent.")

def _config_show() -> None:
    print(json.dumps(load_cfg(), indent=2))

def _config_set(kv: list[str]) -> None:
    cfg = load_cfg()
    for item in kv:
        if "=" not in item:
            print(f"Invalid --set '{item}', expected key=value"); sys.exit(2)
        k, v = item.split("=", 1)
        if v.lower() in ("true","false"): val = v.lower()=="true"
        else:
            try:
                if "." in v: val = float(v)
                else: val = int(v)
            except ValueError:
                val = v
        cfg[k] = val
    save_cfg(cfg); print("Updated config."); _config_show()

def _diag(verbose: bool) -> None:
    print("== CONFIG =="); _config_show()
    print("\n== STATUS =="); print(status_only())
    print("\n== TAIL LOG ==")
    try:
        if LOG.exists():
            lines = LOG.read_text().splitlines()[-60:]
            for ln in lines: print(ln)
        else:
            print("(no log)")
    except Exception as e:
        print(f"(unable to read log: {e})")
    if verbose:
        print("\n== ENV =="); print(f"Python: {sys.executable}"); print(f"PATH: {os.environ.get('PATH')}")

def main() -> None:
    ap = argparse.ArgumentParser(prog="coop-door")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("connect")
    sub.add_parser("disconnect")
    sp_open = sub.add_parser("open"); sp_open.add_argument("percent", type=float)
    sp_raw  = sub.add_parser("open-pulses"); sp_raw.add_argument("pulses", type=int); sp_raw.add_argument("--interval", type=float, default=None)
    sub.add_parser("close")
    sp_cfg = sub.add_parser("config"); sp_cfg.add_argument("--set", nargs="*", default=[])
    sp_diag= sub.add_parser("diag"); sp_diag.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.cmd=="status": print(status_only()); return
    if args.cmd=="connect": print("Connected" if start_daemon() else f"Failed to connect within {load_cfg().get('connect_timeout',15)}s."); return
    if args.cmd=="disconnect": stop_daemon(); print("Disconnected"); return
    if args.cmd=="open": _open_percent(args.percent); return
    if args.cmd=="open-pulses": _open_pulses(args.pulses, args.interval); return
    if args.cmd=="close": _close(); return
    if args.cmd=="config": _config_set(args.set) if args.set else _config_show(); return
    if args.cmd=="diag": _diag(args.verbose); return

if __name__ == "__main__":
    main()
