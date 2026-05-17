"""Kafka consumer for market data streaming.

Provides consumers for each market data topic with
callback-based message handling and group-based consumer
coordination for downstream services.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

from kafka import KafkaConsumer
from kafka.structs import TopicPartition

from data_service.app.kafka.topics import KafkaTopics

logger = logging.getLogger(__name__)


class DataConsumer:
    """Kafka consumer for market data events.

    Usage:
        consumer = DataConsumer(
            bootstrap_servers="kafka:9092",
            group_id="trading-engine",
            topics=[KafkaTopics.MARKET_PRICES, KafkaTopics.MARKET_TRADES],
        )
        consumer.start()

        consumer.register_handler(KafkaTopics.MARKET_PRICES, handle_price_event)
        consumer.consume_loop()
        consumer.stop()
    """

    def __init__(
        self,
        bootstrap_servers: str = "kafka.customer1.svc.cluster.local:9092",
        group_id: str = "data-service-consumer",
        auto_offset_reset: str = "latest",
        enable_auto_commit: bool = True,
        topics: Optional[list[str]] = None,
        **consumer_kwargs: Any,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit
        self._topics = topics or []
        self._extra_kwargs = consumer_kwargs
        self._consumer: Optional[KafkaConsumer] = None
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._running = False

    def start(self) -> None:
        """Initialize the Kafka consumer and subscribe to topics."""
        self._consumer = KafkaConsumer(
            bootstrap_servers=self.bootstrap_servers.split(","),
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=self.enable_auto_commit,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            key_deserializer=lambda k: (k.decode("utf-8") if k else None),
            **self._extra_kwargs,
        )
        if self._topics:
            self._consumer.subscribe(self._topics)
        self._running = True
        logger.info(
            "Kafka consumer started (group=%s, topics=%s)",
            self.group_id, ", ".join(self._topics)
        )

    def stop(self) -> None:
        """Stop consuming and close the consumer."""
        self._running = False
        if self._consumer:
            self._consumer.unsubscribe()
            self._consumer.close(timeout=10)
            self._consumer = None
            logger.info("Kafka consumer closed")

    def register_handler(
        self, topic: str, handler: Callable[[dict[str, Any]], Any]
    ) -> None:
        """Register a message handler for a specific topic."""
        self._handlers[topic] = handler

    def get_topic_handlers(self) -> dict[str, Callable]:
        """Return all registered topic handlers."""
        return dict(self._handlers)

    def consume_once(self, timeout_ms: int = 5000) -> int:
        """Poll for messages once and process them.

        Returns the number of messages processed.
        """
        if not self._consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        messages = self._consumer.poll(timeout_ms=timeout_ms)
        count = 0

        for topic_partition, records in messages.items():
            topic = topic_partition.topic
            handler = self._handlers.get(topic)
            if handler is None:
                continue

            for record in records:
                try:
                    message = {
                        "topic": record.topic,
                        "partition": record.partition,
                        "offset": record.offset,
                        "key": record.key,
                        "value": record.value,
                        "timestamp": record.timestamp,
                        "headers": record.headers,
                    }
                    handler(message)
                    count += 1
                except Exception:
                    logger.exception(
                        "Error processing message from %s [p=%d, o=%d]",
                        topic, record.partition, record.offset,
                    )
        return count

    def consume_loop(self, poll_timeout_ms: int = 1000) -> None:
        """Continuously poll and process messages until stopped."""
        logger.info("Starting consume loop (group=%s)", self.group_id)
        while self._running:
            try:
                count = self.consume_once(timeout_ms=poll_timeout_ms)
                if count > 0:
                    logger.debug("Processed %d messages", count)
            except Exception:
                logger.exception("Error in consume loop")
                time.sleep(1)
        logger.info("Consume loop ended")

    def seek_to_beginning(self, topics: Optional[list[str]] = None) -> None:
        """Reset consumer offsets to the beginning."""
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        topics = topics or list(self._topics)
        partitions = [
            TopicPartition(t, p)
            for t in topics
            for p in (self._consumer.partitions_for_topic(t) or set())
        ]
        self._consumer.seek_to_beginning(*partitions)

    def get_consumer_lag(self, topics: Optional[list[str]] = None) -> dict[str, int]:
        """Get consumer lag (unprocessed messages) per topic."""
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        topics = topics or list(self._topics)
        lag = {}
        for topic in topics:
            tps = [
                TopicPartition(topic, p)
                for p in (self._consumer.partitions_for_topic(topic) or set())
            ]
            end = self._consumer.end_offsets(tps)
            beginning = self._consumer.beginning_offsets(tps)
            lag[topic] = sum(end.get(tp, 0) - beginning.get(tp, 0) for tp in tps)
        return lag

    @property
    def is_running(self) -> bool:
        return self._running and self._consumer is not None

    @property
    def consumer(self) -> KafkaConsumer:
        if self._consumer is None:
            raise RuntimeError("Consumer not started")
        return self._consumer
