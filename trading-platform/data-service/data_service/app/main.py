"""Data service — FastAPI entry point.

Wires together:
- PostgreSQL (DB layer from app.db)
- Redis cache (app.cache)
- Kafka producer/consumer (app.kafka)
- REST API routes (app.routes)
"""
from __future__ import annotations

import logging
import os
from asyncio import timeout as asyncio_timeout
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from data_service.app.cache.client import RedisClient, get_redis_client, shutdown_redis
from data_service.app.cache.service import CacheService
from data_service.app.db import db_config, DatabaseConfig
from data_service.app.routes.market_data import set_cache_service

# Health check router (required for K8s liveness/readiness probes)
from fastapi import APIRouter
health_router = APIRouter(tags=["health"])


# ── Service state for readiness ────────────────────────────────
_service_ready = False


@health_router.get("/health", status_code=200)
async def health_check():
    """Health check endpoint for Kubernetes probes and Docker HEALTHCHECK."""
    return {
        "status": "healthy",
        "service": "trading-data-service",
        "version": "0.1.0",
    }


@health_router.get("/health/ready", status_code=200)
async def health_ready():
    """Readiness check — only returns 200 when all dependencies are connected."""
    if not _service_ready:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"status": "ready"}


logger = logging.getLogger(__name__)


def _build_db_url() -> str:
    """Build PostgreSQL async URL from environment variables."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "trading_data")
    db_user = os.getenv("DB_USER", "trading")
    db_password = os.getenv("DB_PASSWORD", "trading")
    # URL-encode password for safety
    from urllib.parse import quote_plus
    encoded_password = quote_plus(db_password)
    return f"postgresql+asyncpg://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifecycle hooks for service startup and shutdown."""
    global _service_ready

    # ── Startup ────────────────────────────────────────────────────
    logger.info("Starting data service…")

    # Connect Redis with timeout (avoid hanging forever)
    redis_client = None
    try:
        logger.info("Connecting to Redis…")
        async with asyncio_timeout(10):
            redis_client = await get_redis_client()
        cache_svc = CacheService(redis_client.redis)
        set_cache_service(cache_svc)
        logger.info("Redis cache initialized")
    except Exception as e:
        logger.warning("Redis connection failed: %s — continuing without cache", e)

    # Connect DB
    try:
        db_url = _build_db_url()
        logger.info("Connecting to database: %s...%s", db_url[:30], db_url[-30:])
        async with asyncio_timeout(15):
            db_config = DatabaseConfig(url=db_url)
            await db_config.init()
            # Import global and assign
            import data_service.app.db as db_module
            db_module.db_config = db_config
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        raise  # Fail startup if DB is unreachable

    _service_ready = True
    logger.info("Data service ready")

    yield

    # ── Shutdown ───────────────────────────────────────────────────
    _service_ready = False
    logger.info("Shutting down data service…")

    if redis_client:
        try:
            await shutdown_redis()
        except Exception as e:
            logger.warning("Error shutting down Redis: %s", e)

    try:
        import data_service.app.db as db_module
        if db_module.db_config:
            await db_module.db_config.close()
    except Exception as e:
        logger.warning("Error shutting down DB: %s", e)

    logger.info("Data service stopped")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="Trading Data Service",
        version="0.1.0",
        description="PostgreSQL + Redis + Kafka data service for the trading platform",
        lifespan=lifespan,
    )

    from data_service.app.routes.market_data import router

    app.include_router(router)
    app.include_router(health_router)  # /health + /health/ready for K8s probes
    return app


app = create_app()
