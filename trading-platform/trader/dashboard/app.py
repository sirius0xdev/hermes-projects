from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sqlite3
from datetime import datetime
import json
import os
import subprocess
import sys
import signal
import time

# Allow overriding paths via env (for Docker)
import os
from pathlib import Path

BASE_DIR = Path(os.getenv("BASE_DIR", Path(__file__).parent.parent))
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "bot.sqlite"))
PID_PATH = Path(os.getenv("PID_PATH", BASE_DIR / "data" / "bot.pid"))
LOG_PATH = Path(os.getenv("LOG_PATH", BASE_DIR / "logs" / "bot.log"))
SCRIPT = BASE_DIR / "main.py"
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=BASE / "templates")
(BASE / "static").mkdir(exist_ok=True)

# Ensure data/logs directories exist
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
PID_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    conn = db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trades(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                asset TEXT,
                side TEXT,
                decision TEXT,
                size_usd_notional REAL,
                leverage INTEGER,
                entry_approx REAL,
                stop_loss_idea TEXT,
                take_profit_idea TEXT,
                risk_pct_of_equity REAL,
                rationale TEXT,
                status TEXT,
                pnl REAL,
                opened_at TEXT,
                closed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS state(
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS risk_config(
                id INTEGER PRIMARY KEY CHECK (id = 1),
                equity_usd REAL NOT NULL DEFAULT 20.0,
                risk_pct_min REAL NOT NULL DEFAULT 0.05,
                risk_pct_max REAL NOT NULL DEFAULT 0.15,
                max_daily_loss_pct REAL NOT NULL DEFAULT 0.25,
                leverage INTEGER NOT NULL DEFAULT 5,
                max_concurrent_positions INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT OR IGNORE INTO risk_config(id, equity_usd, risk_pct_min, risk_pct_max, max_daily_loss_pct, leverage, max_concurrent_positions, updated_at)
            VALUES(1, 20.0, 0.05, 0.15, 0.25, 5, 1, datetime('now'));
            """
        )
        conn.commit()
    finally:
        conn.close()
init_db()


def _get_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text().strip())
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    PID_PATH.write_text(str(pid))


def _running() -> bool:
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


def _ensure_control_tables() -> None:
    conn = db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS control_state(
                id INTEGER PRIMARY KEY CHECK (id = 1),
                running INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT OR IGNORE INTO control_state(id, running, updated_at) VALUES(1, 0, datetime('now'));
            """
        )
        conn.commit()
    finally:
        conn.close()
_ensure_control_tables()


def _read_control() -> dict:
    conn = db()
    try:
        row = conn.execute("SELECT running, updated_at FROM control_state WHERE id=1").fetchone()
        if not row:
            return {"running": False, "updated_at": None}
        return {"running": bool(row["running"]), "updated_at": row["updated_at"]}
    finally:
        conn.close()


def _write_control(running: bool) -> None:
    conn = db()
    try:
        conn.execute("UPDATE control_state SET running=?, updated_at=datetime('now') WHERE id=1", (1 if running else 0,))
        conn.commit()
    finally:
        conn.close()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return FileResponse(str((BASE / "templates" / "index.html").resolve()))


@app.get("/api/status")
async def api_status() -> JSONResponse:
    return JSONResponse({"running": _running()})


@app.post("/api/control")
async def api_control(request: Request) -> JSONResponse:
    body = await request.json()
    action = (body.get("action") or "").lower()
    if action == "start":
        if _running():
            return JSONResponse({"status": "already_running", "running": True})
        with open(LOG_PATH, "a") as log:
            proc = subprocess.Popen(
                [sys.executable, str(SCRIPT)],
                cwd=str(SCRIPT.parent),
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
            )
        _write_pid(proc.pid)
        _write_control(True)
        return JSONResponse({"status": "started", "pid": proc.pid, "running": True})
    if action == "stop":
        pid = _get_pid()
        if not pid:
            _write_control(False)
            return JSONResponse({"status": "not_running", "running": False})
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                if not _running():
                    break
                time.sleep(0.3)
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        except ProcessLookupError:
            pass
        PID_PATH.unlink(missing_ok=True)
        _write_control(False)
        return JSONResponse({"status": "stopped", "running": False})
    return JSONResponse({"status": "bad_request"}, status_code=400)


@app.get("/api/trades")
async def api_trades(status: str | None = None, limit: int = 200) -> JSONResponse:
    conn = db()
    try:
        query = "SELECT * FROM trades"
        params: list = []
        if status in {"open", "closed"}:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        rows = conn.execute(query, params).fetchall()
        return JSONResponse([dict(r) for r in rows])
    finally:
        conn.close()


@app.post("/api/trades/{trade_id}/close")
async def api_close_trade(trade_id: int) -> JSONResponse:
    conn = db()
    try:
        conn.execute(
            "UPDATE trades SET status='closed', pnl=?, closed_at=? WHERE id=?",
            (None, datetime.utcnow().isoformat(timespec="seconds"), trade_id),
        )
        conn.commit()
        return JSONResponse({"status": "closed", "id": trade_id})
    finally:
        conn.close()


@app.get("/api/pnl")
async def api_pnl() -> JSONResponse:
    conn = db()
    try:
        row = conn.execute(
            """
            SELECT
              COUNT(*) as total_closed,
              COALESCE(SUM(pnl),0) as total_pnl,
              COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END),0) as gross_profit,
              COALESCE(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END),0) as gross_loss
            FROM trades WHERE status='closed'
            """
        ).fetchone()
        return JSONResponse(dict(row) if row else {})
    finally:
        conn.close()


@app.get("/api/config/risk")
async def api_risk_config_get() -> JSONResponse:
    conn = db()
    try:
        row = conn.execute("SELECT equity_usd, risk_pct_min, risk_pct_max, max_daily_loss_pct, leverage, max_concurrent_positions, updated_at FROM risk_config WHERE id=1").fetchone()
        if not row:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(dict(row))
    finally:
        conn.close()


@app.post("/api/config/risk")
async def api_risk_config_set(request: Request) -> JSONResponse:
    body = await request.json()
    allowed = {"equity_usd", "risk_pct_min", "risk_pct_max", "max_daily_loss_pct", "leverage", "max_concurrent_positions"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return JSONResponse({"status": "no_valid_fields"}, status_code=400)
    
    # Validate ranges
    if "equity_usd" in updates and (not isinstance(updates["equity_usd"], (int, float)) or updates["equity_usd"] <= 0):
        return JSONResponse({"status": "invalid_equity_usd"}, status_code=400)
    if "risk_pct_min" in updates and (not isinstance(updates["risk_pct_min"], (int, float)) or not 0 < updates["risk_pct_min"] < 1):
        return JSONResponse({"status": "invalid_risk_pct_min"}, status_code=400)
    if "risk_pct_max" in updates and (not isinstance(updates["risk_pct_max"], (int, float)) or not 0 < updates["risk_pct_max"] < 1):
        return JSONResponse({"status": "invalid_risk_pct_max"}, status_code=400)
    if "risk_pct_min" in updates and "risk_pct_max" in updates and updates["risk_pct_min"] > updates["risk_pct_max"]:
        return JSONResponse({"status": "min_greater_than_max"}, status_code=400)
    if "max_daily_loss_pct" in updates and (not isinstance(updates["max_daily_loss_pct"], (int, float)) or not 0 < updates["max_daily_loss_pct"] < 1):
        return JSONResponse({"status": "invalid_max_daily_loss_pct"}, status_code=400)
    if "leverage" in updates and (not isinstance(updates["leverage"], int) or updates["leverage"] <= 0):
        return JSONResponse({"status": "invalid_leverage"}, status_code=400)
    if "max_concurrent_positions" in updates and (not isinstance(updates["max_concurrent_positions"], int) or updates["max_concurrent_positions"] <= 0):
        return JSONResponse({"status": "invalid_max_concurrent_positions"}, status_code=400)

    conn = db()
    try:
        set_clause = ", ".join(f"{k}=?" for k in updates.keys())
        params = list(updates.values()) + [1]
        conn.execute(f"UPDATE risk_config SET {set_clause}, updated_at=datetime('now') WHERE id=?", params)
        conn.commit()
        
        # Return updated config
        row = conn.execute("SELECT equity_usd, risk_pct_min, risk_pct_max, max_daily_loss_pct, leverage, max_concurrent_positions, updated_at FROM risk_config WHERE id=1").fetchone()
        return JSONResponse(dict(row))
    finally:
        conn.close()


# Secrets/keys API endpoints
VALID_SECRET_KEYS={"HL_PRIVATE_KEY", "HL_ADDRESS", "HL_EXCHANGE_ADDRESS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"}
SECRET_DESCRIPTIONS={"HL_PRIVATE_KEY": "Hyperliquid wallet private key (for signing orders)", "HL_ADDRESS": "Hyperliquid wallet address (public)", "HL_EXCHANGE_ADDRESS": "Hyperliquid exchange/vault address (if using vault)", "TELEGRAM_BOT_TOKEN": "Telegram bot token for alerts", "TELEGRAM_CHAT_ID": "Telegram chat ID for alerts"}


def _mask_value(val: str) -> str:
    """Mask a secret value for display."""
    if not val:
        return ""
    if len(val) > 8:
        return val[:4] + "*" * (len(val) - 8) + val[-4:]
    return "*" * len(val)


@app.get("/api/config/secrets")
async def api_secrets_get() -> JSONResponse:
    """Get all secrets (masked for display)."""
    conn = db()
    try:
        rows = conn.execute("SELECT key, value, description, updated_at FROM secrets").fetchall()
        result = {}
        for row in rows:
            result[row["key"]] = {
                "value": _mask_value(row["value"]),
                "description": row["description"] or SECRET_DESCRIPTIONS.get(row["key"], ""),
                "updated_at": row["updated_at"],
            }
        # Include keys not yet set
        for key in VALID_SECRET_KEYS:
            if key not in result:
                result[key] = {
                    "value": "",
                    "description": SECRET_DESCRIPTIONS.get(key, ""),
                    "updated_at": None,
                }
        return JSONResponse(result)
    finally:
        conn.close()


@app.post("/api/config/secrets")
async def api_secrets_set(request: Request) -> JSONResponse:
    """Set a secret value."""
    body = await request.json()
    key = body.get("key")
    value = body.get("value", "")
    if key not in VALID_SECRET_KEYS:
        return JSONResponse({"status": "invalid_key"}, status_code=400)
    if not isinstance(value, str):
        return JSONResponse({"status": "invalid_value"}, status_code=400)

    conn = db()
    try:
        conn.execute(
            "INSERT INTO secrets(key, value, description, updated_at) VALUES(?, ?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, description=excluded.description, updated_at=datetime('now')",
            (key, value, SECRET_DESCRIPTIONS.get(key, "")),
        )
        conn.commit()
        return JSONResponse({"status": "saved", "key": key})
    finally:
        conn.close()


@app.delete("/api/config/secrets/{key}")
async def api_secrets_delete(key: str) -> JSONResponse:
    """Delete a secret."""
    if key not in VALID_SECRET_KEYS:
        return JSONResponse({"status": "invalid_key"}, status_code=400)

    conn = db()
    try:
        conn.execute("DELETE FROM secrets WHERE key=?", (key,))
        conn.commit()
        return JSONResponse({"status": "deleted", "key": key})
    finally:
        conn.close()