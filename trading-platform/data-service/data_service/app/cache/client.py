"""Async Redis client setup and connection management.

Uses redis-py's async support (redis.asyncio) for non-blocking operations.
Supports connection pooling, health checks, and graceful shutdown.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool, Redis

logger = logging.getLogger(__name__)

# Default TTLs (in seconds)
TTL_HOT = 5       # 5 seconds for prices, order book snapshots
TTL_WARM = 300    # 5 minutes for recent candles/OHLC
TTL_COOL = 3600   # 1 hour for static data (symbol configs, etc.)

# Key prefixes
PREFIX_PRICE = "price:"        # price:{exchange}:{symbol}
PREFIX_ORDERBOOK = "ob:"       # ob:{exchange}:{symbol}
PREFIX_CANDLE = "candle:"      # candle:{exchange}:{symbol}:{interval}
PREFIX_META = "meta:"          # meta:{exchange}:{symbol}


# ── Key builders ───────────────────────────────────────────────────


def _price_key(exchange: str, symbol: str) -> str:
    """Build cache key for current price."""
    return f"{PREFIX_PRICE}{exchange}:{symbol}"


def _orderbook_key(exchange: str, symbol: str, depth: int = 20) -> str:
    """Build cache key for order book snapshot."""
    return f"{PREFIX_ORDERBOOK}{exchange}:{symbol}:{depth}"


def _candle_key(exchange: str, symbol: str, interval: str) -> str:
    """Build cache key for OHLC candles."""
    return f"{PREFIX_CANDLE}{exchange}:{symbol}:{interval}"


def _meta_key(exchange: str, symbol: str) -> str:
    """Build cache key for exchange/metadata info."""
    return f"{PREFIX_META}{exchange}:{symbol}"


class RedisClient:
    """Manages async Redis connection lifecycle.

    Usage:
        client = RedisClient()
        await client.connect()
        # ... use client.redis ...
        await client.disconnect()

    Or as async context manager:
        async with RedisClient() as client:
            await client.set("key", "value")
    """

    def __init__(
        self,
        url: str | None = None,
        max_connections: int = 50,
        decode_responses: bool = True,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30,
    ):
        # Read Redis connection from env vars (populated by ConfigMap).
        # Supports both REDIS_URL and REDIS_HOST/REDIS_PORT patterns.
        redis_url = url or os.getenv("REDIS_URL")
        if not redis_url:
            redis_host = os.getenv("REDIS_HOST", "redis-master")
            redis_port = os.getenv("REDIS_PORT", "6379")
            redis_db = os.getenv("REDIS_DB", "0")
            redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
        self.url = redis_url
        self.max_connections = max_connections
        self.decode_responses = decode_responses
        self.retry_on_timeout = retry_on_timeout
        self.health_check_interval = health_check_interval
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    def _build_pool(self) -> ConnectionPool:
        return ConnectionPool.from_url(
            self.url,
            max_connections=self.max_connections,
            decode_responses=self.decode_responses,
            retry_on_timeout=self.retry_on_timeout,
            health_check_interval=self.health_check_interval,
        )

    async def connect(self) -> None:
        """Establish connection pool and ping Redis to verify connectivity."""
        if self._pool is None:
            self._pool = self._build_pool()
            self._redis = Redis(connection_pool=self._pool)

        try:
            assert self._redis is not None
            await self._redis.ping()
            logger.info(f"Connected to Redis at {self.url}")
        except Exception as e:
            logger.error(f"Redis connection test failed: {e}")
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
        logger.info("Redis connections closed")

    @property
    def redis(self) -> Redis:
        """Return the Redis instance. Raises if not connected."""
        if self._redis is None:
            raise RuntimeError(
                "RedisClient not connected. Call await connect() first "
                "or use 'async with RedisClient() as client:'"
            )
        return self._redis

    async def health_check(self) -> dict:
        """Run a comprehensive Redis health check."""
        r = self.redis
        ping_ok = False
        info = {}
        try:
            ping_ok = await r.ping()
            info_raw = await r.info("server")
            info = {
                "version": info_raw.get("redis_version", "unknown"),
                "mode": info_raw.get("redis_mode", "unknown"),
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

        return {
            "service": "redis",
            "status": "healthy" if ping_ok else "unhealthy",
            **info,
        }

    async def __aenter__(self) -> "RedisClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()


# ── Module-level singleton ─────────────────────────────────────────

_default_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """Return (and lazily initialize) the shared Redis client singleton.

    For FastAPI lifespan / startup hooks, call this once during startup.
    For tests, create RedisClient() instances directly.
    """
    global _default_client
    if _default_client is None:
        _default_client = RedisClient()
        await _default_client.connect()
    return _default_client


async def shutdown_redis() -> None:
    """Shut down the shared Redis client. Call during app shutdown."""
    global _default_client
    if _default_client is not None:
        await _default_client.disconnect()
        _default_client = None
