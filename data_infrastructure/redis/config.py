"""Redis connection configuration for trading data service."""

from pydantic_settings import BaseSettings
from typing import Optional


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    redis_host: str = "trading-redis.customer1.svc.cluster.local"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_socket_timeout: float = 5.0
    redis_socket_connect_timeout: float = 5.0
    redis_retry_on_timeout: bool = True
    redis_health_check_interval: int = 10  # seconds
    redis_max_connections: int = 50

    # Key prefixes for namespacing
    key_prefix: str = "trading"

    # TTL defaults (seconds)
    tick_ttl: int = 60
    orderbook_ttl: int = 30
    bbo_ttl: int = 30

    model_config = {"env_prefix": "DATA_SERVICE_"}


def get_redis_settings() -> RedisSettings:
    """Get Redis settings singleton."""
    return RedisSettings()
