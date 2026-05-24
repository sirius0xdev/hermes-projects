"""Redis configuration for market data caching."""
from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    # Connection
    redis_url: str = "redis://redis-master:6379/0"

    # Hot cache TTLs (seconds)
    hot_orderbook_ttl: int = 60        # Order book snapshot validity
    hot_price_ttl: int = 30            # Latest price validity
    hot_bbo_ttl: int = 5               # Best bid/offer TTL

    # Stream settings
    max_stream_length: int = 100_000   # Max entries per Redis stream
    consumer_group_name: str = "market-data-workers"

    # Rate limiter settings
    rate_limit_ttl: int = 1            # Per-second sliding window
    rate_limit_max_requests: int = 100  # Max requests per window

    model_config = {"env_prefix": "REDIS_", "env_file": ".env", "extra": "ignore"}


redis_settings = RedisSettings()
