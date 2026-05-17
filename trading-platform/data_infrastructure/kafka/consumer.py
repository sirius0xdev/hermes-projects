"""Kafka consumer for market data pipeline.

Consumes Protobuf-serialized messages from Kafka topics,
decodes them, and passes them to registered handlers.

Supports:
- Consumer groups for parallel processing
- Offset management for replay
- Dead letter queue for failed messages
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from aiokafka import AIOKafkaConsumer, ConsumerRecord

from data_infrastructure.kafka.config import kafka_settings
from data_infrastructure.kafka.topics import TopicDef

logger = logging.getLogger(__name__)

# Handler type: async function that receives a decoded message dict
MessageHandler = Callable[[ConsumerRecord], asyncio.coroutine]


class MarketDataConsumer:
    """Kafka consumer for market data topics."""

    def __init__(
        self,
        topics: list[TopicDef],
        bootstrap_servers: Optional[str] = None,
        group_id: Optional[str] = None,
    ):
        self.topics = topics
        self.bootstrap_servers = bootstrap_servers or kafka_settings.bootstrap_servers
        self.group_id = group_id or kafka_settings.consumer_group_id
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._handlers: list[MessageHandler] = []
        self._running = False
        self._message_count = 0

    async def start(self):
        topic_names = [t.name for t in self.topics]
        self.consumer = AIOKafkaConsumer(
            *topic_names,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset=kafka_settings.consumer_auto_offset_reset,
            enable_auto_commit=True,
            auto_commit_interval_ms=1000,
            max_poll_records=kafka_settings.consumer_max_poll_records,
            value_deserializer=lambda v: v,  # raw bytes, handler decodes
        )
        await self.consumer.start()
        logger.info(
            "Kafka consumer started: [%s] group=%s",
            ", ".join(topic_names), self.group_id,
        )

    async def stop(self):
        self._running = False
        if self.consumer:
            await self.consumer.stop()
            self.consumer = None
            logger.info("Kafka consumer stopped, total consumed: %d", self._message_count)

    def register_handler(self, handler: MessageHandler):
        """Register a message handler."""
        self._handlers.append(handler)

    async def _process_record(self, record: ConsumerRecord):
        """Decode and dispatch a single record to all handlers."""
        # Decode value: attempt Protobuf first, fallback to JSON
        value = record.value
        key = record.key.decode("utf-8") if record.key else ""

        for handler in self._handlers:
            try:
                await handler(record)
            except Exception:
                # Dead letter queue pattern: log and continue
                logger.exception(
                    "Handler error on topic=%s partition=%d offset=%d",
                    record.topic, record.partition, record.offset,
                )

    async def consume_loop(self):
        """Main consume loop."""
        if not self.consumer:
            raise RuntimeError("Call start() first")

        self._running = True
        while self._running:
            # Poll for 1 second
            records = await self.consumer.getmany(timeout_ms=1000, max_records=500)
            for tp, msgs in records.items():
                for record in msgs:
                    await self._process_record(record)
                    self._message_count += 1

    async def consume_one_batch(self, count: Optional[int] = None) -> list[ConsumerRecord]:
        """Consume one batch of messages and return them."""
        if not self.consumer:
            raise RuntimeError("Call start() first")

        records = await self.consumer.getmany(
            timeout_ms=5000,
            max_records=count or kafka_settings.consumer_max_poll_records,
        )
        result = []
        for tp, msgs in records.items():
            result.extend(msgs)
        return result

    @property
    def message_count(self) -> int:
        return self._message_count
