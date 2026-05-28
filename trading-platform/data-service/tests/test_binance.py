"""Tests for BinancePriceClient — Binance public API fallback + cache seeding.

Uses mocked httpx calls so tests run without a real Binance API connection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis import FakeAsyncRedis, FakeServer

from data_service.app.cache.service import CacheService
from data_service.app.scanners.binance_prices import (
    BinanceCandle,
    BinancePrice,
    BinancePriceClient,
    DEFAULT_PRICES,
    DEFAULT_SYMBOLS,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def server():
    return FakeServer()


@pytest.fixture
def fake_redis(server: FakeServer) -> FakeAsyncRedis:
    return FakeAsyncRedis(server=server)


@pytest.fixture
def cache(fake_redis: FakeAsyncRedis) -> CacheService:
    return CacheService(fake_redis)


# ── Default values ────────────────────────────────────────────────────


def test_default_symbols_not_empty():
    assert len(DEFAULT_SYMBOLS) >= 5
    assert "BTCUSDT" in DEFAULT_SYMBOLS


def test_default_prices_cover_defaults():
    for sym in list(DEFAULT_SYMBOLS)[:5]:
        assert sym in DEFAULT_PRICES, f"{sym} missing from DEFAULT_PRICES"


def test_default_price_fields():
    for sym, d in DEFAULT_PRICES.items():
        assert "price" in d
        assert "bid" in d
        assert "ask" in d
        assert "vol" in d
        assert "change_pct" in d
        assert d["price"] > 0
        assert d["bid"] > 0
        assert d["ask"] > 0


# ── BinancePriceClient scan_once (API success) ─────────────────────


@pytest.mark.asyncio
async def test_scan_once_returns_prices():
    client = BinancePriceClient(symbols=["BTCUSDT"])
    try:
        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            # First call: 24hr ticker
            # Second call: bookTicker
            mock_get.side_effect = [
                _mock_response([
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "67500.00",
                        "volume": "45000.123",
                        "priceChangePercent": "0.50",
                    }
                ]),
                _mock_response([
                    {
                        "symbol": "BTCUSDT",
                        "bidPrice": "67499.00",
                        "askPrice": "67501.00",
                    }
                ]),
            ]

            batch = await client.scan_once()

            assert "BTCUSDT" in batch
            price = batch["BTCUSDT"]
            assert isinstance(price, BinancePrice)
            assert price.price == 67500.0
            assert price.bid == 67499.0
            assert price.ask == 67501.0
            assert price.volume_24h == 45000.123
            assert price.price_change_pct == 0.50
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_scan_once_filters_symbols():
    """Only configured symbols are returned, others are skipped."""
    client = BinancePriceClient(symbols=["BTCUSDT"])
    try:
        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [
                _mock_response([
                    {"symbol": "BTCUSDT", "lastPrice": "67500", "volume": "1", "priceChangePercent": "0"},
                    {"symbol": "ETHUSDT", "lastPrice": "2650", "volume": "2", "priceChangePercent": "0"},
                ]),
                _mock_response([
                    {"symbol": "BTCUSDT", "bidPrice": "67499", "askPrice": "67501"},
                    {"symbol": "ETHUSDT", "bidPrice": "2649", "askPrice": "2651"},
                ]),
            ]

            batch = await client.scan_once()

            assert "BTCUSDT" in batch
            assert "ETHUSDT" not in batch
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_scan_once_uses_latest_cache():
    """After scan_once, latest_cache is updated."""
    client = BinancePriceClient(symbols=["BTCUSDT"])
    try:
        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [
                _mock_response([
                    {"symbol": "BTCUSDT", "lastPrice": "67500", "volume": "1", "priceChangePercent": "0"},
                ]),
                _mock_response([
                    {"symbol": "BTCUSDT", "bidPrice": "67499", "askPrice": "67501"},
                ]),
            ]

            await client.scan_once()

            latest = client.latest_cache
            assert "BTCUSDT" in latest
            assert latest["BTCUSDT"].price == 67500.0
    finally:
        await client.close()


# ── BinancePriceClient scan_once (API failure → defaults) ────────────


@pytest.mark.asyncio
async def test_scan_once_fallback_to_defaults():
    """When API fails, DEFAULT_PRICES are used as fallback."""
    client = BinancePriceClient(symbols=["BTCUSDT", "ETHUSDT"])
    try:
        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = Exception("Connection error")

            batch = await client.scan_once()

            assert "BTCUSDT" in batch
            assert "ETHUSDT" in batch
            assert batch["BTCUSDT"].price == DEFAULT_PRICES["BTCUSDT"]["price"]
            assert batch["ETHUSDT"].price == DEFAULT_PRICES["ETHUSDT"]["price"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_scan_once_fallback_only_configured_symbols():
    """Fallback only includes symbols in the client's config."""
    client = BinancePriceClient(symbols=["BTCUSDT"])
    try:
        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = Exception("Connection error")

            batch = await client.scan_once()

            assert "BTCUSDT" in batch
            # ETHUSDT is in DEFAULT_PRICES but not configured
            assert "ETHUSDT" not in batch
    finally:
        await client.close()


