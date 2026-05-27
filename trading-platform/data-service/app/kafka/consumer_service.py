"""Consumer service: Kafka consumer with health check endpoint.

Runs the DataConsumer in a background thread while exposing
a FastAPI health check on port 8001 for K8s liveness/readiness probes.

Usage:
    python -m data_service.app.kafka.consumer_service

Environment variables:
    KAFKA_BOOTSTRAP_SERVERS  - Kafka broker address (default: kafka.customer1.svc.cluster.local:9092)
    KAFKA_GROUP_ID           - Consumer group ID (default: data-service-consumer)
    KAFKA_AUTO_OFFSET_RESET  - Offset reset strategy (default: latest)
    CONSUME_TOPICS           - Comma-separated list of topics to consume
    DATABASE_URL             - PostgreSQL connection URL
    REDIS_URL                - Redis connection URL
    LOG_LEVEL                - Logging level (default: INFO)
"""
from __future__ import annotations

import logging
import os
import signal
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from data_service.app.kafka.consumer import DataConsumer
from data_service.app.kafka.solana_ingester import HeliusIngester, JupiterIngester
from data_service.app.kafka.topics import KafkaTopics

logger = logging.getLogger(__name__)


# --- Default topic handlers --- #

def handle_price_event(message: dict[str, Any]) -> None:
    """Handle incoming market price events."""
    value = message.get("value", {})
    symbol = value.get("symbol", "unknown")
    price = value.get("price", "N/A")
    logger.info(
        "Price event: symbol=%s price=%s offset=%d",
        symbol, price, message.get("offset"),
    )


def handle_orderbook_event(message: dict[str, Any]) -> None:
    """Handle incoming orderbook events."""
    value = message.get("value", {})
    symbol = value.get("symbol", "unknown")
    num_bids = len(value.get("bids", []))
    num_asks = len(value.get("asks", []))
    logger.info(
        "Orderbook event: symbol=%s bids=%d asks=%d offset=%d",
        symbol, num_bids, num_asks, message.get("offset"),
    )


def handle_trade_event(message: dict[str, Any]) -> None:
    """Handle incoming trade events."""
    value = message.get("value", {})
    symbol = value.get("symbol", "unknown")
    side = value.get("side", "unknown")
    quantity = value.get("quantity", "N/A")
    price = value.get("price", "N/A")
    logger.info(
        "Trade event: symbol=%s side=%s qty=%s price=%s offset=%d",
        symbol, side, quantity, price, message.get("offset"),
    )


def handle_news_article(message: dict[str, Any]) -> None:
    """Handle incoming news articles."""
    value = message.get("value", {})
    title = value.get("title", "unknown")
    tickers = value.get("tickers", [])
    logger.info(
        "News article: title=%s tickers=%s offset=%d",
        title, tickers, message.get("offset"),
    )


def handle_news_analysis(message: dict[str, Any]) -> None:
    """Handle incoming news analysis events."""
    value = message.get("value", {})
    article_id = value.get("article_id", "unknown")
    sentiment = value.get("sentiment_score", "N/A")
    logger.info(
        "News analysis: article_id=%s sentiment=%s offset=%d",
        article_id, sentiment, message.get("offset"),
    )


def handle_solana_token_transfer(message: dict[str, Any]) -> None:
    """Handle incoming Solana token transfer events."""
    value = message.get("value", {})
    symbol = value.get("token_symbol", "unknown")
    amount = value.get("amount", "N/A")
    mint = value.get("mint", "unknown")[:8]
    logger.info(
        "Solana token transfer: symbol=%s amount=%s mint=%s… offset=%d",
        symbol, amount, mint, message.get("offset"),
    )


def handle_solana_pool_event(message: dict[str, Any]) -> None:
    """Handle incoming Solana pool LP events."""
    value = message.get("value", {})
    action = value.get("action", "unknown")
    pool = value.get("pool_address", "unknown")[:8]
    logger.info(
        "Solana pool event: action=%s pool=%s… offset=%d",
        action, pool, message.get("offset"),
    )


