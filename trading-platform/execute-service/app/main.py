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

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Timeout for each executor initialization (seconds)
EXECUTOR_INIT_TIMEOUT = 10


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Service startup and shutdown lifecycle."""
    logger.info("Starting execution service...")
    await init_db()

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

    logger.info(
        "Service ready. Executor status: %s",
        ", ".join(f"{k}={v}" for k, v in executor_status.items()),
    )

    # Expose executor readiness on the app state for the /health/ready endpoint
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
)

# mTLS middleware (if enabled)
app.add_middleware(MTLSMiddleware)

# Register routers
app.include_router(auth_router)
app.include_router(trades_router)


# Health checks
@app.get("/health")
async def health() -> dict:
    """Liveness probe — always returns 200 once FastAPI has started."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> JSONResponse:
    """Readiness probe — returns 503 if any executor failed to initialize."""
    status = getattr(app.state, "executor_status", {})
    failed = {k: v for k, v in status.items() if v != "ready"}
    if failed:
        return JSONResponse(
            status_code=503,
            content={"status": "initializing", "executors": failed},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "executors": status},
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
