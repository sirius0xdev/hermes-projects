"""Kafka topic administration utility.

Creates and configures all trading platform topics with the
appropriate partition counts, replication factors, and retention
policies defined in the topic config.

Usage:
    python -m data_service.app.kafka.setup_topics

Or programmatically:
    admin = TopicAdmin("kafka:9092")
    await admin.create_all_topics()
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

from data_service.app.kafka.config import TOPIC_CONFIG
from data_service.app.kafka.topics import KafkaTopics

logger = logging.getLogger(__name__)


class TopicAdmin:
    """Admin client for managing Kafka topics."""

    def __init__(
        self,
        bootstrap_servers: str = "kafka:9092",
        client_id: str = "topic-admin",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self._admin: Optional[KafkaAdminClient] = None

    def connect(self) -> None:
        """Create the Kafka admin client connection."""
        self._admin = KafkaAdminClient(
            bootstrap_servers=self.bootstrap_servers.split(","),
            client_id=self.client_id,
        )
        logger.info(
            "TopicAdmin connected to %s", self.bootstrap_servers
        )

    def close(self) -> None:
        """Close the admin client."""
        if self._admin:
            self._admin.close()
            self._admin = None
            logger.info("TopicAdmin closed")

    def create_topic(
        self,
        topic: str,
        partitions: int = 3,
        replication_factor: int = 1,
        topic_config: Optional[dict[str, str]] = None,
    ) -> bool:
        """Create a single topic with optional configuration.

        Returns True if created, False if already exists.
        """
        if not self._admin:
            raise RuntimeError("Admin not connected. Call connect() first.")

        new_topic = NewTopic(
            name=topic,
            num_partitions=partitions,
            replication_factor=replication_factor,
            topic_configs=topic_config or {},
        )

        try:
            self._admin.create_topics([new_topic], validate_only=False)
            logger.info(
                "Created topic: %s (partitions=%d, replication=%d)",
                topic,
                partitions,
                replication_factor,
            )
            return True
        except TopicAlreadyExistsError:
            logger.info("Topic already exists: %s", topic)
            return False

    def create_all_topics(self) -> dict[str, bool]:
        """Create all trading platform topics from the configuration.

        Returns dict of topic_name -> created (True) or already_exists (False).
        """
        results = {}

        for topic_name, config in TOPIC_CONFIG.items():
            created = self.create_topic(
                topic=topic_name,
                partitions=config["partitions"],
                replication_factor=config["replication_factor"],
                topic_config=config.get("config", {}),
            )
            results[topic_name] = created

        logger.info(
            "Topic setup complete: %d topics", len(results)
        )
        return results

    def delete_topic(self, topic: str) -> bool:
        """Delete a topic. Returns True if deleted."""
        if not self._admin:
            raise RuntimeError("Admin not connected")

        try:
            self._admin.delete_topics([topic])
            logger.info("Deleted topic: %s", topic)
            return True
        except Exception as e:
            logger.error("Failed to delete topic %s: %s", topic, e)
            return False

    def list_topics(self) -> list[str]:
        """List all topics in the cluster."""
        if not self._admin:
            raise RuntimeError("Admin not connected")

        return self._admin.list_topics()

    def describe_topic(self, topic: str) -> Optional[dict[str, Any]]:
        """Describe a topic's configuration.

        Returns topic description dict or None if not found.
        """
        if not self._admin:
            raise RuntimeError("Admin not connected")

        # Use the consumer to get topic info
        from kafka import KafkaConsumer

        consumer = KafkaConsumer(
            bootstrap_servers=self.bootstrap_servers.split(","),
            group_id="temp-admin-describe",
        )

        try:
            partitions = consumer.partitions_for_topic(topic)
            if partitions is None:
                return None

            return {
                "topic": topic,
                "partitions": len(partitions),
                "partition_ids": sorted(partitions),
            }
        finally:
            consumer.close()


def setup_topics(bootstrap_servers: str = "kafka:9092") -> dict[str, bool]:
    """Convenience function to create all topics.

    Usage:
        results = setup_topics("kafka:9092")
        for topic, created in results.items():
            status = "CREATED" if created else "EXISTS"
            print(f"  {topic}: {status}")
    """
    admin = TopicAdmin(bootstrap_servers=bootstrap_servers)
    try:
        admin.connect()
        return admin.create_all_topics()
    finally:
        admin.close()


def main() -> None:
    """CLI entry point for topic setup."""
    import os
    import sys

    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

    print(f"Setting up Kafka topics at {bootstrap}...")
    print()

    results = setup_topics(bootstrap_servers=bootstrap)

    for topic, created in results.items():
        status = "CREATED" if created else "ALREADY EXISTS"
        print(f"  [{status}] {topic}")

    print()
    created_count = sum(1 for v in results.values() if v)
    print(f"Setup complete: {created_count}/{len(results)} topics created")

    sys.exit(0)


if __name__ == "__main__":
    main()
