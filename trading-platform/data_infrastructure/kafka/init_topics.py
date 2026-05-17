"""Kafka topic initialization utility.

Creates all required Kafka topics with the correct partition counts,
retention settings, and replication factors.

Usage:
    python -m data_infrastructure.kafka.init_topics
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

from data_infrastructure.kafka.topics import ALL_TOPICS
from data_infrastructure.kafka.config import kafka_settings

logger = logging.getLogger(__name__)


async def ensure_topics(
    bootstrap_servers: Optional[str] = None,
    topics: list | None = None,
) -> None:
    """Create Kafka topics if they don't exist.

    Args:
        bootstrap_servers: Kafka broker address (uses settings if None).
        topics: List of TopicDef to create (uses ALL_TOPICS if None).
    """
    bs = bootstrap_servers or kafka_settings.bootstrap_servers
    topics = topics or ALL_TOPICS

    admin = KafkaAdminClient(
        bootstrap_servers=bs,
        client_id="topic-init",
    )

    new_topics = []
    for t in topics:
        cfg = t.to_admin_config()
        new_topics.append(
            NewTopic(
                name=t.name,
                num_partitions=cfg["num_partitions"],
                replication_factor=min(
                    cfg["replication_factor"],
                    _get_broker_count(admin),
                ),
                topic_configs=cfg["topic_configs"],
            )
        )

    if not new_topics:
        logger.info("No topics to create")
        return

    try:
        admin.create_topics(new_topics)
        logger.info("Created %d topics: %s", len(new_topics), [t.name for t in new_topics])
    except TopicAlreadyExistsError:
        logger.info("Topics already exist — skipping")
    except Exception as e:
        # Some topics may already exist; check individually
        logger.warning("Bulk creation failed (%s), trying one-by-one", e)
        for nt in new_topics:
            try:
                admin.create_topics([nt])
                logger.info("Created topic: %s", nt.name)
            except TopicAlreadyExistsError:
                pass
            except Exception as inner:
                logger.error(
                    "Failed to create topic %s: %s", nt.name, inner,
                )
    finally:
        admin.close()


def _get_broker_count(admin: KafkaAdminClient) -> int:
    """Get number of brokers in the cluster."""
    try:
        return len(admin.cluster.brokers())
    except Exception:
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(ensure_topics())
