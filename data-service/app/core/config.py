"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "data-service"
    debug: bool = False

    # Kafka
    kafka_bootstrap_servers: str = "trading-kafka.customer1.svc.cluster.local:9092"
    kafka_group_id: str = "data-cache-consumer"
    kafka_topic_prices: str = "market.prices"
    kafka_topic_orderbook: str = "market.orderbook"
    kafka_topic_trades: str = "market.trades"
    kafka_auto_offset_reset: str = "latest"

    # Redis
    redis_host: str = "trading-redis.customer1.svc.cluster.local"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # API
    port: int = 8004
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    model_config = {"env_prefix": "DATA_SERVICE_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
