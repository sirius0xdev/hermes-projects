"""Kafka consumer service: connects Kafka topics to Redis cache layer.

Lifecycle:
1. On startup: connect to Redis, register topic handlers, start Kafka consumer
2. On shutdown: stop Kafka consumer, close Redis connection

Topic routing:
- market.prices    -> set_latest_price
- market.orderbook -> set_bbo + set_orderbook
- market.trades    -> add_tick
"""

import logging
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.core.config import get_settings
from app.kafka.consumer import DataConsumer
from data_infrastructure.redis.cache import MarketDataCache

logger = logging.getLogger(__name__)

# ── Shared state ──────────────────────────────────────────────────

cache: MarketDataCache | None = None
data_consumer: DataConsumer | None = None
consumer_thread: threading.Thread | None = None


# ── Kafka message handlers ────────────────────────────────────────

def handle_price(message: dict):
    """Handle market.prices messages -> cache latest price."""
    symbol = message.get("symbol", "")
    if not symbol:
        logger.warning("Price message missing symbol, skipping")
        return

    price_data = {
        "price": message.get("price"),
        "bid": message.get("bid"),
        "ask": message.get("ask"),
        "volume": message.get("volume"),
        "ts_ns": message.get("ts_ns"),
        "exchange": message.get("exchange"),
    }

    if cache and cache.set_latest_price(symbol, price_data):
        logger.debug(f"Cached latest price for {symbol}")
    else:
        logger.error(f"Failed to cache price for {symbol}")


def handle_orderbook(message: dict):
    """Handle market.orderbook messages -> cache BBO + full order book."""
    symbol = message.get("symbol", "")
    if not symbol:
        logger.warning("Orderbook message missing symbol, skipping")
        return

    levels = message.get("levels", [])

    # Extract BBO (top bid + top ask)
    bids = [l for l in levels if l.get("side") == "bid"]
    asks = [l for l in levels if l.get("side") == "ask"]

    if bids and asks:
        best_bid = max(bids, key=lambda x: x.get("price", 0))
        best_ask = min(asks, key=lambda x: x.get("price", float("inf")))
        bbo_data = {
            "bid": best_bid.get("price"),
            "bid_size": best_bid.get("size"),
            "ask": best_ask.get("price"),
            "ask_size": best_ask.get("size"),
            "ts_ns": message.get("ts_ns"),
        }
        if cache:
            cache.set_bbo(symbol, bbo_data)

    # Store full order book levels
    if cache and levels:
        cache.set_orderbook(symbol, levels)

    logger.debug(f"Cached orderbook for {symbol} ({len(levels)} levels)")


def handle_trade(message: dict):
    """Handle market.trades messages -> append tick to stream."""
    symbol = message.get("symbol", "")
    if not symbol:
        logger.warning("Trade message missing symbol, skipping")
        return

    tick_data = {
        "price": str(message.get("price", "")),
        "side": message.get("side", ""),
        "size": str(message.get("size", "")),
        "exchange": message.get("exchange", ""),
        "ts_ns": str(message.get("ts_ns", "")),
    }

    entry_id = ""
    if cache:
        entry_id = cache.add_tick(symbol, tick_data)

    logger.debug(f"Added tick for {symbol} (stream_id={entry_id})")


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: connect Redis, start Kafka consumer."""
    global cache, data_consumer, consumer_thread

    # Startup
    settings = get_settings()
    logger.info(f"Starting {settings.app_name}")

    # 1. Connect Redis
    cache = MarketDataCache()
    await cache.connect()
    logger.info("Redis cache connected")

    # 2. Initialize consumer and register handlers
    data_consumer = DataConsumer(cache)
    data_consumer.register_handler(settings.kafka_topic_prices, handle_price)
    data_consumer.register_handler(settings.kafka_topic_orderbook, handle_orderbook)
    data_consumer.register_handler(settings.kafka_topic_trades, handle_trade)

    # 3. Start consumer in background thread
    consumer_thread = threading.Thread(
        target=data_consumer.start, daemon=True, name="kafka-consumer"
    )
    consumer_thread.start()
    logger.info("Kafka consumer thread started")

    yield

    # Shutdown
    if data_consumer:
        data_consumer.stop()
    if consumer_thread:
        consumer_thread.join(timeout=5)
    if cache:
        await cache.disconnect()
    logger.info("Shut down complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "Real-time market data service. Consumes market data from "
            "Kafka topics and caches in Redis for low-latency reads."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health endpoint ───────────────────────────────────────────

    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check: reports Redis connection status and cache hit rate."""
        global cache

        redis_connected = False
        cache_stats = {"hits": 0, "misses": 0, "hit_rate": 0.0}

        if cache:
            redis_connected = cache.check_connection()
            cache_stats = cache.get_cache_hit_rate()

        status = "healthy" if redis_connected else "degraded"

        return {
            "status": status,
            "service": settings.app_name,
            "version": "1.0.0",
            "redis": {
                "connected": redis_connected,
                "host": settings.redis_host,
                "port": settings.redis_port,
            },
            "cache_stats": cache_stats,
        }

    return app


# Application instance for ASGI servers
app = create_app()
