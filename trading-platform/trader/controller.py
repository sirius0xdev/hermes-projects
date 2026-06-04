#!/usr/bin/env python3
"""
Trader controller: simple file-based control interface.
Creates/reads/writes ~/.scalper/control.json for start/stop/pause.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

CONTROL_DIR = Path.home() / ".scalper"
CONTROL_FILE = CONTROL_DIR / "control.json"


def ensure_dir() -> None:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)


def get_state() -> Dict[str, Optional[object]]:
    ensure_dir()
    if not CONTROL_FILE.exists():
        return {"running": False, "mode": "stopped"}
    try:
        data = json.loads(CONTROL_FILE.read_text())
        if not isinstance(data, dict):
            return {"running": False, "mode": "stopped"}
        return {
            "running": bool(data.get("running", False)),
            "mode": data.get("mode", "stopped"),
        }
    except Exception:
        return {"running": False, "mode": "stopped"}


def set_running(running: bool, mode: str = "running") -> Dict[str, Optional[object]]:
    ensure_dir()
    state = {"running": running, "mode": mode if running else "stopped"}
    CONTROL_FILE.write_text(json.dumps(state, indent=2))
    return state


def mark_running() -> Dict[str, Optional[object]]:
    return set_running(True, "running")


def mark_stopped() -> Dict[str, Optional[object]]:
    return set_running(False, "stopped")


__all__ = ["get_state", "mark_running", "mark_stopped"]
