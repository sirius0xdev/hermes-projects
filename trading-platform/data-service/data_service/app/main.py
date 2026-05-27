"""Data service — FastAPI entry point.

Wires together:
- PostgreSQL (DB layer from app.db)
- Redis cache (app.cache)
- Kafka producer/consumer (app.kafka)
- Solana WebSocket ingesters (Helius + Jupiter)
- REST API routes (app.routes)
"""
from __future__ import annotations

import logging
import os
import signal
import threading
from asyncio import timeout as asyncio_timeout
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from fastapi import FastAPI

from data_service.app.cache.client import RedisClient, get_redis_client, shutdown_redis
from data_service.app.cache.service import CacheService
from data_service.app.db import db_config, DatabaseConfig
from data_service.app.routes.market_data import set_cache_service
from data_service.app.kafka.consumer import DataConsumer
from data_service.app.kafka.solana_ingester import HeliusIngester, JupiterIngester
from data_service.app.kafka.topics import KafkaTopics

# Health check router (required for K8s liveness/readiness probes)
from fastapi import APIRouter
health_router = APIRouter(tags=["health"])


# ── Strip Gateway API prefix ──────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable, Awaitable
import logging
_mw_logger = logging.getLogger(__name__)


class _StripPrefixMiddleware(BaseHTTPMiddleware):
    """Strip /api/data from incoming paths so internal routes work directly."""

    def __init__(self, app, prefix: str = ""):
        super().__init__(app)
        self.prefix = prefix.rstrip("/")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.scope.get("path", "")
        if self.prefix and path.startswith(self.prefix):
            request.scope["path"] = path[len(self.prefix):] or "/"
        return await call_next(request)


# Global state
_service_ready = False

# Kafka + ingester globals
_consumer: DataConsumer | None = None
_consume_thread: threading.Thread | None = None
_helius_ingester: HeliusIngester | None = None
_jupiter_ingester: JupiterIngester | None = None


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
    from fastapi import HTTPException
    if not _service_ready:
        raise HTTPException(status_code=503, detail="Service not ready")
    result = {"status": "ready"}
    if _consumer:
        result["consumer_running"] = _consumer.is_running
    if _helius_ingester:
        result["helius_ingester_running"] = _helius_ingester.is_running
    if _jupiter_ingester:
        result["jupiter_ingester_running"] = _jupiter_ingester.is_running
    return result


logger = logging.getLogger(__name__)


# ── Default Kafka topic handlers ─────────────────────────────────

