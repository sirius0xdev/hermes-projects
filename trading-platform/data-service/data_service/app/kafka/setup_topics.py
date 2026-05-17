"""Kafka topic administration utility."""
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
        bootstrap_servers: str = "kafka.customer1.svc.cluster.local:9092",
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
        logger.info("TopicAdmin connected to %s", self.bootstrap_servers)

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
        """Create a single topic with optional configuration."""
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
            logger.info("Created topic: %s (partitions=%d, replication=%d)",
                        topic, partitions, replication_factor)
            return True
        except TopicAlreadyExistsError:
            logger.info("Topic already exists: %s", topic)
            return False

    def create_all_topics(self) -> dict[str, bool]:
        """Create all trading platform topics from the configuration."""
        results = {}
        for topic_name, config in TOPIC_CONFIG.items():
            created = self.create_topic(
                topic=topic_name,
                partitions=config["partitions"],
                replication_factor=config["replication_factor"],
                topic_config=config.get("config", {}),
            )
            results[topic_name] = created
        logger.info("Topic setup complete: %d topics", len(results))
        return results
