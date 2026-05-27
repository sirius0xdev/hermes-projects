"""Hyperliquid L2 Order Book Ingester.

Fetches real-time L2 order book snapshots from Hyperliquid's public API
and publishes them as OrderbookEvent to Kafka.

Also writes directly to the hot Redis cache for low-latency serving
to the trading dashboard.

Hyperliquid public endpoint:
  POST https://api.hyperliquid.xyz/info
  {"type": "l2Book", "coin": "BTC"}

Usage (started from data-service lifespan):
    producer = DataProducer(...)
    ingester = HyperliquidOrderbookIngester(producer=producer)
    ingester.start()

Environment variables:
    HYPERLIQUID_COINS          - Comma-separated coins (default: BTC,ETH,SOL)
    HYPERLIQUID_OB_POLL_MS     - Poll interval in ms (default: 450)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from data_service.app.kafka.producer import DataProducer
from data_service.app.kafka.schemas import (
    OrderbookEvent,
    OrderbookLevel,
    PriceSource,
)

logger = logging.getLogger(__name__)


# Default coins to track (Hyperliquid naming)
DEFAULT_COINS = ["BTC", "ETH", "SOL", "HYPE"]


def _map_to_dashboard_symbol(coin: str) -> str:
    """Map Hyperliquid coin to dashboard symbol format (e.g. BTC -> BTC-PERP)."""
    coin = coin.upper()
    if coin in {"BTC", "ETH", "SOL", "HYPE", "ARB", "DOGE", "XRP", "AVAX"}:
        return f"{coin}-PERP"
    return f"{coin}-PERP"


class HyperliquidOrderbookIngester:
    """Polls Hyperliquid L2 books and streams them to Kafka + Redis cache."""

    def __init__(
        self,
        producer: DataProducer,
        coins: Optional[list[str]] = None,
        poll_interval_ms: int = 450,
        http_timeout: float = 8.0,
    ):
        self.producer = producer
        self.coins = coins or self._load_coins_from_env()
        self.poll_interval = poll_interval_ms / 1000.0
        self._client = httpx.AsyncClient(timeout=http_timeout)
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = {"requests": 0, "errors": 0, "last_success": None}

    def _load_coins_from_env(self) -> list[str]:
        env = os.getenv("HYPERLIQUID_COINS", "")
        if env.strip():
            return [c.strip().upper() for c in env.split(",") if c.strip()]
        return DEFAULT_COINS

    async def _fetch_l2_book(self, coin: str) -> Optional[dict]:
        """Fetch L2 book for a single coin from Hyperliquid."""
        try:
            resp = await self._client.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "l2Book", "coin": coin},
            )
            resp.raise_for_status()
            data = resp.json()
            self._stats["requests"] += 1
            return data
        except Exception as e:
            self._stats["errors"] += 1
            logger.warning("Hyperliquid L2 fetch failed for %s: %s", coin, e)
            return None

    def _parse_levels(self, levels: list[list[dict]]) -> tuple[list[OrderbookLevel], list[OrderbookLevel]]:
        """Convert Hyperliquid levels [[bids], [asks]] into our schema."""
        bids: list[OrderbookLevel] = []
        asks: list[OrderbookLevel] = []

        if len(levels) >= 1:
            for lvl in levels[0]:  # bids
                try:
                    bids.append(
                        OrderbookLevel(
                            price=Decimal(str(lvl["px"])),
                            quantity=Decimal(str(lvl["sz"])),
                        )
                    )
                except Exception:
                    continue

        if len(levels) >= 2:
            for lvl in levels[1]:  # asks
                try:
                    asks.append(
                        OrderbookLevel(
                            price=Decimal(str(lvl["px"])),
                            quantity=Decimal(str(lvl["sz"])),
                        )
                    )
                except Exception:
                    continue

        return bids, asks

    async def _process_coin(self, coin: str) -> None:
        """Fetch, parse, publish, and cache one coin's order book."""
        raw = await self._fetch_l2_book(coin)
        if not raw or "levels" not in raw:
            return

        bids, asks = self._parse_levels(raw.get("levels", []))
        if not bids and not asks:
            return

        symbol = _map_to_dashboard_symbol(coin)
        now = datetime.now(timezone.utc)

        event = OrderbookEvent(
            symbol=symbol,
            bids=bids[:50],   # cap depth
            asks=asks[:50],
            source=PriceSource.HYPERLIQUID,
            timestamp=now,
        )

        # Publish to Kafka (for other consumers / replay)
        try:
            self.producer.send_orderbook(event)
        except Exception as e:
            logger.exception("Failed to publish orderbook event for %s: %s", symbol, e)

        # Direct write to hot Redis cache (critical for dashboard latency)
        try:
            from data_service.app.routes.market_data import CACHE_SVC

            if CACHE_SVC is not None:
                bid_tuples = [(float(b.price), float(b.quantity)) for b in bids]
                ask_tuples = [(float(a.price), float(a.quantity)) for a in asks]
                await CACHE_SVC.set_orderbook("hyperliquid", symbol, bid_tuples, ask_tuples, depth=50)
                self._stats["last_success"] = now.isoformat()
        except Exception as e:
            logger.debug("Direct cache write skipped for %s (cache not ready?): %s", symbol, e)

    async def _run_loop(self) -> None:
        """Main polling loop."""
        logger.info("HyperliquidOrderbookIngester started for coins=%s", self.coins)

        while self._running:
            start = asyncio.get_event_loop().time()

            tasks = [self._process_coin(coin) for coin in self.coins]
            await asyncio.gather(*tasks, return_exceptions=True)

            elapsed = asyncio.get_event_loop().time() - start
            sleep_time = max(0.0, self.poll_interval - elapsed)
            await asyncio.sleep(sleep_time)

    def start(self) -> None:
        """Start background polling task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "HyperliquidOrderbookIngester running (coins=%s, poll=%.0fms)",
            self.coins,
            self.poll_interval * 1000,
        )

    async def stop(self) -> None:
        """Stop the ingester gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
        logger.info("HyperliquidOrderbookIngester stopped")

    def get_stats(self) -> dict:
        return {**self._stats, "coins": self.coins}