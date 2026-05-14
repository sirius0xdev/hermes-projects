"""AgentForge Waitlist API — FastAPI backend for waitlist signups.

Endpoints:
    POST /api/waitlist  — Submit email to waitlist
    GET  /healthz       — Liveness/readiness probe
    GET  /api/waitlist/count — Admin: total signups (optional)

Connects to CNPG PostgreSQL cluster (siriusdevops-pgdb) and sends
Telegram notifications to Lance on each new signup.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("waitlist-api")

# ── config ─────────────────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "siriusdevops-pgdb-rw.customer1.svc.cluster.local")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "waitlist")
DB_USER = os.getenv("DB_USER", "waitlist")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── globals ────────────────────────────────────────────────────────────────
pool: asyncpg.Pool | None = None
http_client: httpx.AsyncClient | None = None

# ── lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, http_client
    logger.info("Connecting to PostgreSQL %s/%s ...", DB_HOST, DB_NAME)
    pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        min_size=2,
        max_size=10,
    )
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    # Ensure table exists
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS waitlist_signups (
                id          BIGSERIAL PRIMARY KEY,
                email       TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                signup_source TEXT,
                ip_address  TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_waitlist_email
                ON waitlist_signups (LOWER(email));
        """)
    logger.info("Database ready. Pool size=%d", pool.get_size())
    yield
    logger.info("Shutting down...")
    if http_client:
        await http_client.aclose()
    if pool:
        await pool.close()


app = FastAPI(
    title="AgentForge Waitlist API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sirius-sec.com",
        "https://www.sirius-sec.com",
        "https://siriusdevops.com",
        "https://www.siriusdevops.com",
        "https://agentforge.ai",
        "https://www.agentforge.ai",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# ── models ─────────────────────────────────────────────────────────────────
class WaitlistRequest(BaseModel):
    email: str = Field(
        ...,
        min_length=5,
        max_length=254,
        pattern=r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$",
    )
    source: str | None = Field(default=None, max_length=64)

class WaitlistResponse(BaseModel):
    ok: bool
    message: str


def _normalize_email(raw: str) -> str:
    """Lowercase + strip the email."""
    return raw.strip().lower()


async def _notify_telegram(email: str, source: str | None) -> None:
    """Send a notification to Lance via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — skipping notification")
        return

    source_info = f"\nSource: {source}" if source else ""
    text = (
        f"\U0001f514 <b>New AgentForge Waitlist Signup!</b>\n"
        f"<code>{email}</code>{source_info}"
    )

    try:
        r = await http_client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
        )
        r.raise_for_status()
        logger.info("Telegram notification sent for %s", email)
    except Exception:
        logger.exception("Failed to send Telegram notification for %s", email)


# ── routes ─────────────────────────────────────────────────────────────────
@app.post("/api/waitlist", response_model=WaitlistResponse)
async def signup(req: WaitlistRequest, request: Request):
    """Accept a waitlist signup. Stores email + metadata in PostgreSQL."""
    email = _normalize_email(req.email)

    # Extract client IP
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    ip = ip.split(",")[0].strip()

    source = (req.source or "").strip()[:64] or None

    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO waitlist_signups (email, signup_source, ip_address)
                VALUES ($1, $2, $3)
                ON CONFLICT (LOWER(email)) DO NOTHING
                """,
                email, source, ip,
            )
        except Exception as exc:
            logger.exception("DB insert failed for %s", email)
            raise HTTPException(status_code=500, detail="Database error")

    # Fire-and-forget Telegram notification (don't block the response)
    import asyncio as _asyncio
    _asyncio.create_task(_notify_telegram(email, source))

    logger.info("Signup: %s (source=%s, ip=%s)", email, source, ip)
    return WaitlistResponse(ok=True, message="You're on the list!")


@app.get("/healthz")
async def healthz():
    """Kubernetes liveness/readiness probe."""
    if pool is None:
        raise HTTPException(status_code=503, detail="DB pool not ready")
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="DB unreachable")
    return {"status": "ok"}


@app.get("/api/waitlist/count")
async def count():
    """Return total signup count (optional admin endpoint)."""
    if pool is None:
        raise HTTPException(status_code=503, detail="DB pool not ready")
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM waitlist_signups")
    return {"count": total}
