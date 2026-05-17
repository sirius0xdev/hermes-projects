"""Data service — FastAPI entry point.

Wires together:
- PostgreSQL (DB layer from app.db)
- Redis cache (app.cache)
- Kafka producer/consumer (app.kafka)
- REST API routes (app.routes)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from data_service.app.cache.client import RedisClient, get_redis_client, shutdown_redis
from data_service.app.cache.service import CacheService
from data_service.app.routes.market_data import set_cache_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifecycle hooks for service startup and shutdown."""
    # ── Startup ────────────────────────────────────────────────────
    logger.info("Starting data service…")

    # Connect Redis
    logger.info("Connecting to Redis…")
    redis_client = await get_redis_client()
    cache_svc = CacheService(redis_client.redis)
    set_cache_service(cache_svc)
    logger.info("Redis cache initialized")

    # TODO: init DB, Kafka

    yield

    # ── Shutdown ───────────────────────────────────────────────────
    logger.info("Shutting down data service…")
    await shutdown_redis()
    # TODO: close DB, Kafka

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
    return app


app = create_app()
