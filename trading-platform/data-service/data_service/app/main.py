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
import asyncio
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
from data_service.app.scanners.opportunity_scanner import OpportunityScanner
from data_service.app.scanners.binance_prices import BinancePriceClient

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
_opportunity_scanner: OpportunityScanner | None = None
_opp_scan_thread: threading.Thread | None = None


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
    """Readiness check — verifies DB + Redis connectivity with timeouts.

    Returns 200 when the service is functionally ready to accept traffic.
    External dependencies (Kafka, Solana) are best-effort and reported
    but don't block readiness.
    """
    from fastapi import HTTPException

    if not _service_ready:
        raise HTTPException(status_code=503, detail="Service not ready")

    deps: dict[str, bool] = {}

    # ── Check Redis ──────────────────────────────────────────────
    try:
        import data_service.app.routes.market_data as md_routes
        cache_svc = md_routes.CACHE_SVC
        if cache_svc is not None:
            async with asyncio_timeout(5):
                await cache_svc.redis.ping()
            deps["redis"] = True
        else:
            deps["redis"] = False
    except Exception:
        deps["redis"] = False

    # ── Check DB ──────────────────────────────────────────────────
    try:
        import data_service.app.db as db_module
        from sqlalchemy import text as sa_text
        if db_module.db_config is not None:
            async with asyncio_timeout(5):
                async with db_module.db_config.session_factory() as sess:
                    await sess.execute(sa_text("SELECT 1"))
            deps["postgres"] = True
        else:
            deps["postgres"] = False
    except Exception:
        deps["postgres"] = False

    # If DB or Redis is down, not ready
    if not deps.get("postgres") or not deps.get("redis"):
        raise HTTPException(
            status_code=503,
            detail=f"Dependencies not healthy: {deps}",
        )

    result = {"status": "ready", "dependencies": deps}
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


def handle_opportunity(message: dict[str, Any]) -> None:
    value = message.get("value", {})
    logger.info("Opportunity: type=%s symbol=%s spread=%.2f%%", value.get("opportunity_type"), value.get("symbol"), value.get("spread_pct"))


