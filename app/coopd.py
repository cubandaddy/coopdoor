#!/usr/bin/env python3
"""
CoopDoor BLE Daemon - Persistent Connection Mode

CHANGES FROM ORIGINAL:
- Removed one_shot parameter handling (daemon always persistent)
- Added exponential backoff on reconnection (prevents connection spam)
- Added connection health metrics (success rate tracking)
- Enhanced error recovery
- Better logging
"""
from __future__ import annotations
import argparse, asyncio, json, time, signal, fcntl, os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

CHAR_WR      = "00000000-8e22-4541-9d4c-21edae82ed19"
# Battery Configuration (G-80 specific)
CHAR_BATTERY = "00000001-8e22-4541-9d4c-21edae82ed19"  # Status characteristic (not standard battery service)
BATTERY_BYTE_OFFSET = 48  # Battery percentage is at byte 48 of status packet
OPEN_PAYLOAD = bytes.fromhex("002729e5682729e5680000000000000e340e3400000100000000000000000013")
CLOSE_PAYLOAD= bytes.fromhex("002a29e5682a29e5680000000000000e340e340000020000000000000000002a")

HOME = Path.home()
RUNTIME = HOME/".cache"/"coopdoor"
SOCK    = RUNTIME/"door.sock"
PIDF    = RUNTIME/"coopd.pid"
LOCKF   = RUNTIME/"coopd.lock"
LOGF    = RUNTIME/"coopd.log"

def _json(o: Any) -> bytes: return (json.dumps(o) + "\n").encode("utf-8")
def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with open(LOGF, "a", buffering=1) as f: f.write(f"[{ts}] {msg}\n")

