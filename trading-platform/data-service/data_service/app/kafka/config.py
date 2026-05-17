from __future__ import annotations
from data_service.app.kafka.topics import KafkaTopics

# Topic naming convention: trading-platform.<domain>.<data-type>.<version>
TOPIC_CONFIG = {
    KafkaTopics.MARKET_PRICES: {
        "partitions": 6,
        "replication_factor": 1,
        "config": {
            "retention.ms": "86400000",  # 24 hours
            "cleanup.policy": "delete",
            "compression.type": "lz4",
            "segment.ms": "3600000",  # 1 hour segments
        }
    },
    KafkaTopics.MARKET_ORDERBOOK: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "3600000",  # 1 hour (orderbook data expires quickly)
            "cleanup.policy": "delete",
            "compression.type": "lz4",
            "compact": "false",
        }
    },
    KafkaTopics.MARKET_TRADES: {
        "partitions": 6,
        "replication_factor": 1,
        "config": {
            "retention.ms": "604800000",  # 7 days
            "cleanup.policy": "delete",
            "compression.type": "zstd",
            "segment.ms": "3600000",
        }
    },
    KafkaTopics.NEWS_FEED: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "2592000000",  # 30 days
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        }
    },
    KafkaTopics.NEWS_ANALYSIS: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "2592000000",  # 30 days
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        }
    },
    KafkaTopics.TRADING_SIGNALS: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "86400000",  # 24 hours
            "cleanup.policy": "delete",
            "compression.type": "lz4",
            "min.insync.replicas": "1",
        }
    },
}

def get_topic_config(topic: str) -> dict:
    """Get configuration for a specific topic."""
    return TOPIC_CONFIG.get(topic, {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "86400000",
            "cleanup.policy": "delete",
        }
    })
