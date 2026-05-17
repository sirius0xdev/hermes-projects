"""Tests for the Redis cache layer (T5b).

Uses pytest-asyncio and fakeredis's async support so tests run
without a real Redis server.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import pytest
from fakeredis import FakeAsyncRedis, FakeServer

from data_service.app.cache.client import (
    TTL_HOT,
    TTL_WARM,
    _price_key,
    _orderbook_key,
    _candle_key,
    _meta_key,
)
from data_service.app.cache.service import CacheService, _serialize, _deserialize


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def server():
    return FakeServer()


@pytest.fixture
def fake_redis(server: FakeServer) -> FakeAsyncRedis:
    """Provide an isolated fake Redis per test."""
    return FakeAsyncRedis(server=server)


@pytest.fixture
def cache(fake_redis: FakeAsyncRedis) -> CacheService:
    return CacheService(fake_redis)


# ── Serialization ───────────────────────────────────────────────────


def test_serialize_deserialize_roundtrip():
    obj = {
        "price": Decimal("42.50"),
        "ts": datetime(2026, 1, 1, 0, 0, 0),
        "flag": True,
    }
    encoded = _serialize(obj)
    decoded = _deserialize(encoded)
    assert decoded["price"] == "42.50"
    assert decoded["ts"] == "2026-01-01T00:00:00"
    assert decoded["flag"] is True


def test_deserialize_none():
    assert _deserialize(None) is None


# ── Key builders ────────────────────────────────────────────────────


def test_price_key():
    assert _price_key("binance", "BTC/USDT") == "price:binance:BTC/USDT"


def test_orderbook_key():
    assert _orderbook_key("binance", "BTC/USDT", 20) == "ob:binance:BTC/USDT:20"


def test_candle_key():
    assert _candle_key("binance", "BTC/USDT", "1h") == "candle:binance:BTC/USDT:1h"


def test_meta_key():
    assert _meta_key("binance", "BTC/USDT") == "meta:binance:BTC/USDT"


# ── Price tier (HOT, TTL 5s) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_set_and_get_price(cache: CacheService):
    await cache.set_price("binance", "SOL/USDT", bid="100.00", ask="100.01", last="100.005")
    result = await cache.get_price("binance", "SOL/USDT")
    assert result is not None
    assert result["exchange"] == "binance"
    assert result["symbol"] == "SOL/USDT"
    assert result["bid"] == "100.00"
    assert result["ask"] == "100.01"
    assert result["last"] == "100.005"
    assert "ts" in result


@pytest.mark.asyncio
async def test_get_price_miss(cache: CacheService):
    assert await cache.get_price("binance", "NONEXIST") is None


@pytest.mark.asyncio
async def test_delete_price(cache: CacheService):
    await cache.set_price("binance", "BTC/USDT", last="50000")
    await cache.delete_price("binance", "BTC/USDT")
    assert await cache.get_price("binance", "BTC/USDT") is None


@pytest.mark.asyncio
async def test_set_price_batch(cache: CacheService):
    updates = [
        {"exchange": "binance", "symbol": "BTC/USDT", "last": "50000"},
        {"exchange": "binance", "symbol": "ETH/USDT", "last": "3000"},
        {"exchange": "hyperliquid", "symbol": "SOL-USD", "last": "100"},
    ]
    await cache.set_price_batch(updates)
    btc = await cache.get_price("binance", "BTC/USDT")
    eth = await cache.get_price("binance", "ETH/USDT")
    sol = await cache.get_price("hyperliquid", "SOL-USD")
    assert btc["last"] == "50000"
    assert eth["last"] == "3000"
    assert sol["last"] == "100"


@pytest.mark.asyncio
async def test_price_ttl_is_hot(server: FakeServer, fake_redis: FakeAsyncRedis, cache: CacheService):
    """Verify prices are written with HOT TTL (5s)."""
    await cache.set_price("binance", "BTC/USDT", last="50000")
    ttl = await fake_redis.ttl(_price_key("binance", "BTC/USDT"))
    assert 0 < ttl <= TTL_HOT


# ── Order book tier (HOT, TTL 5s) ──────────────────────────────────


@pytest.mark.asyncio
async def test_set_and_get_orderbook(cache: CacheService):
    bids = [("100.00", "10.5"), ("99.99", "5.0")]
    asks = [("100.01", "8.0"), ("100.02", "12.0")]
    await cache.set_orderbook("binance", "BTC/USDT", bids, asks, depth=2)
    result = await cache.get_orderbook("binance", "BTC/USDT", depth=2)
    assert result is not None
    assert result["exchange"] == "binance"
    assert len(result["bids"]) == 2
    assert len(result["asks"]) == 2
    assert result["bids"][0] == ["100.00", "10.5"]


@pytest.mark.asyncio
async def test_orderbook_depth_truncation(cache: CacheService):
    bids = [(f"{i}.00", "1.0") for i in range(50)]
    asks = [(f"{i}.01", "1.0") for i in range(50)]
    await cache.set_orderbook("binance", "BTC/USDT", bids, asks, depth=20)
    result = await cache.get_orderbook("binance", "BTC/USDT", depth=20)
    assert len(result["bids"]) == 20
    assert len(result["asks"]) == 20


@pytest.mark.asyncio
async def test_get_orderbook_miss(cache: CacheService):
    assert await cache.get_orderbook("binance", "FAKE") is None


@pytest.mark.asyncio
async def test_delete_orderbook(cache: CacheService):
    await cache.set_orderbook("binance", "BTC/USDT", [("1", "1")], [("2", "1")])
    await cache.delete_orderbook("binance", "BTC/USDT")
    assert await cache.get_orderbook("binance", "BTC/USDT") is None


@pytest.mark.asyncio
async def test_orderbook_ttl_is_hot(server: FakeServer, fake_redis: FakeAsyncRedis, cache: CacheService):
    await cache.set_orderbook("binance", "BTC/USDT", [("1", "1")], [("2", "1")])
    ttl = await fake_redis.ttl(_orderbook_key("binance", "BTC/USDT"))
    assert 0 < ttl <= TTL_HOT


# ── Candles tier (WARM, TTL 5m) ────────────────────────────────────


@pytest.mark.asyncio
async def test_set_and_get_candles(cache: CacheService):
    candles = [
        {"time": "2026-01-01T00:00:00", "open": "100", "high": "110", "low": "90", "close": "105", "volume": "50"},
        {"time": "2026-01-01T01:00:00", "open": "105", "high": "120", "low": "100", "close": "115", "volume": "70"},
    ]
    await cache.set_candles("binance", "BTC/USDT", "1h", candles)
    result = await cache.get_candles("binance", "BTC/USDT", "1h")
    assert result is not None
    assert len(result) == 2
    assert result[0]["close"] == "105"


@pytest.mark.asyncio
async def test_get_candles_miss(cache: CacheService):
    assert await cache.get_candles("binance", "FAKE", "1m") is None


@pytest.mark.asyncio
async def test_delete_candles(cache: CacheService):
    await cache.set_candles("binance", "BTC/USDT", "1h", [{"time": "t", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}])
    await cache.delete_candles("binance", "BTC/USDT", "1h")
    assert await cache.get_candles("binance", "BTC/USDT", "1h") is None


@pytest.mark.asyncio
async def test_delete_symbol_candles_all_intervals(cache: CacheService):
    await cache.set_candles("binance", "BTC/USDT", "1m", [{"time": "t", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}])
    await cache.set_candles("binance", "BTC/USDT", "1h", [{"time": "t", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}])
    await cache.set_candles("binance", "BTC/USDT", "1d", [{"time": "t", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}])
    await cache.delete_symbol_candles("binance", "BTC/USDT")
    assert await cache.get_candles("binance", "BTC/USDT", "1m") is None
    assert await cache.get_candles("binance", "BTC/USDT", "1h") is None
    assert await cache.get_candles("binance", "BTC/USDT", "1d") is None


@pytest.mark.asyncio
async def test_candle_ttl_is_warm(fake_redis: FakeAsyncRedis, cache: CacheService):
    await cache.set_candles("binance", "BTC/USDT", "1h", [{"time": "t", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}])
    ttl = await fake_redis.ttl(_candle_key("binance", "BTC/USDT", "1h"))
    assert 0 < ttl <= TTL_WARM


# ── Meta tier ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_and_get_meta(cache: CacheService):
    await cache.set_meta("binance", "BTC/USDT", {"base_asset": "BTC", "quote_asset": "USDT", "tick_size": "0.01"})
    result = await cache.get_meta("binance", "BTC/USDT")
    assert result is not None
    assert result["base_asset"] == "BTC"


@pytest.mark.asyncio
async def test_get_meta_miss(cache: CacheService):
    assert await cache.get_meta("binance", "FAKE") is None


# ── Cache invalidation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_on_update(cache: CacheService):
    # Populate all tiers
    await cache.set_price("binance", "BTC/USDT", last="50000")
    await cache.set_orderbook("binance", "BTC/USDT", [("1", "1")], [("2", "1")])
    await cache.set_candles("binance", "BTC/USDT", "1h", [{"time": "t", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}])

    await cache.invalidate_on_update("binance", "BTC/USDT")

    assert await cache.get_price("binance", "BTC/USDT") is None
    assert await cache.get_orderbook("binance", "BTC/USDT") is None
    assert await cache.get_candles("binance", "BTC/USDT", "1h") is None


@pytest.mark.asyncio
async def test_invalidate_selective(cache: CacheService):
    await cache.set_price("binance", "BTC/USDT", last="50000")
    await cache.set_candles("binance", "BTC/USDT", "1h", [{"time": "t", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}])

    # Only invalidate price, leave candles
    await cache.invalidate_on_update("binance", "BTC/USDT", price=True, candles=False)

    assert await cache.get_price("binance", "BTC/USDT") is None
    assert await cache.get_candles("binance", "BTC/USDT", "1h") is not None


@pytest.mark.asyncio
async def test_flush_exchange(cache: CacheService):
    # Set data for two exchanges
    await cache.set_price("binance", "BTC/USDT", last="50000")
    await cache.set_price("hyperliquid", "BTC-USD", last="49990")
    await cache.set_candles("binance", "BTC/USDT", "1h", [{"time": "t", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}])

    deleted = await cache.flush_exchange("binance")
    assert deleted >= 2

    # Binance data gone
    assert await cache.get_price("binance", "BTC/USDT") is None
    assert await cache.get_candles("binance", "BTC/USDT", "1h") is None

    # Hyperliquid data preserved
    hl = await cache.get_price("hyperliquid", "BTC-USD")
    assert hl is not None
    assert hl["last"] == "49990"


# ── Cache stats ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_empty(cache: CacheService):
    stats = await cache.stats()
    assert stats["total"] == 0


@pytest.mark.asyncio
async def test_stats_with_data(cache: CacheService):
    await cache.set_price("binance", "A/B", last="1")
    await cache.set_price("binance", "C/D", last="2")
    await cache.set_orderbook("binance", "A/B", [("1", "1")], [("2", "1")])

    stats = await cache.stats()
    assert stats["hot_prices"] >= 2
    assert stats["hot_orderbooks"] >= 1
    assert stats["warm_candles"] == 0
    assert stats["total"] >= 3


# ── Cross-exchange isolation ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_exchange_isolation(cache: CacheService):
    """Keys should not collide across exchanges."""
    await cache.set_price("binance", "BTC/USDT", last="50000")
    await cache.set_price("hyperliquid", "BTC-USD", last="49900")

    binance_price = await cache.get_price("binance", "BTC/USDT")
    hyper_price = await cache.get_price("hyperliquid", "BTC-USD")

    assert binance_price["last"] == "50000"
    assert hyper_price["last"] == "49900"