DEFAULT_HANDLERS: dict[str, Any] = {
    KafkaTopics.MARKET_PRICES: handle_price_event,
    KafkaTopics.MARKET_ORDERBOOK: handle_orderbook_event,
    KafkaTopics.MARKET_TRADES: handle_trade_event,
    KafkaTopics.NEWS_FEED: handle_news_article,
    KafkaTopics.NEWS_ANALYSIS: handle_news_analysis,
    KafkaTopics.SOLANA_TOKEN_DATA: handle_solana_token_transfer,
    KafkaTopics.SOLANA_POOL_DATA: handle_solana_pool_event,
    KafkaTopics.SOLANA_BLOCK: handle_solana_block,
    KafkaTopics.OPPORTUNITIES: handle_opportunity,
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
        cache_svc = None

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

    # ── Seed Redis cache: Chainlink (primary) → Binance (fallback) ──
    if cache_svc is not None:
        # Primary: Chainlink Data API
        try:
            logger.info("Seeding Redis cache from Chainlink Data API…")
            from data_service.app.scanners.chainlink_prices import ChainlinkPriceClient

            chainlink = ChainlinkPriceClient()
            async with asyncio_timeout(25):
                prices = await chainlink.scan_once()
            await chainlink.close()

            if prices:
                # Batch-write prices to cache
                price_updates = []
                for sym, cp in prices.items():
                    price_updates.append({
                        "exchange": "chainlink",
                        "symbol": sym,
                        "bid": f"{cp.bid:.8f}",
                        "ask": f"{cp.ask:.8f}",
                        "last": f"{cp.price:.8f}",
                        "volume_24h": f"{cp.volume_24h:.4f}",
                    })
                if price_updates:
                    await cache_svc.set_price_batch(price_updates)
                    logger.info("Seeded %d Chainlink prices in Redis cache", len(price_updates))

                # Fetch 1h candles for top symbols
                for sym in list(prices.keys())[:5]:
                    try:
                        candles = await chainlink.get_candles(sym, interval="1h", limit=50)
                        candle_dicts = [
                            {
                                "time": c.time,
                                "open": c.open,
                                "high": c.high,
                                "low": c.low,
                                "close": c.close,
                                "volume": c.volume,
                            }
                            for c in candles
                        ]
                        if candle_dicts:
                            await cache_svc.set_candles(
                                exchange="chainlink", symbol=sym, interval="1h", candles=candle_dicts
                            )
                    except Exception:
                        logger.debug("Failed to seed candles for %s", sym)
            else:
                raise ValueError("Chainlink returned 0 prices")
        except Exception:
            logger.warning("Chainlink cache seeding failed — falling back to Binance")
            # Fallback: Binance public API
            try:
                logger.info("Seeding Redis cache from Binance public API…")
                binance = BinancePriceClient()
                async with asyncio_timeout(20):
                    prices = await binance.scan_once()

                price_updates = []
                for sym, bp in prices.items():
                    price_updates.append({
                        "exchange": "binance",
                        "symbol": sym,
                        "bid": f"{bp.bid:.8f}",
                        "ask": f"{bp.ask:.8f}",
                        "last": f"{bp.price:.8f}",
                        "volume_24h": f"{bp.volume_24h:.4f}",
                    })
                if price_updates:
                    await cache_svc.set_price_batch(price_updates)
                    logger.info("Seeded %d Binance prices in Redis cache", len(price_updates))

                for sym in list(prices.keys())[:5]:
                    try:
                        candles = await binance.get_candles(sym, interval="1h", limit=50)
                        candle_dicts = [
                            {
                                "time": c.time,
                                "open": c.open,
                                "high": c.high,
                                "low": c.low,
                                "close": c.close,
                                "volume": c.volume,
                            }
                            for c in candles
                        ]
                        if candle_dicts:
                            await cache_svc.set_candles(
                                exchange="binance", symbol=sym, interval="1h", candles=candle_dicts
                            )
                    except Exception:
                        logger.debug("Failed to seed candles for %s", sym)

                await binance.close()
            except Exception:
                logger.warning("Binance cache seeding also failed — will retry on first request")
    else:
        logger.info("Skipping cache seed (Redis unavailable)")

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

    # ── Opportunity scanner ──────────────────────────────────────
    _opportunity_scanner = OpportunityScanner(
        producer=_producer,
        min_spread_pct=0.3,
    )

    def _run_opp_scan_loop():
        """Run opportunity scanner in its own event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Run first scan synchronously, then loop
            loop.run_until_complete(_opportunity_scanner.scan_once())
            while _opportunity_scanner._running:
                loop.run_until_complete(_opportunity_scanner.scan_once())
                loop.run_until_complete(asyncio.sleep(_opportunity_scanner.poll_interval))
        except Exception:
            logger.exception("Opportunity scanner loop crashed")
        finally:
            loop.run_until_complete(_opportunity_scanner.close())
            loop.close()

    _opp_scan_thread = threading.Thread(
        target=_run_opp_scan_loop,
        daemon=True,
        name="opportunity-scanner",
    )
    _opp_scan_thread.start()
    logger.info("Opportunity scanner started")

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
    if _opportunity_scanner:
        _opportunity_scanner.stop()
    _producer.stop()
    if _consumer:
        _consumer.stop()

    if redis_client:
        try:
            async with asyncio_timeout(10):
                await shutdown_redis()
        except asyncio.TimeoutError:
            logger.warning("Redis shutdown timed out")
        except Exception as e:
            logger.warning("Error shutting down Redis: %s", e)

    try:
        async with asyncio_timeout(10):
            import data_service.app.db as db_module
            if db_module.db_config:
                await db_module.db_config.close()
    except asyncio.TimeoutError:
        logger.warning("DB shutdown timed out")
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

    # Strip Gateway API prefix so /api/data/api/v1/... -> /api/v1/...
    app.add_middleware(_StripPrefixMiddleware, prefix="/api/data")

    from data_service.app.routes.market_data import router

    app.include_router(router)
    from data_service.app.routes.opportunities import router as opp_router
    app.include_router(opp_router)
    app.include_router(health_router)  # /health + /health/ready for K8s probes
    return app


app = create_app()
