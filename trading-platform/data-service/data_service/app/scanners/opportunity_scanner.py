"""Opportunity scanner — cross-chain arbitrage and yield spread detection.

Combines data from:
  - SolanaYieldScanner: Aave v3 + Solend supply/borrow yields
  - HyperliquidFundingScanner: perpetual funding rates

Detects:
  1. **Yield spread** — same asset on different lending protocols (e.g., USDC supply on Solend vs Aave)
  2. **Funding arbitrage** — negative funding on Hyperliquid + positive yield on Solana (cash & carry)
  3. **Delta-neutral arb** — long on one platform, short on another for basis convergence
  4. **Price differential** — mark price divergence between Hyperliquid and spot

Publishes OpportunityEvent to Kafka topic trading-platform.opportunities.v1.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

from data_service.app.kafka.producer import DataProducer
from data_service.app.kafka.schemas import OpportunityEvent, OpportunityType
from data_service.app.kafka.topics import KafkaTopics
from data_service.app.scanners.solana_yields import SolanaYieldScanner, YieldSnapshot
from data_service.app.scanners.hyperliquid_funding import HyperliquidFundingScanner, FundingRate

logger = logging.getLogger(__name__)


class OpportunityScanner:
    """Cross-chain opportunity scanner.

    Coordinates yield and funding scanners, computes opportunities,
    and publishes them to Kafka + SSE subscribers.

    Usage:
        scanner = OpportunityScanner(
            producer=data_producer,
            min_spread_pct=0.5,   # minimum 0.5% spread to report
        )
        async for opportunities in scanner.scan():
            # opportunities: list[OpportunityEvent]
            pass
    """

    # Common assets across protocols
    COMMON_ASSETS = ["USDC", "USDT", "BTC", "ETH", "SOL"]

    def __init__(
        self,
        producer: Optional[DataProducer] = None,
        min_spread_pct: float = 0.5,      # minimum spread to report
        min_funding_arb_apr: float = 1.0,  # minimum annualized for funding arb
        poll_interval: float = 300.0,      # scan every 5 minutes
        on_opportunity: Optional[Callable] = None,  # callback for SSE
    ):
        self._producer = producer
        self.min_spread_pct = min_spread_pct
        self.min_funding_arb_apr = min_funding_arb_apr
        self.poll_interval = poll_interval
        self._on_opportunity = on_opportunity
        self._running = False

        # Scanners
        self._yield_scanner = SolanaYieldScanner(poll_interval=poll_interval)
        self._funding_scanner = HyperliquidFundingScanner(poll_interval=poll_interval)

        # State
        self._latest: list[OpportunityEvent] = []
        self._lock = asyncio.Lock()

    @property
    def latest_opportunities(self) -> list[OpportunityEvent]:
        return list(self._latest)

    async def scan_once(self) -> list[OpportunityEvent]:
        """Run one scan cycle. Returns list of OpportunityEvent."""
        opportunities: list[OpportunityEvent] = []

        # Fetch data from both scanners concurrently
        yield_task = self._yield_scanner.scan_once()
        funding_task = self._funding_scanner.scan_once()

        results = await asyncio.gather(yield_task, funding_task, return_exceptions=True)

        if isinstance(results[0], dict):
            yield_batch = results[0]
        else:
            logger.warning("Yield scan failed: %s", results[0])
            yield_batch = self._yield_scanner.latest_cache

        if isinstance(results[1], dict):
            funding_batch = results[1]
        else:
            logger.warning("Funding scan failed: %s", results[1])
            funding_batch = self._funding_scanner.latest_cache

        # Detect opportunities
        opportunities.extend(self._detect_yield_spreads(yield_batch))
        opportunities.extend(self._detect_funding_arbs(yield_batch, funding_batch))
        opportunities.extend(self._detect_price_differentials(funding_batch))

        # Filter by minimum thresholds
        opportunities = [
            opp for opp in opportunities
            if abs(opp.spread_pct) >= self.min_spread_pct
        ]

        # Publish to Kafka
        if self._producer and opportunities:
            for opp in opportunities:
                try:
                    self._producer.send_message(
                        topic=KafkaTopics.OPPORTUNITIES,
                        key=f"{opp.opportunity_type.value}:{opp.symbol}",
                        value=opp.model_dump(mode="json"),
                        headers=[("event_type", b"opportunity")],
                    )
                except Exception:
                    logger.exception("Failed to publish opportunity %s", opp.opportunity_id)

        # Notify SSE subscribers
        if self._on_opportunity and opportunities:
            for opp in opportunities:
                try:
                    if asyncio.iscoroutinefunction(self._on_opportunity):
                        await self._on_opportunity(opp.model_dump(mode="json"))
                    else:
                        self._on_opportunity(opp.model_dump(mode="json"))
                except Exception:
                    logger.exception("Failed to notify SSE for opportunity %s", opp.opportunity_id)

        # Update latest
        async with self._lock:
            # Keep last 50 opportunities
            self._latest = opportunities + self._latest[:50 - len(opportunities)]

        logger.info("Scan complete: %d opportunities found", len(opportunities))
        return opportunities

    def _detect_yield_spreads(
        self, yields: dict[str, dict[str, YieldSnapshot]]
    ) -> list[OpportunityEvent]:
        """Detect yield spread opportunities between Solana lending protocols."""
        opportunities: list[OpportunityEvent] = []

        # Get all protocols
        protocols = list(yields.keys())
        if len(protocols) < 2:
            return opportunities

        # Compare each pair of protocols for each asset
        for i, proto_a in enumerate(protocols):
            for proto_b in protocols[i + 1:]:
                assets_a = yields.get(proto_a, {})
                assets_b = yields.get(proto_b, {})

                common = set(assets_a.keys()) & set(assets_b.keys())
                for asset in common:
                    snap_a = assets_a[asset]
                    snap_b = assets_b[asset]

                    # Supply yield spread
                    spread = snap_b.supply_apy - snap_a.supply_apy
                    if abs(spread) >= self.min_spread_pct:
                        opportunities.append(OpportunityEvent(
                            opportunity_id=str(uuid.uuid4()),
                            opportunity_type=OpportunityType.YIELD_SPREAD,
                            symbol=asset,
                            title=f"{asset} yield spread: {snap_b.protocol} {snap_b.supply_apy:.1f}% vs {snap_a.protocol} {snap_a.supply_apy:.1f}%",
                            description=f"Supply {asset} on {snap_b.protocol} for {spread:+.1f}% higher yield than {snap_a.protocol}",
                            platform_a=snap_a.protocol,
                            platform_a_value=round(snap_a.supply_apy, 2),
                            platform_b=snap_b.protocol,
                            platform_b_value=round(snap_b.supply_apy, 2),
                            spread_pct=round(spread, 2),
                            estimated_apr=round(abs(spread), 2),
                            risk_level="low" if asset.startswith("US") else "medium",
                            metadata={"asset": asset, "scan_type": "yield_spread"},
                        ))

        return opportunities

    def _detect_funding_arbs(
        self,
        yields: dict[str, dict[str, YieldSnapshot]],
        funding: dict[str, FundingRate],
    ) -> list[OpportunityEvent]:
        """Detect funding rate arbitrage: negative funding + positive yield."""
        opportunities: list[OpportunityEvent] = []

        for symbol, fund in funding.items():
            if fund.funding_rate_annual < -0.5:
                # Negative funding = shorts pay longs
                # Strategy: long on Hyperliquid, earn funding + yield
                for proto, assets in yields.items():
                    if symbol not in assets:
                        continue
                    snap = assets[symbol]

                    # Combined APR: positive yield from lending + negative funding paid to you
                    combined_apr = snap.supply_apy + abs(fund.funding_rate_annual)

                    if combined_apr >= self.min_funding_arb_apr:
                        opportunities.append(OpportunityEvent(
                            opportunity_id=str(uuid.uuid4()),
                            opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
                            symbol=symbol,
                            title=f"{symbol} funding arb: long Hyperliquid, lend on {proto}",
                            description=f"Negative funding on Hyperliquid ({fund.funding_rate_annual:.1f}% annual) + supply yield on {proto} ({snap.supply_apy:.1f}%) = {combined_apr:.1f}% combined APR",
                            platform_a="hyperliquid",
                            platform_a_value=round(fund.funding_rate_annual, 2),
                            platform_a_url=f"https://hyperliquid.xyz/trade/{symbol}",
                            platform_b=proto,
                            platform_b_value=round(snap.supply_apy, 2),
                            spread_pct=round(combined_apr, 2),
                            estimated_apr=round(combined_apr, 2),
                            risk_level="medium",
                            metadata={"asset": symbol, "scan_type": "funding_arb"},
                        ))

        return opportunities

    def _detect_price_differentials(
        self, funding: dict[str, FundingRate]
    ) -> list[OpportunityEvent]:
        """Detect mark vs index price differentials (basis opportunities)."""
        opportunities: list[OpportunityEvent] = []

        for symbol, fund in funding.items():
            if fund.index_price == 0:
                continue

            # Basis = (mark - index) / index * 100
            basis_pct = (fund.mark_price - fund.index_price) / fund.index_price * 100

            if abs(basis_pct) >= 0.05:  # 0.05% threshold
                direction = "premium" if basis_pct > 0 else "discount"
                opportunities.append(OpportunityEvent(
                    opportunity_id=str(uuid.uuid4()),
                    opportunity_type=OpportunityType.PRICE_DIFFERENTIAL,
                    symbol=symbol,
                    title=f"{symbol} trading at {basis_pct:+.3f}% {direction} vs index",
                    description=f"Mark: ${fund.mark_price:,.2f}, Index: ${fund.index_price:,.2f} — {direction} of {abs(basis_pct):.3f}%",
                    platform_a="hyperliquid_mark",
                    platform_a_value=round(fund.mark_price, 2),
                    platform_b="hyperliquid_index",
                    platform_b_value=round(fund.index_price, 2),
                    spread_pct=round(basis_pct, 4),
                    estimated_apr=round(basis_pct * 365 * 24, 2),  # hourly basis annualized
                    risk_level="low",
                    metadata={"asset": symbol, "scan_type": "price_diff"},
                ))

        return opportunities

    async def scan_loop(self):
        """Run continuous scanning loop."""
        self._running = True
        while self._running:
            try:
                await self.scan_once()
            except Exception:
                logger.exception("Error in opportunity scan loop")
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
        self._yield_scanner.stop()
        self._funding_scanner.stop()

    async def close(self) -> None:
        self.stop()
        await self._yield_scanner.close()
        await self._funding_scanner.close()
