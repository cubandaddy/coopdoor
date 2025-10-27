#!/usr/bin/env python3
from __future__ import annotations
import argparse, asyncio, json, time, signal, fcntl, os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
from bleak import BleakClient, BleakScanner

CHAR_WR      = "00000000-8e22-4541-9d4c-21edae82ed19"
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
class State:
    connected: bool = False
    busy: bool = False
    op: Optional[str] = None
    eta: Optional[float] = None
    error: Optional[str] = None

class DoorDaemon:
    def __init__(self, mac: str, adapter: str, connect_timeout: int) -> None:
        self.mac = mac
        self.adapter = adapter
        self.state = State()
        self._server: Optional[asyncio.AbstractServer] = None
        self._stop = asyncio.Event()
        self._client: Optional[BleakClient] = None
        self._connect_timeout = connect_timeout

    async def start(self, sock_path: Path) -> None:
        sock_path.parent.mkdir(parents=True, exist_ok=True)
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
        one_shot = bool(req.get("one_shot", False))
        log(f"rpc: {cmd} {req}")

        if cmd == "status":
            await self._reply(w, {"connected": self.state.connected, "busy": self.state.busy,
                                  "op": self.state.op, "eta": self.state.eta, "error": self.state.error}); return
        if cmd == "shutdown":
            await self._reply(w, {"ok": True}); asyncio.create_task(self.shutdown()); return
        if cmd == "open_pulses":
            if self.state.busy: await self._reply(w, {"error":"busy"}); return
            n = int(req.get("pulses", 1)); it = float(req.get("interval", 2.0))
            asyncio.create_task(self._do_open_pulses(n, it, one_shot)); await self._reply(w, {"started": True}); return
        if cmd == "close":
            if self.state.busy: await self._reply(w, {"error":"busy"}); return
            asyncio.create_task(self._do_close(one_shot)); await self._reply(w, {"ok": True}); return

        await self._reply(w, {"error": f"unknown:{cmd}"})

    async def _connect_loop(self) -> None:
        while not self._stop.is_set():
            try:
                log("conn: start scanning")
                dev = await BleakScanner.find_device_by_address(self.mac, timeout=8.0, adapter=self.adapter)
                if not dev:
                    log("conn: NOT_FOUND")
                    await asyncio.sleep(1.0); continue
                log("conn: connecting…")
                async with BleakClient(self.mac, timeout=self._connect_timeout, address_type="public", adapter=self.adapter) as c:
                    self._client = c; self.state.connected = True
                    log("conn: CONNECTED")
                    while not self._stop.is_set() and c.is_connected:
                        await asyncio.sleep(0.3)
                log("conn: dropped"); self.state.connected = False
            except Exception as e:
                log(f"conn: error {e!r}")
            finally:
                await self._disconnect()
                await asyncio.sleep(1.0)

    async def _disconnect(self) -> None:
        c = self._client; self._client = None
        if c:
            try: await c.disconnect()
            except Exception: pass
        self.state.connected = False

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

    async def _do_open_pulses(self, n: int, interval: float, one_shot: bool) -> None:
        self.state.busy = True; self.state.op = "open_pulses"; self.state.eta = _now() + n*interval + 3.0; self.state.error = None
        try:
            for i in range(n):
                if self._stop.is_set(): break
                c = self._client
                if not c or not c.is_connected: raise Exception("disconnected")
                ok = await self._write_with_retry(c, CHAR_WR, OPEN_PAYLOAD)
                if not ok: raise Exception("write_failed")
                log(f"open_pulses: {i+1}/{n}")
                if i < n-1: await asyncio.sleep(interval)
            log(f"open_pulses: done {n}")
        except Exception as e:
            log(f"open_pulses: error {e!r}"); self.state.error = str(e)
        finally:
            self.state.busy = False; self.state.op = None; self.state.eta = None
            if one_shot: asyncio.create_task(self.shutdown())

    async def _do_close(self, one_shot: bool) -> None:
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
            if one_shot: asyncio.create_task(self.shutdown())

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", required=True)
    ap.add_argument("--adapter", default="hci0")
    ap.add_argument("--connect-timeout", type=int, default=15)
    ap.add_argument("--sock", required=True)
    args = ap.parse_args()
    lock_fh = _get_lock()
    if not lock_fh: raise SystemExit("Another daemon is running")
    Path(PIDF).write_text(str(os.getpid()))
    log(f"daemon start: {args.mac} via {args.adapter}")
    daemon = DoorDaemon(args.mac, args.adapter, args.connect_timeout)
    await daemon.start(Path(args.sock))
    try: await daemon.run_forever()
    finally: await daemon.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
