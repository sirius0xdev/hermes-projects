"""Kafka producer for market data streaming.

Provides type-safe producers for each market data topic:
- Prices: real-time price updates from exchanges
- Orderbook: order book snapshots and updates
- Trades: individual trade executions
- News: news articles and analysis
- Signals: trading signals for downstream consumption

Uses kafka-python-ng with configurable batch settings,
compression, and delivery callbacks.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from kafka import KafkaProducer
from kafka.errors import KafkaError
from pydantic import BaseModel

from data_service.app.kafka.config import get_topic_config
from data_service.app.kafka.topics import KafkaTopics

logger = logging.getLogger(__name__)


class DataProducer:
    """Kafka producer for market data events.

    Usage:
        producer = DataProducer(bootstrap_servers="kafka:9092")
        producer.start()

        # Send typed events
        producer.send_price(price_event)
        producer.send_orderbook(orderbook_event)

        # Or send raw messages
        producer.send_message(topic, key, value)

        producer.stop()
    """

    def __init__(
        self,
        bootstrap_servers: str = "kafka.customer1.svc.cluster.local:9092",
        client_id: str = "data-service-producer",
        **producer_kwargs: Any,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self._extra_kwargs = producer_kwargs
        self._producer: Optional[KafkaProducer] = None

    def start(self) -> None:
        """Initialize the Kafka producer connection."""
        from data_service.app.kafka.schemas import PriceSource

        producer_config = {
            "bootstrap_servers": self.bootstrap_servers.split(","),
            "client_id": self.client_id,
            "value_serializer": lambda v: json.dumps(v, default=self._json_serializer).encode("utf-8"),
            "key_serializer": lambda k: k.encode("utf-8") if isinstance(k, str) else k,
            "acks": "all",
            "retries": 3,
            "compression_type": "lz4",
            "batch_size": 16384,
            "linger_ms": 5,
            "buffer_memory": 33554432,
            **self._extra_kwargs,
        }
        self._producer = KafkaProducer(**producer_config)
        logger.info("Kafka producer connected to %s", self.bootstrap_servers)

    def stop(self) -> None:
        """Flush pending messages and close the producer."""
        if self._producer:
            logger.info("Flushing Kafka producer...")
            self._producer.flush(timeout=10)
            self._producer.close(timeout=10)
            self._producer = None
            logger.info("Kafka producer closed")

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """Custom JSON serializer for Pydantic models and special types."""
        from datetime import datetime
        from decimal import Decimal
        from enum import Enum

        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def send_message(
        self,
        topic: str,
        key: str,
        value: Any,
        headers: Optional[list[tuple[str, bytes]]] = None,
    ) -> None:
        """Send a raw message to any topic."""
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        try:
            if isinstance(value, BaseModel):
                value = json.dumps(value.model_dump(mode="json"), default=self._json_serializer)

            future = self._producer.send(
                topic, key=key, value=value, headers=headers or []
            )
            record_metadata = future.get(timeout=10)
            logger.debug(
                "Sent to %s partition=%d offset=%d",
                record_metadata.topic,
                record_metadata.partition,
                record_metadata.offset,
            )
        except KafkaError as e:
            logger.error("Failed to send message to %s: %s", topic, e)
            raise

    def send_price(self, event) -> None:
        """Send a market price event. Key: symbol."""
        from data_service.app.kafka.schemas import MarketPriceEvent

        if not isinstance(event, MarketPriceEvent):
            raise TypeError("Expected MarketPriceEvent")
        headers = [
            ("event_type", b"price"),
            ("source", event.source.value.encode()),
        ]
        self.send_message(KafkaTopics.MARKET_PRICES, key=event.symbol, value=event, headers=headers)

    def send_orderbook(self, event) -> None:
        """Send an orderbook snapshot/update. Key: symbol."""
        from data_service.app.kafka.schemas import OrderbookEvent

        if not isinstance(event, OrderbookEvent):
            raise TypeError("Expected OrderbookEvent")
        headers = [("event_type", b"orderbook"), ("source", event.source.value.encode())]
        self.send_message(KafkaTopics.MARKET_ORDERBOOK, key=event.symbol, value=event, headers=headers)

    def send_trade(self, event) -> None:
        """Send a trade execution event. Key: symbol."""
        from data_service.app.kafka.schemas import TradeEvent

        if not isinstance(event, TradeEvent):
            raise TypeError("Expected TradeEvent")
        headers = [("event_type", b"trade"), ("source", event.source.value.encode())]
        self.send_message(KafkaTopics.MARKET_TRADES, key=event.symbol, value=event, headers=headers)

    def send_news_article(self, article) -> None:
        """Send a news article. Key: article_id."""
        from data_service.app.kafka.schemas import NewsArticle

        if not isinstance(article, NewsArticle):
            raise TypeError("Expected NewsArticle")
        headers = [("event_type", b"news_article")]
        self.send_message(KafkaTopics.NEWS_FEED, key=article.article_id, value=article, headers=headers)

    def send_news_analysis(self, analysis) -> None:
        """Send analyzed news article. Key: article_id."""
        from data_service.app.kafka.schemas import NewsAnalysisEvent

        if not isinstance(analysis, NewsAnalysisEvent):
            raise TypeError("Expected NewsAnalysisEvent")
        headers = [("event_type", b"news_analysis")]
        self.send_message(KafkaTopics.NEWS_ANALYSIS, key=analysis.article_id, value=analysis, headers=headers)

    def send_trading_signal(self, signal) -> None:
        """Send a trading signal. Key: signal_id."""
        from data_service.app.kafka.schemas import TradingSignal

        if not isinstance(signal, TradingSignal):
            raise TypeError("Expected TradingSignal")
        headers = [
            ("event_type", b"trading_signal"),
            ("signal_type", signal.signal_type.value.encode()),
        ]
        self.send_message(KafkaTopics.TRADING_SIGNALS, key=signal.signal_id, value=signal, headers=headers)

    # ── Solana blockchain events ─────────────────────────────────────

    def send_solana_token_transfer(self, event) -> None:
        """Send a Solana SPL token transfer. Key: mint address."""
        from data_service.app.kafka.schemas import SolanaTokenTransfer

        if not isinstance(event, SolanaTokenTransfer):
            raise TypeError("Expected SolanaTokenTransfer")
        headers = [
            ("event_type", b"solana_token_transfer"),
            ("source", b"helius"),
        ]
        self.send_message(
            KafkaTopics.SOLANA_TOKEN_DATA, key=event.mint, value=event, headers=headers
        )

    def send_solana_pool_event(self, event) -> None:
        """Send a Solana pool LP event. Key: pool_address."""
        from data_service.app.kafka.schemas import SolanaPoolEvent

        if not isinstance(event, SolanaPoolEvent):
            raise TypeError("Expected SolanaPoolEvent")
        headers = [
            ("event_type", b"solana_pool"),
            ("source", b"helius"),
        ]
        self.send_message(
            KafkaTopics.SOLANA_POOL_DATA, key=event.pool_address, value=event, headers=headers
        )

    def send_solana_block_event(self, event) -> None:
        """Send a Solana block event. Key: slot number."""
        from data_service.app.kafka.schemas import SolanaBlockEvent

        if not isinstance(event, SolanaBlockEvent):
            raise TypeError("Expected SolanaBlockEvent")
        headers = [
            ("event_type", b"solana_block"),
            ("source", b"helius"),
        ]
        self.send_message(
            KafkaTopics.SOLANA_BLOCK, key=str(event.slot), value=event, headers=headers
        )

    def send_jupiter_swap(self, event) -> None:
        """Send a Jupiter DEX swap event. Key: in_mint."""
        from data_service.app.kafka.schemas import JupiterSwapEvent

        if not isinstance(event, JupiterSwapEvent):
            raise TypeError("Expected JupiterSwapEvent")
        headers = [
            ("event_type", b"jupiter_swap"),
            ("source", b"jupiter"),
        ]
        self.send_message(
            KafkaTopics.MARKET_TRADES, key=event.in_mint, value=event, headers=headers
        )

    @property
    def is_running(self) -> bool:
        return self._producer is not None
