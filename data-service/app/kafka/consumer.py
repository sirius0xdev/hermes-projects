"""Kafka consumer for market data topics."""

import json
import logging
from typing import Optional, Callable, Any

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from app.core.config import get_settings
from data_infrastructure.redis.cache import MarketDataCache

logger = logging.getLogger(__name__)


class DataConsumer:
    """Multi-topic Kafka consumer that routes messages to Redis cache handlers.

    Topic routing:
    - market.prices   -> set_latest_price
    - market.orderbook -> set_bbo + set_orderbook
    - market.trades   -> add_tick
    """

    def __init__(self, cache: MarketDataCache):
        self._cache = cache
        self._consumer: Optional[KafkaConsumer] = None
        self._running = False
        self._handlers: dict[str, Callable] = {}

    def register_handler(self, topic: str, handler: Callable[[dict], None]):
        """Register a handler function for a Kafka topic.

        Args:
            topic: Kafka topic name
            handler: Function that processes a single message dict
        """
        self._handlers[topic] = handler
        logger.info(f"Registered handler for topic: {topic}")

    def start(self):
        """Start consuming from all configured topics."""
        settings = get_settings()

        topics = [
            settings.kafka_topic_prices,
            settings.kafka_topic_orderbook,
            settings.kafka_topic_trades,
        ]

        self._consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            auto_offset_reset=settings.kafka_auto_offset_reset,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            enable_auto_commit=True,
            auto_commit_interval_ms=1000,
        )

        self._running = True
        logger.info(
            f"DataConsumer started (topics={topics}, "
            f"group={settings.kafka_group_id})"
        )

        try:
            while self._running:
                records = self._consumer.poll(timeout_ms=100)
                for topic_partition, messages in records.items():
                    topic_name = topic_partition.topic
                    handler = self._handlers.get(topic_name)
                    if handler is None:
                        logger.warning(f"No handler for topic: {topic_name}")
                        continue
                    for message in messages:
                        self._process_message(topic_name, message, handler)
        except KafkaError:
            logger.exception("Kafka consumer error")
            self.stop()
        except Exception:
            logger.exception("Unexpected consumer error")
            self.stop()

    def _process_message(self, topic: str, message, handler: Callable):
        """Process a single message through the handler."""
        try:
            logger.debug(
                f"Processing message from {topic}: "
                f"partition={message.partition}, offset={message.offset}"
            )
            handler(message.value)
        except Exception:
            logger.exception(
                f"Error processing message at topic={topic} "
                f"partition={message.partition} offset={message.offset}"
            )

    @property
    def consumer(self) -> Optional[KafkaConsumer]:
        return self._consumer

    def stop(self):
        """Stop consuming and close the consumer."""
        self._running = False
        if self._consumer:
            self._consumer.close()
            logger.info("DataConsumer closed")
