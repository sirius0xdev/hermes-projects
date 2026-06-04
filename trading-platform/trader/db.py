from __future__ import annotations

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Allow overriding paths via env (for Docker)
BASE_DIR = Path(os.getenv("BASE_DIR", Path(__file__).parent))
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "bot.sqlite"))

# Ensure data directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    conn = _conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trades (
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
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS risk_config (
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
            CREATE TABLE IF NOT EXISTS secrets (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _serialize(value: Any) -> str:
    return json.dumps(value)


def _deserialize(value: str | None) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def set_key(key: str, value: Any) -> None:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
            (key, _serialize(value)),
        )
        conn.commit()
    finally:
        conn.close()


def get_key(key: str, default: Any = None) -> Any:
    conn = _conn()
    try:
        row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        return _deserialize(row["value"])
    finally:
        conn.close()


def record_trade(trade: dict[str, Any]) -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO trades(
                ts, asset, side, decision, size_usd_notional, leverage, entry_approx,
                stop_loss_idea, take_profit_idea, risk_pct_of_equity, rationale, status,
                pnl, opened_at, closed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                trade.get("ts", datetime.utcnow().isoformat(timespec="seconds")),
                trade.get("asset"),
                trade.get("side") or trade.get("decision"),
                trade.get("decision"),
                trade.get("size_usd_notional"),
                trade.get("leverage"),
                trade.get("entry_approx"),
                trade.get("stop_loss_idea"),
                trade.get("take_profit_idea"),
                trade.get("risk_pct_of_equity"),
                trade.get("rationale"),
                trade.get("status", "open"),
                trade.get("pnl"),
                datetime.utcnow().isoformat(timespec="seconds"),
                None,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def close_trade(trade_id: int, pnl: float | None = None) -> None:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE trades SET status='closed', pnl=?, closed_at=? WHERE id=?",
            (pnl, datetime.utcnow().isoformat(timespec="seconds"), trade_id),
        )
        conn.commit()
    finally:
        conn.close()


def open_trades(limit: int = 50):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='open' ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def closed_trades(limit: int = 200):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def pnl_summary() -> dict[str, Any]:
    conn = _conn()
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total_closed,
                COALESCE(SUM(pnl), 0) as total_pnl,
                COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END), 0) as gross_profit,
                COALESCE(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END), 0) as gross_loss
            FROM trades WHERE status='closed'
            """
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_risk_config() -> dict[str, Any]:
    """Get risk config from DB, falling back to env defaults if not set."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT equity_usd, risk_pct_min, risk_pct_max, max_daily_loss_pct, leverage, max_concurrent_positions FROM risk_config WHERE id=1"
        ).fetchone()
        if row:
            return dict(row)
    finally:
        conn.close()
    # Fallback to env defaults
    return {
        "equity_usd": float(os.getenv("STARTING_EQUITY_USD", "20")),
        "risk_pct_min": float(os.getenv("RISK_PCT_MIN", "0.05")),
        "risk_pct_max": float(os.getenv("RISK_PCT_MAX", "0.15")),
        "max_daily_loss_pct": float(os.getenv("MAX_DAILY_LOSS_PCT", "0.25")),
        "leverage": int(os.getenv("LEVERAGE", "5")),
        "max_concurrent_positions": int(os.getenv("MAX_CONCURRENT_POSITIONS", "1")),
    }


# Secret/key management
VALID_SECRET_KEYS={"HL_PRIVATE_KEY", "HL_ADDRESS", "HL_EXCHANGE_ADDRESS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"}


def get_secret(key: str, default: str | None = None) -> str | None:
    """Get a secret value from DB, falling back to env if not set."""
    if key not in VALID_SECRET_KEYS:
        return default
    conn = _conn()
    try:
        row = conn.execute("SELECT value FROM secrets WHERE key=?", (key,)).fetchone()
        if row and row["value"]:
            return row["value"]
    finally:
        conn.close()
    # Fallback to env
    return os.getenv(key, default)


def get_all_secrets() -> dict[str, str]:
    """Get all secrets (values masked for display)."""
    conn = _conn()
    try:
        rows = conn.execute("SELECT key, value, description, updated_at FROM secrets").fetchall()
        result = {}
        for row in rows:
            val = row["value"]
            # Mask value for display (show first 4 and last 4 chars)
            if val and len(val) > 8:
                masked = val[:4] + "*" * (len(val) - 8) + val[-4:]
            elif val:
                masked = "*" * len(val)
            else:
                masked = ""
            result[row["key"]] = {
                "value": masked,
                "description": row["description"],
                "updated_at": row["updated_at"],
            }
        return result
    finally:
        conn.close()


def set_secret(key: str, value: str, description: str = "") -> bool:
    """Set a secret value in DB. Returns True if successful."""
    if key not in VALID_SECRET_KEYS:
        return False
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO secrets(key, value, description, updated_at) VALUES(?, ?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, description=excluded.description, updated_at=datetime('now')",
            (key, value, description),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_secret(key: str) -> bool:
    """Delete a secret from DB. Returns True if successful."""
    if key not in VALID_SECRET_KEYS:
        return False
    conn = _conn()
    try:
        conn.execute("DELETE FROM secrets WHERE key=?", (key,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_secret_descriptions() -> dict[str, str]:
    """Return descriptions for valid secret keys."""
    return {
        "HL_PRIVATE_KEY": "Hyperliquid wallet private key (for signing orders)",
        "HL_ADDRESS": "Hyperliquid wallet address (public)",
        "HL_EXCHANGE_ADDRESS": "Hyperliquid exchange/vault address (if using vault)",
        "TELEGRAM_BOT_TOKEN": "Telegram bot token for alerts",
        "TELEGRAM_CHAT_ID": "Telegram chat ID for alerts",
    }