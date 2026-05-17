"""Market data ingester: fetches market data from external APIs (yfinance, etc.)
and streams it to Kafka topics.

Designed as a background service that runs continuously, fetching
market data at configurable intervals and publishing to Kafka.

Usage:
    ingester = MarketDataIngester(
        symbols=["BTC-USD", "ETH-USD", "SPY"],
        kafka_bootstrap="kafka:9092",
        interval_seconds=60,
    )
    await ingester.run()  # blocking loop
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

from data_service.app.kafka.topics import KafkaTopics

logger = logging.getLogger(__name__)


@dataclass
class IngesterConfig:
    """Configuration for the market data ingester."""

    symbols: list[str] = field(default_factory=lambda: ["BTC-USD", "ETH-USD"])
    kafka_bootstrap_servers: str = "kafka:9092"
    price_interval_seconds: int = 60
    batch_size: int = 50
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    # Source: 'yfinance' or custom callable
    data_source: str = "yfinance"


class MarketDataIngester:
    """Fetches market data from APIs and streams to Kafka.

    Uses yfinance as the default data source for stocks, ETFs,
    and crypto pairs available through Yahoo Finance.

    Can be extended with custom data sources for exchange-specific
    APIs (Binance, Coinbase, Hyperliquid, etc.).
    """

    def __init__(
        self,
        symbols: Optional[list[str]] = None,
        kafka_bootstrap_servers: str = "kafka:9092",
        price_interval_seconds: int = 60,
        batch_size: int = 50,
        max_retries: int = 3,
    ):
        self.config = IngesterConfig(
            symbols=symbols or ["BTC-USD", "ETH-USD"],
            kafka_bootstrap_servers=kafka_bootstrap_servers,
            price_interval_seconds=price_interval_seconds,
            batch_size=batch_size,
            max_retries=max_retries,
        )
        self._producer = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the ingester and connect to Kafka."""
        from data_service.app.kafka.producer import DataProducer

        self._producer = DataProducer(
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            client_id="market-data-ingester",
        )
        await self._producer.start()
        self._running = True
        logger.info(
            "MarketDataIngester started for symbols: %s",
            ", ".join(self.config.symbols),
        )

    async def stop(self) -> None:
        """Stop the ingester and close Kafka producer."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._producer:
            await self._producer.stop()
        logger.info("MarketDataIngester stopped")

    async def fetch_and_publish_prices(self, symbols: Optional[list[str]] = None) -> int:
        """Fetch current prices for symbols and publish to Kafka.

        Returns the number of successfully published price events.
        """
        from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource
        from decimal import Decimal

        symbols = symbols or self.config.symbols
        if not symbols:
            logger.warning("No symbols configured for price fetching")
            return 0

        published = 0

        # Batch fetch using yfinance for efficiency
        try:
            import yfinance as yf

            tickers = yf.Tickers(" ".join(symbols))
            for symbol in symbols:
                try:
                    ticker = tickers.tickers.get(symbol)
                    if ticker is None:
                        logger.warning("Ticker %s not found, skipping", symbol)
                        continue

                    info = ticker.fast_info
                    if info is None:
                        logger.warning("No fast_info for %s, skipping", symbol)
                        continue

                    price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                    if price is None:
                        # Fallback to full info
                        full_info = ticker.info
                        price = full_info.get("currentPrice") or full_info.get("regularMarketPrice")

                    if price is None:
                        logger.warning("No price data for %s", symbol)
                        continue

                    event = MarketPriceEvent(
                        symbol=symbol,
                        price=Decimal(str(price)),
                        bid=getattr(info, "day_high", None) and Decimal(str(getattr(info, "day_high", 0))),
                        ask=getattr(info, "day_low", None) and Decimal(str(getattr(info, "day_low", 0))),
                        volume_24h=None,  # yfinance doesn't provide reliable 24h volume
                        source=PriceSource.YFINANCE,
                        timestamp=datetime.utcnow(),
                    )

                    if self._producer:
                        await self._producer.send_price(event)
                        published += 1

                except Exception as e:
                    logger.error("Error fetching price for %s: %s", symbol, e, exc_info=True)

        except ImportError:
            logger.error("yfinance not installed. Install with: pip install yfinance")
            raise
        except Exception as e:
            logger.error("Batch fetch error: %s", e, exc_info=True)

        return published

    async def fetch_and_publish_batch(self) -> dict[str, Any]:
        """Fetch prices for all configured symbols and publish in batch.

        Returns summary of the batch operation.
        """
        start_time = datetime.utcnow()
        published = await self.fetch_and_publish_prices()
        elapsed = (datetime.utcnow() - start_time).total_seconds()

        return {
            "symbols_requested": len(self.config.symbols),
            "symbols_published": published,
            "elapsed_seconds": elapsed,
            "timestamp": start_time.isoformat(),
        }

    async def run_once(self) -> dict[str, Any]:
        """Run a single ingestion cycle.

        Useful for cron-based or scheduled ingestion.
        """
        if not self._producer or not self._producer.is_running:
            await self.start()

        try:
            result = await self.fetch_and_publish_batch()
            return result
        finally:
            await self.stop()

    async def run(self) -> None:
        """Run the continuous ingestion loop.

        Fetches and publishes market data at the configured interval.
        """
        if not self._producer or not self._producer.is_running:
            await self.start()

        logger.info(
            "Starting continuous ingestion (interval=%ds, symbols=%d)",
            self.config.price_interval_seconds,
            len(self.config.symbols),
        )

        while self._running:
            try:
                result = await self.fetch_and_publish_batch()
                logger.info(
                    "Ingestion cycle complete: %d/%d symbols published in %.2fs",
                    result["symbols_published"],
                    result["symbols_requested"],
                    result["elapsed_seconds"],
                )
            except Exception as e:
                logger.error("Ingestion cycle error: %s", e, exc_info=True)
                await asyncio.sleep(self.config.retry_delay_seconds)
                continue

            await asyncio.sleep(self.config.price_interval_seconds)

        await self.stop()

    async def run_background(self) -> asyncio.Task:
        """Start the ingestion loop as a background task.

        Returns the asyncio.Task for the running loop.
        """
        self._task = asyncio.create_task(self.run())
        return self._task

    @property
    def is_running(self) -> bool:
        """Whether the ingester is actively running."""
        return self._running
