"""Main entry point for data infrastructure service.

Provides async start/stop lifecycle for Redis cache and Kafka producer/consumer.
"""
from __future__ import annotations

import asyncio
import logging

from data_infrastructure.config import settings, setup_logging
from data_infrastructure.kafka.topics import ALL_TOPICS
from data_infrastructure.kafka.producer import MarketDataProducer
from data_infrastructure.kafka.consumer import MarketDataConsumer
from data_infrastructure.redis.cache import MarketDataCache

logger = logging.getLogger(__name__)


class DataInfraService:
    """Lifecycle manager for the data infrastructure layer."""

    def __init__(self):
        self.redis_cache = MarketDataCache(redis_url=settings.redis_url)
        self.producer = MarketDataProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
        )
        self.consumer = MarketDataConsumer(
            topics=[t for t in ALL_TOPICS if t.name.startswith("market-data")],
            bootstrap_servers=settings.kafka_bootstrap_servers,
        )

    async def start(self):
        """Initialize all connections and create topics if needed."""
        setup_logging()
        logger.info("Starting data infrastructure layer...")

        await self.redis_cache.connect()
        logger.info("Redis connected: %s", settings.redis_url)

        await self.producer.start()
        logger.info("Kafka producer started: %s", settings.kafka_bootstrap_servers)

        await self.consumer.start()

        logger.info("Data infrastructure layer started successfully")

    async def stop(self):
        """Gracefully shut down all connections."""
        logger.info("Shutting down data infrastructure layer...")

        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        if self.redis_cache:
            await self.redis_cache.close()

        logger.info("Data infrastructure layer stopped")


async def main():
    """Run the service."""
    service = DataInfraService()
    await service.start()

    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(60)
            logger.info("Service alive — %d messages produced, %d consumed",
                       service.producer.message_count,
                       service.consumer.message_count)
    except asyncio.CancelledError:
        logger.info("Service interrupted, shutting down...")
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
