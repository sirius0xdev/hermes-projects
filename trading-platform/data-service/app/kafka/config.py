from __future__ import annotations
from data_service.app.kafka.topics import KafkaTopics

TOPIC_CONFIG = {
    KafkaTopics.MARKET_PRICES: {
        "partitions": 6,
        "replication_factor": 1,
        "config": {
            "retention.ms": "86400000",
            "cleanup.policy": "delete",
            "compression.type": "lz4",
            "segment.ms": "3600000",
        }
    },
    KafkaTopics.MARKET_ORDERBOOK: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "3600000",
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        },
    },
    KafkaTopics.MARKET_TRADES: {
        "partitions": 6,
        "replication_factor": 1,
        "config": {
            "retention.ms": "604800000",
            "cleanup.policy": "delete",
            "compression.type": "zstd",
        },
    },
    KafkaTopics.NEWS_FEED: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "2592000000",
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        }
    },
    KafkaTopics.NEWS_ANALYSIS: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "2592000000",
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        },
    },
    KafkaTopics.TRADING_SIGNALS: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "86400000",
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        },
    },
    # Solana blockchain topics
    KafkaTopics.SOLANA_TOKEN_DATA: {
        "partitions": 6,
        "replication_factor": 1,
        "config": {
            "retention.ms": "2592000000",
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        },
    },
    KafkaTopics.SOLANA_POOL_DATA: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "2592000000",
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        },
    },
    KafkaTopics.SOLANA_BLOCK: {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "86400000",
            "cleanup.policy": "delete",
            "compression.type": "lz4",
        },
    },
}

def get_topic_config(topic: str) -> dict:
    return TOPIC_CONFIG.get(topic, {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "retention.ms": "86400000",
            "cleanup.policy": "delete",
        }
    })
