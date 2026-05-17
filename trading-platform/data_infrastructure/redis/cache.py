"""Redis layer for real-time market data caching.

Patterns implemented:
- HOT cache: Sorted sets (orderbooks), latest prices in hashes
- WARM cache: Redis Streams for tick replay
- COLD cache: PostgreSQL (via data-infrastructure models)

Hot data lives in Redis with short TTLs. When a cache miss occurs,
data is loaded from Kafka replay or DB, then cached with TTL.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from data_infrastructure.redis.config import redis_settings

logger = logging.getLogger(__name__)


class MarketDataCache:
    """Redis-backed cache for market data with hot/cold patterns.

    All keys use hash tags {symbol} to ensure co-location in Redis Cluster.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or redis_settings.redis_url
        self._pool: Optional[aioredis.Redis] = None

    async def connect(self):
        self._pool = aioredis.from_url(
            self.redis_url,
            decode_responses=True,
            encoding="utf-8",
        )

    async def close(self):
        if self._pool:
            await self._pool.close()

    @property
    def redis(self) -> aioredis.Redis:
        if self._pool is None:
            raise RuntimeError("Call connect() first")
        return self._pool

    # ---- HOT CACHE: Latest price (hash) ----

    async def set_latest_price(
        self, symbol: str, price: float, timestamp: Optional[datetime] = None,
        source: str = "aggregated",
    ):
        """Cache latest price for a symbol. Key: {symbol}:price:latest"""
        key = f"{{{symbol}}}:price:latest"
        ts = timestamp or datetime.now(timezone.utc)
        data = {
            "price": str(price),
            "timestamp": ts.isoformat(),
            "source": source,
        }
        await self.redis.hset(key, mapping=data)
        await self.redis.expire(key, redis_settings.hot_price_ttl)

    async def get_latest_price(self, symbol: str) -> Optional[dict]:
        """Get latest cached price. Returns None on cache miss."""
        key = f"{{{symbol}}}:price:latest"
        data = await self.redis.hgetall(key)
        if not data:
            return None
        return {
            "price": float(data["price"]),
            "timestamp": data["timestamp"],
            "source": data["source"],
        }

    # ---- HOT CACHE: Best bid/offer (hash) ----

    async def set_bbo(self, symbol: str, bid: float, ask: float, bid_size: float, ask_size: float):
        """Cache best bid and offer. Key: {symbol}:bbo"""
        key = f"{{{symbol}}}:bbo"
        data = {
            "bid": str(bid), "ask": str(ask),
            "bid_size": str(bid_size), "ask_size": str(ask_size),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis.hset(key, mapping=data)
        await self.redis.expire(key, redis_settings.hot_bbo_ttl)

    async def get_bbo(self, symbol: str) -> Optional[dict]:
        key = f"{{{symbol}}}:bbo"
        data = await self.redis.hgetall(key)
        if not data:
            return None
        return {
            "bid": float(data["bid"]), "ask": float(data["ask"]),
            "bid_size": float(data["bid_size"]), "ask_size": float(data["ask_size"]),
            "ts": data["ts"],
        }

    # ---- HOT CACHE: Orderbook (sorted set with hash tag) ----

    async def set_orderbook(self, symbol: str, bids: list[tuple[float, float]], asks: list[tuple[float, float]]):
        """Store full orderbook in sorted set.
        Key: {symbol}:ob:bids / {symbol}:ob:asks
        Score = price, payload = qty as member.
        """
        bid_key = f"{{{symbol}}}:ob:bids"
        ask_key = f"{{{symbol}}}:ob:asks"

        pipe = self.redis.pipeline()
        pipe.delete(bid_key, ask_key)

        # Negative scores for bids so highest bid is at top
        for price, qty in bids:
            pipe.zadd(bid_key, {str(qty): -price})
        for price, qty in asks:
            pipe.zadd(ask_key, {str(qty): price})

        await pipe.execute()
        await self.redis.expire(bid_key, redis_settings.hot_orderbook_ttl)
        await self.redis.expire(ask_key, redis_settings.hot_orderbook_ttl)

    async def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[dict]:
        """Retrieve orderbook at given depth."""
        bid_key = f"{{{symbol}}}:ob:bids"
        ask_key = f"{{{symbol}}}:ob:asks"

        pipe = self.redis.pipeline()
        pipe.zrange(bid_key, 0, depth - 1, desc=True)  # top bids
        pipe.zrange(ask_key, 0, depth - 1, desc=False)  # lowest asks
        results = await pipe.execute()

        if not results[0] and not results[1]:
            return None

        return {
            "bids": results[0],
            "asks": results[1],
        }

    # ---- WARM CACHE: Tick stream (Redis Streams) ----

    async def add_tick(self, symbol: str, tick: dict) -> str:
        """Push a tick to Redis Stream. Key: {symbol}:ticks"""
        key = f"{{{symbol}}}:ticks"
        stream_data = {
            f"{k}": str(v) for k, v in tick.items()
        }
        entry_id = await self.redis.xadd(
            key, stream_data, maxlen=redis_settings.max_stream_length,
            approximate=True,
        )
        return entry_id if entry_id else ""

    async def get_ticks_recent(
        self, symbol: str, count: int = 100,
    ) -> list[dict]:
        """Get recent ticks from stream (tail behavior)."""
        key = f"{{{symbol}}}:ticks"
        entries = await self.redis.xrevrange(key, count=count)
        return [{"id": eid.decode() if isinstance(eid, bytes) else eid, **{
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }} for eid, data in entries]

    async def create_consumer_group(self, symbol: str) -> Optional[str]:
        """Create consumer group for tick replay."""
        key = f"{{{symbol}}}:ticks"
        group_name = redis_settings.consumer_group_name
        try:
            await self.redis.xgroup_create(key, group_name, id="0", mkstream=True)
            return group_name
        except aioredis.ResponseError:
            # Group already exists
            return group_name

    async def read_stream(
        self, symbol: str, consumer_name: str,
        batch_size: int = 50, block_ms: int = 5000,
    ) -> list[tuple[str, dict]]:
        """Read from consumer group. Returns [(entry_id, data), ...]."""
        key = f"{{{symbol}}}:ticks"
        group_name = redis_settings.consumer_group_name

        response = await self.redis.xreadgroup(
            group_name, consumer_name, {key: ">"},
            count=batch_size, block=block_ms,
        )
        if not response:
            return []

        results = []
        for _, entries in response:
            for entry_id, data in entries.items():
                results.append((entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id), {
                    k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                    for k, v in data.items()
                }))
        return results

    # ---- HOT CACHE: Rate limiter (sliding window) ----

    async def check_rate_limit(self, client_id: str, action: str = "default") -> bool:
        """Sliding window rate limiter using sorted sets.
        Returns True if allowed, False if rate limited.
        Key: rate:{client_id}:{action}
        """
        key = f"rate:{client_id}:{action}"
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - redis_settings.rate_limit_ttl

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {f"{now}:{client_id}": now})
        pipe.zcard(key)
        pipe.expire(key, redis_settings.rate_ttl + 10)

        _, _, count, _ = await pipe.execute()

        if count > redis_settings.rate_limit_max_requests:
            return False
        return True

    # ---- PIPELINE / BATCH OPERATIONS ----

    async def batch_set_latest_prices(
        self, prices: dict[str, dict],
    ):
        """Batch-set latest prices for many symbols via pipeline.

        Args:
            prices: {symbol: {"price": float, "timestamp": datetime, "source": str}}
        """
        pipe = self.redis.pipeline()
        for symbol, data in prices.items():
            key = f"{{{symbol}}}:price:latest"
            price_data = {
                "price": str(data["price"]),
                "timestamp": (
                    data["timestamp"].isoformat()
                    if isinstance(data.get("timestamp"), datetime)
                    else str(data.get("timestamp", ""))
                ),
                "source": data.get("source", "aggregated"),
            }
            pipe.hset(key, mapping=price_data)
            pipe.expire(key, redis_settings.hot_price_ttl)
        await pipe.execute()

    async def batch_set_bbo(
        self, bbos: dict[str, dict],
    ):
        """Batch-set BBOs for many symbols.

        Args:
            bbos: {symbol: {"bid": float, "ask": float, "bid_size": float, "ask_size": float}}
        """
        pipe = self.redis.pipeline()
        for symbol, data in bbos.items():
            key = f"{{{symbol}}}:bbo"
            bbo_data = {
                "bid": str(data["bid"]),
                "ask": str(data["ask"]),
                "bid_size": str(data["bid_size"]),
                "ask_size": str(data["ask_size"]),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            pipe.hset(key, mapping=bbo_data)
            pipe.expire(key, redis_settings.hot_bbo_ttl)
        await pipe.execute()

    async def batch_add_ticks(
        self, symbol: str, ticks: list[dict],
    ) -> list[str]:
        """Batch-add ticks to a Redis Stream using a single pipeline.

        Returns list of entry IDs.
        """
        if not ticks:
            return []

        pipe = self.redis.pipeline()
        key = f"{{{symbol}}}:ticks"
        for tick in ticks:
            stream_data = {str(k): str(v) for k, v in tick.items()}
            pipe.xadd(key, stream_data, maxlen=redis_settings.max_stream_length, approximate=True)
        results = await pipe.execute()
        return [r if r else "" for r in results]

    async def invalidate_symbol(self, symbol: str):
        """Delete all cached data for a symbol."""
        pipe = self.redis.pipeline()
        for suffix in [
            ":price:latest", ":bbo", ":ob:bids", ":ob:asks", ":ticks",
        ]:
            pipe.delete(f"{{{symbol}}}{suffix}")
        await pipe.execute()

    async def pipeline_health(self) -> dict:
        """Check Redis health and basic metrics."""
        info = await self.redis.info("memory")
        client = await self.redis.info("clients")
        return {
            "connected": True,
            "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            "connected_clients": client.get("connected_clients", 0),
        }
