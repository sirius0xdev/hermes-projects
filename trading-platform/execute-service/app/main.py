"""
Trading Execution Microservice
- Wallet auth (SIWE/SIWS)
- Hyperliquid futures + spot execution
- Solana on-chain execution
- Order management + position tracking
- mTLS for inter-service communication
"""
from __future__ import annotations

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Service startup and shutdown lifecycle."""
    logger.info("Starting execution service...")
    await init_db()

    # Initialize executors
    hl_exec = get_hyperliquid_executor()
    sol_exec = get_solana_executor()
    await hl_exec.initialize()
    await sol_exec.initialize()
    logger.info("All executors initialized")

    yield

    # Shutdown
    logger.info("Shutting down execution service...")
    await sol_exec.close()
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
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> dict:
    """Check if all executors are initialized."""
    hl = get_hyperliquid_executor()
    sol = get_solana_executor()
    ready = hl._initialized and sol._initialized
    return {"status": "ready" if ready else "initializing"}


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