# ── BinancePriceClient get_candles ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_candles():
    client = BinancePriceClient(symbols=["BTCUSDT"])
    try:
        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            ts = int(datetime.now(timezone.utc).timestamp()) * 1000
            mock_get.return_value = _mock_response([
                [ts, "67000", "68000", "66500", "67500", "500.5", ts + 3600000],
                [ts + 3600000, "67500", "69000", "67000", "68000", "600.2", ts + 7200000],
            ])

            candles = await client.get_candles("BTCUSDT", interval="1h", limit=50)

            assert len(candles) == 2
            assert isinstance(candles[0], BinanceCandle)
            assert candles[0].open == 67000.0
            assert candles[0].high == 68000.0
            assert candles[0].low == 66500.0
            assert candles[0].close == 67500.0
            assert candles[0].volume == 500.5
    finally:
        await client.close()


# ── Cache seeding integration ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_seeding_prices(cache: CacheService):
    """Prices from scan_once can be batch-written to cache."""
    client = BinancePriceClient(symbols=["BTCUSDT", "ETHUSDT"])
    try:
        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [
                _mock_response([
                    {"symbol": "BTCUSDT", "lastPrice": "67500", "volume": "45000", "priceChangePercent": "0.5"},
                    {"symbol": "ETHUSDT", "lastPrice": "2650", "volume": "200000", "priceChangePercent": "-0.2"},
                ]),
                _mock_response([
                    {"symbol": "BTCUSDT", "bidPrice": "67499", "askPrice": "67501"},
                    {"symbol": "ETHUSDT", "bidPrice": "2649", "askPrice": "2651"},
                ]),
            ]

            prices = await client.scan_once()

            # Simulate what the lifespan does
            price_updates = []
            for sym, bp in prices.items():
                price_updates.append({
                    "exchange": "binance",
                    "symbol": sym,
                    "bid": f"{bp.bid:.8f}",
                    "ask": f"{bp.ask:.8f}",
                    "last": f"{bp.price:.8f}",
                    "volume_24h": f"{bp.volume_24h:.4f}",
                })

            await cache.set_price_batch(price_updates)

            # Verify prices are cached
            btc = await cache.get_price("binance", "BTCUSDT")
            assert btc is not None
            assert btc["last"] == "67500.00000000"
            assert btc["exchange"] == "binance"

            eth = await cache.get_price("binance", "ETHUSDT")
            assert eth is not None
            assert eth["last"] == "2650.00000000"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cache_seeding_candles(cache: CacheService):
    """Candles from get_candles can be written to cache."""
    client = BinancePriceClient(symbols=["BTCUSDT"])
    try:
        ts = int(datetime.now(timezone.utc).timestamp()) * 1000

        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = _mock_response([
                [ts, "67000", "68000", "66500", "67500", "500.5", ts + 3600000],
            ])

            candles = await client.get_candles("BTCUSDT", interval="1h", limit=50)

            candle_dicts = [
                {
                    "time": c.time,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ]

            await cache.set_candles(
                exchange="binance", symbol="BTCUSDT", interval="1h", candles=candle_dicts
            )

            result = await cache.get_candles("binance", "BTCUSDT", "1h")
            assert result is not None
            assert len(result) == 1
            assert result[0]["open"] == 67000.0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cache_seeding_fallback_prices(cache: CacheService):
    """Cache seeding still works when API fails (uses defaults)."""
    client = BinancePriceClient(symbols=["BTCUSDT"])
    try:
        with patch.object(
            client._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = Exception("API down")

            prices = await client.scan_once()

            assert "BTCUSDT" in prices
            assert prices["BTCUSDT"].price == DEFAULT_PRICES["BTCUSDT"]["price"]

            # Write to cache
            price_updates = [{
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "last": f"{prices['BTCUSDT'].price:.8f}",
                "bid": f"{prices['BTCUSDT'].bid:.8f}",
                "ask": f"{prices['BTCUSDT'].ask:.8f}",
                "volume_24h": f"{prices['BTCUSDT'].volume_24h:.4f}",
            }]
            await cache.set_price_batch(price_updates)

            cached = await cache.get_price("binance", "BTCUSDT")
            assert cached is not None
            assert cached["exchange"] == "binance"
    finally:
        await client.close()


# ── Context manager ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_context_manager():
    async with BinancePriceClient(symbols=["BTCUSDT"]) as client:
        assert client is not None
        # client._client should be open
        assert not client._client.is_closed


# ── Helpers ───────────────────────────────────────────────────────────


def _mock_response(json_data):
    """Create a mock httpx.Response with the given JSON data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp
