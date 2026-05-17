"""Redis cache layer for real-time market data.

Provides async Redis caching for:
- Hot data: current prices, order book snapshots (TTL 5s)
- Warm data: recent candles/OHLC (TTL 5m)
- Cache keys by symbol+exchange with automatic invalidation
"""
from data_service.app.cache.client import RedisClient, get_redis_client
from data_service.app.cache.service import CacheService

__all__ = ["RedisClient", "get_redis_client", "CacheService"]
