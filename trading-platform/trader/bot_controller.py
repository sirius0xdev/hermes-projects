from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PID_FILE = Path(__file__).with_name("bot.pid")
LOG_FILE = Path(__file__).with_name("bot.log")
SCRIPT = Path(__file__).with_name("main.py")


def _get_pid() -> int | None:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except Exception:
            return None
    return None


def _write_pid(pid: int) -> None:
    PID_FILE.write_text(str(pid))


def is_running() -> bool:
    pid = _get_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def start_bot() -> dict[str, Any]:
    pid = _get_pid()
    if pid and is_running():
        return {"status": "already_running", "pid": pid}
    with open(LOG_FILE, "a") as log:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT)],
            cwd=str(SCRIPT.parent),
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    _write_pid(proc.pid)
    return {"status": "started", "pid": proc.pid}


def stop_bot() -> dict[str, Any]:
    pid = _get_pid()
    if not pid:
        return {"status": "not_running"}
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            if not is_running():
                break
            time.sleep(0.3)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        PID_FILE.unlink(missing_ok=True)
        return {"status": "stopped"}
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return {"status": "not_running"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_status() -> dict[str, Any]:
    pid = _get_pid()
    return {"running": is_running(), "pid": pid}
