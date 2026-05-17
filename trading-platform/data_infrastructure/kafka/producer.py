"""Kafka producer for market data ingestion.

Uses aiokafka for async I/O. Serializes messages via Protobuf.
Key = symbol (ensures partition affinity per symbol).

Sources per architecture-reference.md:
- Binance (crypto) via WebSocket feed -> producer
- Finnhub (equities) via WebSocket feed -> producer
- OpenBB SDK polling -> producer
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from aiokafka import AIOKafkaProducer
from google.protobuf.json_format import MessageToDict

from data_infrastructure.kafka.config import kafka_settings
from data_infrastructure.kafka.topics import TopicDef

logger = logging.getLogger(__name__)


def _serialize_message(proto_message) -> bytes:
    """Serialize a Protobuf message to bytes for Kafka."""
    return proto_message.SerializeToString()


def _extract_key(proto_message) -> str:
    """Extract symbol from a protobuf message for Kafka key."""
    return getattr(proto_message, "symbol", "")


class MarketDataProducer:
    """Kafka producer for market data streams."""

    def __init__(self, bootstrap_servers: Optional[str] = None):
        self.bootstrap_servers = bootstrap_servers or kafka_settings.bootstrap_servers

        self.producer: Optional[AIOKafkaProducer] = None
        self._message_count = 0

    async def start(self):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            acks=kafka_settings.producer_acks,
            compression_type=kafka_settings.producer_compression,
            linger_ms=kafka_settings.producer_linger_ms,
            batch_size=kafka_settings.producer_batch_size,
            key_serializer=lambda k: k.encode("utf-8") if k else b"",
        )
        await self.producer.start()
        logger.info("Kafka producer started: %s", self.bootstrap_servers)

    async def stop(self):
        if self.producer:
            await self.producer.stop()
            self.producer = None
            logger.info("Kafka producer stopped")

    async def produce(self, topic: TopicDef, proto_message, key: Optional[str] = None):
        """Produce a single Protobuf-serialized message to a topic."""
        if not self.producer:
            raise RuntimeError("Call start() first")

        kafka_key = key or _extract_key(proto_message)
        value_bytes = _serialize_message(proto_message)

        await self.producer.send(
            topic=topic.name, value=value_bytes, key=kafka_key.encode("utf-8"),
        )
        self._message_count += 1

    async def produce_batch(self, topic: TopicDef, messages: list, key_fn=None):
        """Produce a batch of messages. Messages are auto-dict or protobuf."""
        if not self.producer:
            raise RuntimeError("Call start() first")

        for msg in messages:
            if hasattr(msg, "SerializeToString"):
                # Protobuf message
                value_bytes = _serialize_message(msg)
                kafka_key = (key_fn(msg) if key_fn else _extract_key(msg)).encode("utf-8")
            else:
                # Dict/JSON fallback
                value_bytes = json.dumps(msg).encode("utf-8")
                kafka_key = (key_fn(msg) if key_fn else msg.get("symbol", "")).encode("utf-8")

            await self.producer.send(
                topic=topic.name, value=value_bytes, key=kafka_key,
            )
            self._message_count += 1

    async def flush(self):
        """Ensure all buffered messages are sent."""
        if self.producer:
            await self.producer.flush()
            logger.info("Producer flushed, total messages: %d", self._message_count)

    @property
    def message_count(self) -> int:
        return self._message_count


# Convenience functions for common market data topics
async def produce_ticks(producer: MarketDataProducer, ticks):
    """Produce tick data to market-data.ticks topic."""
    from data_infrastructure.kafka.topics import TICKS
    await producer.produce_batch(TICKS, ticks)


async def produce_trades(producer: MarketDataProducer, trades):
    """Produce trade data to market-data.trades topic."""
    from data_infrastructure.kafka.topics import TRADES
    await producer.produce_batch(TRADES, trades)


async def produce_quotes(producer: MarketDataProducer, quotes):
    """Produce BBO quotes to market-data.quotes topic."""
    from data_infrastructure.kafka.topics import QUOTES
    await producer.produce_batch(QUOTES, quotes)