def handle_price_event(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    logger.info("Price event: symbol=%s price=%s", value.get("symbol"), value.get("price"))


def handle_orderbook_event(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    bids = len(value.get("bids", []))
    asks = len(value.get("asks", []))
    logger.info("Orderbook event: symbol=%s bids=%d asks=%d", value.get("symbol"), bids, asks)


def handle_trade_event(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    logger.info("Trade event: symbol=%s side=%s qty=%s price=%s", value.get("symbol"), value.get("side"), value.get("quantity"), value.get("price"))


def handle_news_article(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    logger.info("News article: title=%s tickers=%s", value.get("title"), value.get("tickers"))


def handle_news_analysis(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    logger.info("News analysis: article_id=%s sentiment=%s", value.get("article_id"), value.get("sentiment_score"))


def handle_solana_token_transfer(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    logger.info("Solana token transfer: symbol=%s amount=%s", value.get("token_symbol"), value.get("amount"))


def handle_solana_pool_event(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    logger.info("Solana pool event: action=%s pool=%s", value.get("action"), value.get("pool_address", "")[:8])


def handle_solana_block(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    logger.info("Solana block: slot=%d", value.get("slot"))


DEFAULT_HANDLERS: dict[str, Any] = {
    KafkaTopics.MARKET_PRICES: handle_price_event,
    KafkaTopics.MARKET_ORDERBOOK: handle_orderbook_event,
    KafkaTopics.MARKET_TRADES: handle_trade_event,
    KafkaTopics.NEWS_FEED: handle_news_article,
    KafkaTopics.NEWS_ANALYSIS: handle_news_analysis,
    KafkaTopics.SOLANA_TOKEN_DATA: handle_solana_token_transfer,
    KafkaTopics.SOLANA_POOL_DATA: handle_solana_pool_event,
    KafkaTopics.SOLANA_BLOCK: handle_solana_block,
}


def _build_db_url() -> str:
    """Build PostgreSQL async URL from environment variables."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "trading_data")
    db_user = os.getenv("DB_USER", "trading")
    db_password = os.getenv("DB_PASSWORD", "trading")
    from urllib.parse import quote_plus
    encoded_password = quote_plus(db_password)
    return f"postgresql+asyncpg://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifecycle hooks — connects DB, Redis, Kafka consumer, Solana ingesters."""
    global _service_ready, _consumer, _consume_thread, _helius_ingester, _jupiter_ingester

    # ── Startup ────────────────────────────────────────────────────
    logger.info("Starting data service…")

    # Connect Redis
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
            dbc = DatabaseConfig(url=db_url)
            await dbc.init()
            import data_service.app.db as db_module
            db_module.db_config = dbc
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        raise

    # ── Kafka consumer ─────────────────────────────────────────────
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "trading-kafka.customer1.svc.cluster.local:9092")
    group_id = os.getenv("KAFKA_GROUP_ID", "data-service-consumer")
    auto_offset_reset = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")
    consume_topics_str = os.getenv("CONSUME_TOPICS", ",".join(DEFAULT_HANDLERS.keys()))
    topics = [t.strip() for t in consume_topics_str.split(",") if t.strip()]

    _consumer = DataConsumer(
        bootstrap_servers=bootstrap,
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        topics=topics,
    )
    for topic, handler in DEFAULT_HANDLERS.items():
        if topic in topics:
            _consumer.register_handler(topic, handler)
    _consumer.start()

    _consume_thread = threading.Thread(
        target=_consumer.consume_loop,
        daemon=True,
        name="kafka-consumer-loop",
    )
    _consume_thread.start()
    logger.info("Kafka consumer started: group=%s topics=%s", group_id, topics)

    # ── Solana WebSocket ingesters ─────────────────────────────────
    from data_service.app.kafka.producer import DataProducer

    kafka_broker = os.getenv("KAFKA_BROKER", bootstrap)
    _producer = DataProducer(
        bootstrap_servers=kafka_broker,
        client_id="solana-ws-ingester",
    )
    _producer.start()

    helius_api_key = os.getenv("HELIUS_API_KEY")
    if helius_api_key:
        monitored_mints = os.getenv("MONITORED_SOLANA_MINTS", "")
        monitored_pools = os.getenv("MONITORED_SOLANA_POOLS", "")
        _helius_ingester = HeliusIngester(
            producer=_producer,
            api_key=helius_api_key,
            monitored_mints=[m.strip() for m in monitored_mints.split(",") if m.strip()],
            monitored_pools=[p.strip() for p in monitored_pools.split(",") if p.strip()],
        )
        _helius_ingester.start()
        logger.info("HeliusIngester started")
    else:
        logger.info("HeliusIngester skipped (no HELIUS_API_KEY set)")

    jupiter_api_key = os.getenv("JUPITER_API_KEY")
    _jupiter_ingester = JupiterIngester(
        producer=_producer,
        api_key=jupiter_api_key,
    )
    _jupiter_ingester.start()
    logger.info("JupiterIngester started")

    _service_ready = True
    logger.info("Data service ready")

    yield

    # ── Shutdown ───────────────────────────────────────────────────
    _service_ready = False
    logger.info("Shutting down data service…")

    if _helius_ingester:
        _helius_ingester.stop()
    if _jupiter_ingester:
        _jupiter_ingester.stop()
    _producer.stop()
    if _consumer:
        _consumer.stop()

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
        root_path="/api/data",
    )

    # Strip Gateway API prefix so /api/data/api/v1/... -> /api/v1/...
    app.add_middleware(_StripPrefixMiddleware, prefix="/api/data")

    from data_service.app.routes.market_data import router

    app.include_router(router)
    app.include_router(health_router)  # /health + /health/ready for K8s probes
    return app


app = create_app()