def handle_solana_block(message: dict[str, Any]) -> None:
    """Handle incoming Solana block events."""
    value = message.get("value", {})
    slot = value.get("slot", 0)
    logger.info("Solana block: slot=%d offset=%d", slot, message.get("offset"))


# Map topics to handlers
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

# Global instances (set during lifespan)
_consumer: DataConsumer | None = None
_consume_thread: threading.Thread | None = None
_helius_ingester: HeliusIngester | None = None
_jupiter_ingester: JupiterIngester | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start Kafka consumer and WebSocket ingesters on startup, stop on shutdown."""
    global _consumer, _consume_thread, _helius_ingester, _jupiter_ingester

    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.customer1.svc.cluster.local:9092")
    group_id = os.getenv("KAFKA_GROUP_ID", "data-service-consumer")
    auto_offset_reset = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")
    consume_topics_str = os.getenv(
        "CONSUME_TOPICS",
        ",".join(DEFAULT_HANDLERS.keys()),
    )

    topics = [t.strip() for t in consume_topics_str.split(",") if t.strip()]

    _consumer = DataConsumer(
        bootstrap_servers=bootstrap,
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        topics=topics,
    )

    # Register handlers
    for topic, handler in DEFAULT_HANDLERS.items():
        if topic in topics:
            _consumer.register_handler(topic, handler)

    # Start consumer
    _consumer.start()

    # Run consume loop in background thread
    _consume_thread = threading.Thread(
        target=_consumer.consume_loop,
        daemon=True,
        name="kafka-consumer-loop",
    )
    _consume_thread.start()

    # Start Solana WebSocket ingesters (sidecars)
    # They use the same Kafka producer to publish events
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
        logger.info("HeliusIngester started (key=%s…)", helius_api_key[:8])
    else:
        logger.info("HeliusIngester skipped (no HELIUS_API_KEY set)")

    # Jupiter ingester (no API key required for public WS)
    jupiter_api_key = os.getenv("JUPITER_API_KEY")
    _jupiter_ingester = JupiterIngester(
        producer=_producer,
        api_key=jupiter_api_key,
    )
    _jupiter_ingester.start()
    logger.info("JupiterIngester started")

    logger.info(
        "Consumer service started: group=%s topics=%s",
        group_id, topics,
    )

    yield

    # Shutdown
    if _helius_ingester:
        _helius_ingester.stop()
    if _jupiter_ingester:
        _jupiter_ingester.stop()
    _producer.stop()
    if _consumer:
        _consumer.stop()
    logger.info("Consumer service stopped")


app = FastAPI(
    title="Data Service Consumer",
    description="Kafka consumer for market data streaming",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    """Health check endpoint for K8s probes."""
    return {
        "status": "healthy",
        "consumer_running": _consumer.is_running if _consumer else False,
        "helius_ingester_running": _helius_ingester.is_running if _helius_ingester else False,
        "jupiter_ingester_running": _jupiter_ingester.is_running if _jupiter_ingester else False,
    }


@app.get("/consumer/lag")
def consumer_lag():
    """Get consumer lag per topic."""
    if not _consumer or not _consumer.is_running:
        return {"error": "Consumer not running"}
    try:
        lag = _consumer.get_consumer_lag()
        return {"lag": lag}
    except Exception as e:
        return {"error": str(e)}


@app.get("/consumer/handlers")
def list_handlers():
    """List registered topic handlers."""
    if not _consumer:
        return {"error": "Consumer not running"}
    handlers = _consumer.get_topic_handlers()
    return {
        "handlers": {topic: handler.__name__ for topic, handler in handlers.items()},
    }


def main() -> None:
    """CLI entry point for the consumer service."""
    import uvicorn

    log_level = os.getenv("LOG_LEVEL", "INFO").lower()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
