#!/usr/bin/env python3
"""Shared configuration and utilities for CoopDoor - Single source of truth."""
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Tuple

# ========== PATH CONSTANTS (Single Source of Truth) ==========
CONF_DIR = Path("/etc/coopdoor")
AUTOMATION_PATH = CONF_DIR / "automation.json"
DEVICE_CONFIG_PATH = CONF_DIR / "config.json"
UI_CONFIG_PATH = CONF_DIR / "ui.json"
DOOR_STATE_PATH = CONF_DIR / "door_state.json"
LAST_ACTION_PATH = CONF_DIR / "last_action.json"

SYSTEMD_DIR = Path("/etc/systemd/system")
BACKUP_DIR = Path("/var/lib/coopdoor-backups")

# ========== SHARED UTILITIES ==========

def system_timezone() -> str:
    """
    Get system timezone with UTC fallback.
    Single implementation used across all modules.
    """
    tz_file = Path("/etc/timezone")
    if tz_file.exists():
        try:
            return tz_file.read_text().strip()
        except Exception:
            pass
    return "UTC"

def run_command(args: list[str], timeout: float = 45.0) -> Tuple[int, str, str]:
    """
    Execute subprocess command with timeout.
    Single implementation used across all modules.
    
    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    p = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()