def _get_lock():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    fh = open(LOCKF, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(str(os.getpid()))
        fh.flush()
        return fh
    except Exception:
        return None

from time import time as _now

@dataclass
class ConnectionMetrics:
    """NEW: Track connection health for monitoring."""
    connect_attempts: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    disconnections: int = 0
    last_connect_time: Optional[float] = None
    total_connected_time: float = 0.0

@dataclass
class State:
    connected: bool = False
    busy: bool = False
    op: Optional[str] = None
    eta: Optional[float] = None
    error: Optional[str] = None
    battery_percent: Optional[int] = None  # NEW: Battery percentage (0-100)
    battery_last_read: Optional[float] = None  # NEW: Timestamp of last battery read
    metrics: ConnectionMetrics = field(default_factory=ConnectionMetrics)  # NEW

class DoorDaemon:
    def __init__(self, mac: str, adapter: str, connect_timeout: int, max_reconnect_backoff: int = 60) -> None:  # NEW: max_reconnect_backoff
        self.mac = mac
        self.adapter = adapter
        self.state = State()
        self._server: Optional[asyncio.AbstractServer] = None
        self._stop = asyncio.Event()
        self._client: Optional[BleakClient] = None
        self._connect_timeout = connect_timeout
        self._max_reconnect_backoff = max_reconnect_backoff  # NEW
        self._current_backoff = 1.0  # NEW

    async def start(self, sock_path: Path) -> None:
        # Create parent directory if it doesn't exist and we have permission
        # (systemd's RuntimeDirectory creates this for us when running as service)
        try:
            sock_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Directory likely created by systemd's RuntimeDirectory - continue
            if not sock_path.parent.exists():
                raise RuntimeError(f"Socket directory {sock_path.parent} does not exist and cannot be created")
        
        # Remove old socket if it exists
        try: sock_path.unlink()
        except FileNotFoundError: pass
        
        self._server = await asyncio.start_unix_server(self._handle_rpc, path=str(sock_path))
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try: loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError: pass
        asyncio.create_task(self._connect_loop())

    async def run_forever(self) -> None:
        assert self._server
        async with self._server:
            try: await self._server.serve_forever()
            except asyncio.CancelledError: log("server: cancelled")
            except Exception as e: log(f"server: error {e!r}")

    async def shutdown(self) -> None:
        log("shutdown requested")
        self._stop.set()
        try:
            if self._server:
                self._server.close()
                await self._server.wait_closed()
        finally:
            try: SOCK.unlink()
            except FileNotFoundError: pass
        await self._disconnect()
        log("daemon exit")

    async def _reply(self, w, res: dict) -> None:
        try:
            w.write(_json(res))
            try: await w.drain()
            except Exception: pass
        finally:
            try: w.close(); await w.wait_closed()
            except Exception: pass

    async def _handle_rpc(self, r, w) -> None:
        try:
            raw = await r.readline()
            req = json.loads(raw.decode("utf-8").strip() or "{}")
        except Exception as e:
            log(f"rpc: bad_request {e!r}")
            await self._reply(w, {"error":"bad_request"}); return

        cmd = req.get("cmd")
        # CHANGED: one_shot parameter ignored (always persistent mode)
        log(f"rpc: {cmd}")

        if cmd == "status":
            # CHANGED: Added metrics and battery to status response
            await self._reply(w, {
                "connected": self.state.connected,
                "busy": self.state.busy,
                "op": self.state.op,
                "eta": self.state.eta,
                "error": self.state.error,
                "battery_percent": self.state.battery_percent,
                "battery_last_read": self.state.battery_last_read,
                "metrics": {
                    "connect_attempts": self.state.metrics.connect_attempts,
                    "successful_connections": self.state.metrics.successful_connections,
                    "failed_connections": self.state.metrics.failed_connections,
                    "success_rate": (self.state.metrics.successful_connections / self.state.metrics.connect_attempts 
                                   if self.state.metrics.connect_attempts > 0 else 0.0)
                }
            })
            return
        if cmd == "shutdown":
            await self._reply(w, {"ok": True}); asyncio.create_task(self.shutdown()); return
        if cmd == "open_pulses":
            if self.state.busy: await self._reply(w, {"error":"busy"}); return
            n = int(req.get("pulses", 1)); it = float(req.get("interval", 2.0))
            # CHANGED: Removed one_shot handling
            asyncio.create_task(self._do_open_pulses(n, it))
            await self._reply(w, {"started": True}); return
        if cmd == "close":
            if self.state.busy: await self._reply(w, {"error":"busy"}); return
            # CHANGED: Removed one_shot handling
            asyncio.create_task(self._do_close())
            await self._reply(w, {"ok": True}); return
        if cmd == "read_battery":
            # NEW: Manual battery reading command
            battery = await self._read_battery()
            await self._reply(w, {"battery_percent": battery}); return

        await self._reply(w, {"error": f"unknown:{cmd}"})

    async def _connect_loop(self) -> None:
        """CHANGED: Enhanced with exponential backoff and metrics."""
        while not self._stop.is_set():
            try:
                self.state.metrics.connect_attempts += 1
                log(f"conn: scanning (backoff: {self._current_backoff:.1f}s)")
                
                dev = await BleakScanner.find_device_by_address(self.mac, timeout=8.0, adapter=self.adapter)
                if not dev:
                    log("conn: NOT_FOUND")
                    self.state.metrics.failed_connections += 1
                    await self._backoff_sleep()
                    continue
                
                log("conn: connecting…")
                async with BleakClient(self.mac, timeout=self._connect_timeout, address_type="public", adapter=self.adapter) as c:
                    self._client = c
                    self.state.connected = True
                    self.state.metrics.successful_connections += 1
                    self.state.metrics.last_connect_time = _now()
                    self._current_backoff = 1.0  # Reset on success
                    log("conn: CONNECTED")
                    
                    # NEW: Read battery immediately after connecting
                    await self._read_battery()
                    
                    connection_start = _now()
                    last_battery_read = _now()
                    
                    # NEW: Enhanced heartbeat loop with periodic battery reading
                    while not self._stop.is_set() and c.is_connected:
                        await asyncio.sleep(0.5)
                        
                        # Read battery every 5 minutes
                        if _now() - last_battery_read > 300:  # 300 seconds = 5 minutes
                            await self._read_battery()
                            last_battery_read = _now()
                    
                    # Track connection duration
                    connection_duration = _now() - connection_start
                    self.state.metrics.total_connected_time += connection_duration
                    self.state.metrics.disconnections += 1
                    log(f"conn: dropped (connected for {connection_duration:.1f}s)")
                
            except BleakError as e:
                log(f"conn: BleakError {e!r}")
                self.state.metrics.failed_connections += 1
            except Exception as e:
                log(f"conn: error {e!r}")
                self.state.metrics.failed_connections += 1
            finally:
                await self._disconnect()
                await self._backoff_sleep()

    async def _backoff_sleep(self) -> None:
        """NEW: Exponential backoff with configurable max."""
        await asyncio.sleep(self._current_backoff)
        self._current_backoff = min(self._current_backoff * 2, self._max_reconnect_backoff)

    async def _disconnect(self) -> None:
        c = self._client; self._client = None
        if c:
            try: await c.disconnect()
            except Exception: pass
        self.state.connected = False

    async def _read_battery(self) -> Optional[int]:
        """NEW: Read battery percentage from BLE device (G-80 specific)."""
        try:
            c = self._client
            if not c or not c.is_connected:
                return None
            
            # Read full status packet
            value = await c.read_gatt_char(CHAR_BATTERY)
            
            # G-80 devices store battery at byte 48 of the status packet
            if len(value) > BATTERY_BYTE_OFFSET:
                battery = value[BATTERY_BYTE_OFFSET]  # Extract from byte 48
                
                self.state.battery_percent = battery
                self.state.battery_last_read = _now()
                log(f"battery: {battery}%")
                return battery
            else:
                log(f"battery: status packet too short ({len(value)} bytes, expected >{BATTERY_BYTE_OFFSET})")
                return None
            
        except Exception as e:
            # Don't log error if battery service not supported
            if "not found" not in str(e).lower():
                log(f"battery: read failed {e!r}")
            return None

    async def _write_with_retry(self, c, char, payload, *, attempts=3, delay=0.25):
        last = None
        for i in range(1, attempts+1):
            try:
                await c.write_gatt_char(char, payload, response=True)
                return True
            except Exception as e:
                last = e
                log(f"gatt write retry {i}/{attempts} error {e!r}")
                await asyncio.sleep(delay)
        log(f"gatt write failed after {attempts} attempts: {last!r}")
        return False

    async def _do_open_pulses(self, n: int, interval: float) -> None:
        """Send open pulses. For partial opens (< base_pulses), disconnect after to stop door."""
        self.state.busy = True; self.state.op = "open_pulses"; self.state.eta = _now() + n*interval + 3.0; self.state.error = None
        
        # Determine if this is a partial open (need to disconnect to stop door)
        # Read base_pulses from config to know what "full open" means
        base_pulses = 14  # Default
        is_partial = False
        try:
            import json
            from pathlib import Path
            config_path = Path("/etc/coopdoor/config.json")
            if config_path.exists():
                cfg = json.loads(config_path.read_text())
                base_pulses = int(cfg.get("base_pulses", 14))
                is_partial = n < base_pulses
                log(f"open_pulses: config check: n={n}, base_pulses={base_pulses}, is_partial={is_partial}")
            else:
                log(f"open_pulses: config file not found, using default base_pulses=14")
                is_partial = n < 14
        except Exception as e:
            # If can't read config, assume full open (don't disconnect)
            log(f"open_pulses: config read failed: {e!r}, assuming full open")
            is_partial = False
            
        try:
            for i in range(n):
                if self._stop.is_set(): break
                c = self._client
                if not c or not c.is_connected: raise Exception("disconnected")
                ok = await self._write_with_retry(c, CHAR_WR, OPEN_PAYLOAD)
                if not ok: raise Exception("write_failed")
                log(f"open_pulses: {i+1}/{n}")
                if i < n-1: await asyncio.sleep(interval)
            log(f"open_pulses: done {n}" + (" (partial, disconnecting)" if is_partial else " (full, staying connected)"))
            
            # For partial opens, disconnect to stop the door from continuing
            if is_partial and self._client and self._client.is_connected:
                log("open_pulses: disconnecting to stop door at partial position")
                await self._client.disconnect()
                # Clear client so connection manager will reconnect
                self._client = None
                # Schedule reconnection after a delay
                await asyncio.sleep(2.0)
            else:
                log(f"open_pulses: not disconnecting (is_partial={is_partial}, connected={self._client and self._client.is_connected})")
                
        except Exception as e:
            log(f"open_pulses: error {e!r}"); self.state.error = str(e)
        finally:
            self.state.busy = False; self.state.op = None; self.state.eta = None

    async def _do_close(self) -> None:
        """CHANGED: Removed one_shot shutdown."""
        self.state.busy = True; self.state.op = "close"; self.state.eta = _now() + 3.0; self.state.error = None
        try:
            c = self._client
            if not c or not c.is_connected: raise Exception("disconnected")
            ok = await self._write_with_retry(c, CHAR_WR, CLOSE_PAYLOAD)
            if not ok: raise Exception("write_failed")
            log("close: done")
        except Exception as e:
            log(f"close: error {e!r}"); self.state.error = str(e)
        finally:
            self.state.busy = False; self.state.op = None; self.state.eta = None
            # REMOVED: one_shot shutdown

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", required=True)
    ap.add_argument("--adapter", default="hci0")
    ap.add_argument("--connect-timeout", type=int, default=15)
    ap.add_argument("--sock", required=True)
    ap.add_argument("--max-reconnect-backoff", type=int, default=60)  # NEW
    args = ap.parse_args()
    lock_fh = _get_lock()
    if not lock_fh: raise SystemExit("Another daemon is running")
    Path(PIDF).write_text(str(os.getpid()))
    log(f"daemon start: {args.mac} via {args.adapter} (persistent mode)")
    daemon = DoorDaemon(args.mac, args.adapter, args.connect_timeout, args.max_reconnect_backoff)
    await daemon.start(Path(args.sock))
    try: await daemon.run_forever()
    finally: await daemon.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
