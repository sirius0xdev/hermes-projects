"""Kafka event streaming for market data.

Provides:
- Producer: async market data ingestion (yfinance, exchange APIs)
- Consumer: downstream consumption for trading engine, dashboard
- Topic management: create and configure trading platform topics
- Schema registry: Pydantic-based serialization with versioned events
- Consumer service: FastAPI-backed consumer with health checks
"""
from data_service.app.kafka.config import get_topic_config
from data_service.app.kafka.producer import DataProducer
from data_service.app.kafka.consumer import DataConsumer
from data_service.app.kafka.topics import KafkaTopics
from data_service.app.kafka.consumer_service import app as consumer_app

__all__ = [
    "get_topic_config",
    "DataProducer",
    "DataConsumer",
    "KafkaTopics",
    "consumer_app",
]
