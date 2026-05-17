"""Cache service implementing market data caching patterns.

Three-tier caching:
- Hot: current prices, order book snapshots (TTL 5s)
- Warm: recent candles/OHLC (TTL 5m)
- Cool: static configs (TTL 1h, not implemented here but supported)

All keys are namespaced by exchange + symbol to avoid collisions
across venues (e.g. Binance BTC/USDT vs Hyperliquid BTC-USD).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Optional

from redis.asyncio import Redis

from data_service.app.cache.client import (
    PREFIX_CANDLE,
    PREFIX_META,
    PREFIX_ORDERBOOK,
    PREFIX_PRICE,
    TTL_COOL,
    TTL_HOT,
    TTL_WARM,
    _candle_key,
    _meta_key,
    _orderbook_key,
    _price_key,
)

logger = logging.getLogger(__name__)

# ── Serialization helpers ──────────────────────────────────────────


def _serialize(obj: Any) -> str:
    """Serialize Python objects to JSON string for Redis.

    Handles Decimal and datetime objects that json.dumps
    can't serialize natively.
    """
    return json.dumps(obj, default=_json_serializer)


def _json_serializer(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _deserialize(text: str | None) -> Any | None:
    """Deserialize JSON string from Redis back to Python objects."""
    if text is None:
        return None
    return json.loads(text)


# ── Cache Service ───────────────────────────────────────────────────


class CacheService:
    """High-level cache operations for market data.

    All methods are non-blocking (async) and use JSON serialization.
    Each method maps to a specific cache tier (hot/warm/cool).

    The service does NOT manage the Redis connection lifecycle;
    pass an already-connected Redis/RedisClient instance.
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    # ── HOT tier: prices (TTL 5s) ──────────────────────────────────

    async def set_price(
        self,
        exchange: str,
        symbol: str,
        bid: str | Decimal | None = None,
        ask: str | Decimal | None = None,
        last: str | Decimal | None = None,
        volume_24h: str | Decimal | None = None,
    ) -> None:
        """Cache the latest price ticker for a symbol."""
        key = _price_key(exchange, symbol)
        data = {
            "exchange": exchange,
            "symbol": symbol,
            "bid": str(bid) if bid is not None else None,
            "ask": str(ask) if ask is not None else None,
            "last": str(last) if last is not None else None,
            "volume_24h": str(volume_24h) if volume_24h is not None else None,
            "ts": datetime.now(UTC).isoformat(),
        }
        await self.redis.setex(key, TTL_HOT, _serialize(data))

    async def get_price(
        self, exchange: str, symbol: str
    ) -> dict[str, Any] | None:
        """Get cached price. Returns None on cache miss."""
        key = _price_key(exchange, symbol)
        return _deserialize(await self.redis.get(key))

    async def delete_price(self, exchange: str, symbol: str) -> None:
        """Invalidate cached price."""
        key = _price_key(exchange, symbol)
        await self.redis.delete(key)

    async def set_price_batch(
        self, updates: list[dict[str, Any]]
    ) -> None:
        """Set multiple prices in a pipeline for lower latency.

        Each dict must have: exchange, symbol, and optionally
        bid, ask, last, volume_24h.
        """
        pipe = self.redis.pipeline()
        now = datetime.now(UTC).isoformat()
        for item in updates:
            exchange = item["exchange"]
            symbol = item["symbol"]
            key = _price_key(exchange, symbol)
            data = {
                "exchange": exchange,
                "symbol": symbol,
                "bid": str(item.get("bid")) if item.get("bid") else None,
                "ask": str(item.get("ask")) if item.get("ask") else None,
                "last": str(item.get("last")) if item.get("last") else None,
                "volume_24h": str(item.get("volume_24h"))
                if item.get("volume_24h")
                else None,
                "ts": now,
            }
            pipe.setex(key, TTL_HOT, _serialize(data))
        await pipe.execute()

    # ── HOT tier: order book snapshots (TTL 5s) ────────────────────

    async def set_orderbook(
        self,
        exchange: str,
        symbol: str,
        bids: list[tuple[str | Decimal, str | Decimal]],
        asks: list[tuple[str | Decimal, str | Decimal]],
        depth: int = 20,
    ) -> None:
        """Cache order book snapshot."""
        key = _orderbook_key(exchange, symbol, depth)
        data = {
            "exchange": exchange,
            "symbol": symbol,
            "depth": depth,
            "bids": [[str(price), str(qty)] for price, qty in bids[:depth]],
            "asks": [[str(price), str(qty)] for price, qty in asks[:depth]],
            "ts": datetime.now(UTC).isoformat(),
        }
        await self.redis.setex(key, TTL_HOT, _serialize(data))

    async def get_orderbook(
        self, exchange: str, symbol: str, depth: int = 20
    ) -> dict[str, Any] | None:
        """Get cached order book. Returns None on cache miss."""
        key = _orderbook_key(exchange, symbol, depth)
        return _deserialize(await self.redis.get(key))

    async def delete_orderbook(
        self, exchange: str, symbol: str, depth: int = 20
    ) -> None:
        """Invalidate cached order book."""
        key = _orderbook_key(exchange, symbol, depth)
        await self.redis.delete(key)

    # ── WARM tier: candles / OHLC (TTL 5m) ─────────────────────────

    async def set_candles(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        candles: list[dict[str, Any]],
    ) -> None:
        """Cache OHLC candles for a symbol+interval.

        Each candle dict should contain:
        time (ISO string), open, high, low, close, volume.
        """
        key = _candle_key(exchange, symbol, interval)
        data = {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "count": len(candles),
            "candles": candles,
            "ts": datetime.now(UTC).isoformat(),
        }
        await self.redis.setex(key, TTL_WARM, _serialize(data))

    async def get_candles(
        self, exchange: str, symbol: str, interval: str
    ) -> list[dict[str, Any]] | None:
        """Get cached candles. Returns None on cache miss."""
        key = _candle_key(exchange, symbol, interval)
        result = _deserialize(await self.redis.get(key))
        if result is None:
            return None
        return result.get("candles")

    async def delete_candles(
        self, exchange: str, symbol: str, interval: str
    ) -> None:
        """Invalidate cached candles."""
        key = _candle_key(exchange, symbol, interval)
        await self.redis.delete(key)

    async def delete_symbol_candles(
        self, exchange: str, symbol: str
    ) -> None:
        """Delete all candle intervals for a symbol (use SCAN, not KEYS)."""
        pattern = _candle_key(exchange, symbol, "*")
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match=pattern, count=100
            )
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break

    # ── WARM tier: exchange/metadata ───────────────────────────────

    async def set_meta(
        self, exchange: str, symbol: str, data: dict[str, Any]
    ) -> None:
        """Cache exchange/metadata for a symbol (1h TTL)."""
        from data_service.app.cache.client import TTL_COOL

        key = _meta_key(exchange, symbol)
        payload = {"exchange": exchange, "symbol": symbol, **data}
        await self.redis.setex(key, TTL_COOL, _serialize(payload))

    async def get_meta(
        self, exchange: str, symbol: str
    ) -> dict[str, Any] | None:
        """Get cached metadata."""
        key = _meta_key(exchange, symbol)
        return _deserialize(await self.redis.get(key))

    # ── Cache invalidation patterns ────────────────────────────────

    async def invalidate_on_update(
        self,
        exchange: str,
        symbol: str,
        price: bool = True,
        orderbook: bool = True,
        candles: bool = True,
    ) -> None:
        """Broad invalidation for a symbol after a significant update.

        For example, after a large price swing or exchange maintenance,
        callers may want to flush all cached data for a symbol.
        """
        tasks = []
        if price:
            tasks.append(self.delete_price(exchange, symbol))
        if orderbook:
            tasks.append(self.delete_orderbook(exchange, symbol))
        if candles:
            tasks.append(self.delete_symbol_candles(exchange, symbol))
        await asyncio.gather(*tasks)

    async def flush_exchange(self, exchange: str) -> int:
        """Flush ALL cached data for an exchange. Use with caution.

        Returns the total number of keys deleted.
        """
        pattern = f"*:{exchange}:*"
        # Build a union of patterns for all key types
        patterns = [
            f"{PREFIX_PRICE}{exchange}:*",
            f"{PREFIX_ORDERBOOK}{exchange}:*",
            f"{PREFIX_CANDLE}{exchange}:*",
            f"{PREFIX_META}{exchange}:*",
        ]
        deleted = 0
        for pat in patterns:
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(
                    cursor, match=pat, count=500
                )
                if keys:
                    deleted += await self.redis.delete(*keys)
                if cursor == 0:
                    break
        logger.info(f"Flushed {deleted} keys for exchange {exchange}")
        return deleted

    # ── Bulk cache stats ───────────────────────────────────────────

    async def stats(self) -> dict[str, int]:
        """Return cache statistics: estimated key counts per tier."""
        hot_prices = await self._count_keys(f"{PREFIX_PRICE}*")
        hot_orderbooks = await self._count_keys(f"{PREFIX_ORDERBOOK}*")
        warm_candles = await self._count_keys(f"{PREFIX_CANDLE}*")
        warm_meta = await self._count_keys(f"{PREFIX_META}*")
        return {
            "hot_prices": hot_prices,
            "hot_orderbooks": hot_orderbooks,
            "warm_candles": warm_candles,
            "warm_meta": warm_meta,
            "total": hot_prices + hot_orderbooks + warm_candles + warm_meta,
        }

    async def _count_keys(self, pattern: str) -> int:
        """Count keys matching pattern using SCAN (safe for production)."""
        count = 0
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=500)
            count += len(keys)
            if cursor == 0:
                break
        return count
