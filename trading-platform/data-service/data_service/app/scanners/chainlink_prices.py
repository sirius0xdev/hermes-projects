"""Chainlink Data API client — authenticated REST for on-chain price feeds.

Fetches real-time price data from Chainlink's Data API v2:
  POST https://api.chain.link/api/v2/data-feeds/{network}-{address}/latest

Requires an API key (env var CHAINLINK_API_KEY). Used as the primary
price source for the dashboard — prices flow into Redis cache on startup
and on cache-miss fallback.

Symbols supported (Ethereum Mainnet feeds):
  BTC, ETH, SOL, DOGE, ARB

Usage:
    client = ChainlinkPriceClient()
    price = await client.get_price("BTC")     # ChainlinkPrice | None
    batch = await client.scan_once()           # dict[symbol -> ChainlinkPrice]
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Ethereum Mainnet Data Feed addresses ────────────────────────────

FEED_ADDRESSES: dict[str, str] = {
    "BTC": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "ETH": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
    "SOL": "0xEd6F8C8AA3f5e81dC9B01458a2D2E0d67E6e65B8",
    "DOGE": "0x15037764299A0C569c8Dd5b26667A17e8753A970",
    "ARB": "0x4E352cF164E64EF5E1d85596bE6717245227BAd7",
}

# Decimal places per feed (Chainlink returns raw integer prices)
FEED_DECIMALS: dict[str, int] = {
    "BTC": 8,
    "ETH": 8,
    "SOL": 8,
    "DOGE": 8,
    "ARB": 8,
}

# Fallback symbol -> Binance symbol mapping for candle data
SYMBOL_BINANCE: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "DOGE": "DOGEUSDT",
    "ARB": "ARBUSDT",
}

DEFAULT_SYMBOLS = list(FEED_ADDRESSES.keys())


@dataclass
class ChainlinkPrice:
    """A single price tick from Chainlink."""

    symbol: str         # e.g. "BTC"
    price: float        # decoded last price
    bid: float          # bid price (may equal price if not available)
    ask: float          # ask price (may equal price if not available)
    volume_24h: float   # estimated 24h volume (0 if not from this API)
    price_change_pct: float  # 24h change % (0 if not from this API)
    timestamp: datetime  # UTC timestamp of the reading


@dataclass
class ChainlinkCandle:
    """A single OHLCV candle (aggregated from Chainlink heartbeats or fallback)."""

    time: str       # ISO 8601 timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChainlinkPriceClient:
    """Fetches real-time prices from Chainlink Data API v2.

    Requires CHAINLINK_API_KEY env var for authentication.
    Falls back gracefully if API is unavailable.

    Usage:
        client = ChainlinkPriceClient()
        price = await client.get_price("BTC")
        batch = await client.scan_once()
    """

    BASE_URL = "https://api.chain.link/api/v2"
    NETWORK = "ethereum"  # Mainnet

    def __init__(
        self,
        http_timeout: float = 15.0,
        symbols: Optional[list[str]] = None,
    ):
        self.symbols = symbols or list(DEFAULT_SYMBOLS)
        api_key = os.getenv("CHAINLINK_API_KEY", "")
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=http_timeout,
            headers={
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json",
                "User-Agent": "trading-data-service/0.1.0",
            },
        )
        self._cache: dict[str, ChainlinkPrice] = {}
        self._api_key = api_key

    @property
    def latest_cache(self) -> dict[str, ChainlinkPrice]:
        """Return a copy of the latest cached prices."""
        return dict(self._cache)

    def _decode_price(self, symbol: str, raw: str) -> float:
        """Decode a Chainlink raw price string using feed decimals."""
        decimals = FEED_DECIMALS.get(symbol, 8)
        try:
            return int(raw) / (10 ** decimals)
        except (ValueError, TypeError):
            return 0.0

    async def get_price(self, symbol: str) -> Optional[ChainlinkPrice]:
        """Fetch the latest price for a single symbol from Chainlink.

        Returns None if the API call fails or symbol is unknown.
        """
        address = FEED_ADDRESSES.get(symbol)
        if not address:
            logger.warning("No Chainlink feed for symbol %s", symbol)
            return None

        endpoint = f"/data-feeds/{self.NETWORK}-{address}/latest"
        now = datetime.now(timezone.utc)

        try:
            resp = await self._client.post(endpoint, json={})
            resp.raise_for_status()
            data = resp.json()

            # Chainlink API returns answer inside 'data.answer' for v2
            answer_data = data.get("data", {}).get("answer", {})
            raw_answer = answer_data.get("answer", "0")
            raw_bid = answer_data.get("bid", raw_answer)
            raw_ask = answer_data.get("ask", raw_answer)
            round_timestamp = answer_data.get("round", 0)

            # Decode prices
            price = self._decode_price(symbol, raw_answer)
            bid = self._decode_price(symbol, raw_bid)
            ask = self._decode_price(symbol, raw_ask)

            # Timestamp from round timestamp (Unix seconds)
            ts = datetime.fromtimestamp(round_timestamp, tz=timezone.utc)

            return ChainlinkPrice(
                symbol=symbol,
                price=price,
                bid=bid,
                ask=ask,
                volume_24h=0.0,
                price_change_pct=0.0,
                timestamp=ts,
            )

        except Exception as e:
            logger.warning("Chainlink price fetch failed for %s: %s", symbol, e)
            return None

    async def scan_once(self) -> dict[str, ChainlinkPrice]:
        """Fetch latest prices for all configured symbols.

        Fetches in parallel, falls back to previous cache for failed symbols.
        Returns dict mapping symbol -> ChainlinkPrice.
        """
        batch: dict[str, ChainlinkPrice] = {}
        now = datetime.now(timezone.utc)

        # Fetch all symbols in parallel
        tasks = [self.get_price(sym) for sym in self.symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(self.symbols, results):
            if isinstance(result, Exception):
                logger.warning("Failed to fetch %s from Chainlink: %s", sym, result)
                if sym in self._cache:
                    batch[sym] = self._cache[sym]
                continue
            if isinstance(result, ChainlinkPrice):
                batch[sym] = result

        # Update internal cache
        self._cache.update(batch)
        logger.info("Chainlink price scan complete: %d/%d symbols", len(batch), len(self.symbols))
        return batch

    async def get_candles(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 50,
    ) -> list[ChainlinkCandle]:
        """Get candle data for a symbol.

        Chainlink doesn't provide OHLC candles natively — delegate to
        Binance for candle data. Returns empty list on failure.
        """
        binance_symbol = SYMBOL_BINANCE.get(symbol)
        if not binance_symbol:
            return []

        try:
            from data_service.app.scanners.binance_prices import BinancePriceClient

            binance = BinancePriceClient(http_timeout=12)
            candles = await binance.get_candles(
                binance_symbol, interval=interval, limit=limit
            )
            await binance.close()

            # Re-wrap as ChainlinkCandle (same shape)
            return [
                ChainlinkCandle(
                    time=c.time,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                )
                for c in candles
            ]
        except Exception as e:
            logger.warning("Candle fetch failed for %s: %s", symbol, e)
            return []

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "ChainlinkPriceClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


import asyncio
