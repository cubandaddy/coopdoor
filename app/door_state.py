#!/usr/bin/env python3
"""Door state management and persistence for CoopDoor system."""
from __future__ import annotations

import math
import json
from typing import TypedDict, Literal, Optional
from datetime import datetime, timezone
from pathlib import Path

class DoorState(TypedDict):
    """Current door position state."""
    position_pulses: int      # 0-14
    position_percent: int     # 0-100
    last_updated: str         # ISO timestamp

class LastAction(TypedDict):
    """Last door operation record."""
    cmd: Literal["open", "close"]
    requested_percent: Optional[int]
    actual_pulses: int
    delta_pulses: int
    ok: bool
    at: str
    source: str
    error: Optional[str]

CONF_DIR = Path("/etc/coopdoor")
DOOR_STATE_PATH = CONF_DIR / "door_state.json"
LAST_ACTION_PATH = CONF_DIR / "last_action.json"

def percent_to_pulses(percent: int, base_pulses: int = 14) -> int:
    """
    Convert percentage to pulses, ALWAYS rounding UP as required.
    
    Examples:
        25% with 14 pulses = 3.5 → 4 pulses (rounds up)
        50% with 14 pulses = 7.0 → 7 pulses
        75% with 14 pulses = 10.5 → 11 pulses (rounds up)
    """
    if percent <= 0:
        return 0
    return max(1, math.ceil(base_pulses * (percent / 100.0)))

def pulses_to_percent(pulses: int, base_pulses: int = 14) -> int:
    """Convert pulses back to percentage."""
    return min(100, int((pulses / base_pulses) * 100))

def atomic_write_json(path: Path, data: dict) -> None:
    """
    Atomic write to prevent corruption on power loss.
    Writes to temp file then renames (atomic operation).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2))
    temp.replace(path)

def get_door_state() -> DoorState:
    """Load current door position from state file."""
    if not DOOR_STATE_PATH.exists():
        default: DoorState = {
            "position_pulses": 0,
            "position_percent": 0,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        atomic_write_json(DOOR_STATE_PATH, default)
        return default
    
    try:
        data = json.loads(DOOR_STATE_PATH.read_text())
        return data
    except Exception:
        # Corrupted state, reset to closed
        default: DoorState = {
            "position_pulses": 0,
            "position_percent": 0,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        atomic_write_json(DOOR_STATE_PATH, default)
        return default

def update_door_position(pulses: int, base_pulses: int = 14) -> DoorState:
    """Update door position after operation."""
    state: DoorState = {
        "position_pulses": max(0, min(base_pulses, pulses)),
        "position_percent": pulses_to_percent(pulses, base_pulses),
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    atomic_write_json(DOOR_STATE_PATH, state)
    return state

def save_last_action(action: LastAction) -> None:
    """Persist last action for UI display."""
    atomic_write_json(LAST_ACTION_PATH, action)

def get_last_action() -> Optional[LastAction]:
    """Load last action from disk."""
    if not LAST_ACTION_PATH.exists():
        return None
    try:
        return json.loads(LAST_ACTION_PATH.read_text())
    except Exception:
        return None

def reset_door_position() -> DoorState:
    """Reset position to closed (for manual adjustments)."""
    return update_door_position(0)