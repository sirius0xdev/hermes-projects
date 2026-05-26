"""
Trading Execution Microservice
- Wallet auth (SIWE/SIWS)
- Hyperliquid futures + spot execution
- Solana on-chain execution
- Order management + position tracking
- mTLS for inter-service communication
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import ssl

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db, get_session, engine
from app.middleware.mtls import MTLSMiddleware, create_ssl_context
from app.dependencies import (
    get_hyperliquid_executor,
    get_solana_executor,
    get_order_manager,
)

# Import API routers
from app.api.auth import router as auth_router
from app.api.trades import router as trades_router
from app.api.settings import router as settings_router

# Strip Gateway API prefix
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from typing import Callable, Awaitable


class _StripPrefixMiddleware(BaseHTTPMiddleware):
    """Strip /api/execute from incoming paths so internal routes work."""

    def __init__(self, app, prefix: str = ""):
        super().__init__(app)
        self.prefix = prefix.rstrip("/")

    async def dispatch(
        self, request: StarletteRequest, call_next: Callable[[StarletteRequest], Awaitable[StarletteResponse]]
    ) -> StarletteResponse:
        path = request.scope.get("path", "")
        if self.prefix and path.startswith(self.prefix):
            request.scope["path"] = path[len(self.prefix):] or "/"
        return await call_next(request)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Timeout for each executor initialization (seconds)
EXECUTOR_INIT_TIMEOUT = 10

# Global readiness flag set once all executors init
_service_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Service startup and shutdown lifecycle."""
    logger.info("Starting execution service...")

    if settings.db_auto_create_tables:
        logger.info("Auto-creating tables (dev mode)")
        await init_db()
    else:
        logger.info("Skipping table creation (production - relies on CNPG init jobs / migrations)")

    # Initialize executors with timeout and graceful fallback
    # If one hangs, the service still serves /health so K8s probes pass
    hl_exec = get_hyperliquid_executor()
    sol_exec = get_solana_executor()

    executor_status = {}

    for name, executor in [("Hyperliquid", hl_exec), ("Solana", sol_exec)]:
        try:
            async with asyncio.timeout(EXECUTOR_INIT_TIMEOUT):
                await executor.initialize()
            executor_status[name] = "ready"
            logger.info("%s executor initialized", name)
        except asyncio.TimeoutError:
            executor_status[name] = "timeout"
            logger.warning(
                "%s executor initialization timed out after %ds — will retry on first request",
                name, EXECUTOR_INIT_TIMEOUT,
            )
        except Exception:
            executor_status[name] = "failed"
            logger.exception(
                "%s executor initialization failed — will retry on first request", name
            )

    # Service is ready once DB is connected — executors can initialize lazily
    _service_ready = True
    logger.info(
        "Service ready. Executor status: %s",
        ", ".join(f"{k}={v}" for k, v in executor_status.items()),
    )
    app.state.executor_status = executor_status

    yield

    # Shutdown
    logger.info("Shutting down execution service...")
    try:
        await sol_exec.close()
    except Exception:
        logger.exception("Error closing Solana executor")
    await engine.dispose()


app = FastAPI(
    title="Execution Service",
    description="Trading execution microservice for Hyperliquid + Solana",
    version="0.1.0",
    lifespan=lifespan,
    root_path="/api/execute",
)

# mTLS middleware (if enabled)
app.add_middleware(MTLSMiddleware)

# Strip Gateway API prefix so /api/execute/trades -> /trades
app.add_middleware(_StripPrefixMiddleware, prefix="/api/execute")

# Register routers
app.include_router(auth_router)
app.include_router(trades_router)
app.include_router(settings_router)


# Health checks
@app.get("/health")
async def health() -> dict:
    """Liveness probe — always returns 200 once FastAPI has started."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> JSONResponse:
    """Readiness probe — returns 200 once the service is running.
    Executors initialize lazily on first request after startup."""
    if not _service_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "starting"},
        )
    status = getattr(app.state, "executor_status", {})
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "executors": status},
    )


@app.get("/health/executors")
async def executor_health() -> JSONResponse:
    """Report executor initialization status (separate from readiness probe)."""
    status = getattr(app.state, "executor_status", {})
    return JSONResponse(
        status_code=200,
        content=status,
    )


@app.get("/health/live")
async def liveness() -> dict:
    return {"status": "alive"}


def run():
    """Entrypoint for uvicorn or direct execution."""
    import uvicorn

    ssl_context = create_ssl_context()

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        ssl_keyfile=settings.mtls_server_key if settings.mtls_enabled else None,
        ssl_certfile=settings.mtls_server_cert if settings.mtls_enabled else None,
    )


if __name__ == "__main__":
    run()
