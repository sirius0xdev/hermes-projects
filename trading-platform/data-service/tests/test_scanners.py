"""Tests for opportunity scanner components."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from data_service.app.kafka.schemas import (
    OpportunityEvent,
    OpportunityType,
)
from data_service.app.kafka.topics import KafkaTopics
from data_service.app.scanners.solana_yields import (
    SolanaYieldScanner,
    YieldSnapshot,
    DEFAULT_YIELDS,
)
from data_service.app.scanners.hyperliquid_funding import (
    HyperliquidFundingScanner,
    FundingRate,
    DEFAULT_FUNDING,
)
from data_service.app.scanners.opportunity_scanner import OpportunityScanner


# ── Solana Yield Scanner tests ── #


class TestSolanaYieldScanner:
    def test_init(self):
        scanner = SolanaYieldScanner(poll_interval=60)
        assert scanner.poll_interval == 60
        assert scanner.ASSETS == ["USDC", "USDT", "SOL", "BTC"]

    @pytest.mark.asyncio
    async def test_scan_once_returns_all_protocols(self):
        scanner = SolanaYieldScanner()
        batch = await scanner.scan_once()

        # Should have both protocols even if APIs fail
        assert "aave_v3_sol" in batch
        assert "solend" in batch

        # Each protocol should have all assets
        for protocol in batch:
            assert len(batch[protocol]) == 4
            for asset in ["USDC", "USDT", "SOL", "BTC"]:
                assert asset in batch[protocol]

    @pytest.mark.asyncio
    async def test_scan_once_snapshots_valid(self):
        scanner = SolanaYieldScanner()
        batch = await scanner.scan_once()

        for protocol, assets in batch.items():
            for asset, snap in assets.items():
                assert snap.protocol == protocol
                assert snap.asset == asset
                assert snap.supply_apy >= 0
                assert snap.borrow_apy >= 0
                assert 0 <= snap.utilization <= 1
                assert snap.timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_latest_cache_updates(self):
        scanner = SolanaYieldScanner()
        assert scanner.latest_cache == {}

        await scanner.scan_once()
        assert len(scanner.latest_cache) > 0

    @pytest.mark.asyncio
    async def test_close(self):
        scanner = SolanaYieldScanner()
        await scanner.scan_once()
        await scanner.close()
        assert not scanner._running

    def test_resolve_mint_usdc(self):
        result = SolanaYieldScanner._resolve_mint("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
        assert result == "USDC"

    def test_resolve_mint_sol(self):
        result = SolanaYieldScanner._resolve_mint("So11111111111111111111111111111111111111112")
        assert result == "SOL"

    def test_resolve_mint_unknown(self):
        result = SolanaYieldScanner._resolve_mint("unknown_mint")
        assert result is None

    def test_default_yields_structure(self):
        assert "aave_v3_sol" in DEFAULT_YIELDS
        assert "solend" in DEFAULT_YIELDS
        for protocol in DEFAULT_YIELDS:
            for asset in ["USDC", "USDT", "SOL", "BTC"]:
                assert asset in DEFAULT_YIELDS[protocol]
                d = DEFAULT_YIELDS[protocol][asset]
                assert "supply" in d
                assert "borrow" in d
                assert "utilization" in d


# ── Hyperliquid Funding Scanner tests ── #


class TestHyperliquidFundingScanner:
    def test_init(self):
        scanner = HyperliquidFundingScanner(poll_interval=1800)
        assert scanner.poll_interval == 1800

    @pytest.mark.asyncio
    async def test_scan_once_returns_symbols(self):
        scanner = HyperliquidFundingScanner()

        # Mock HTTP to return realistic data
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {"universe": [
                {"name": "BTC", "assetIndex": 0},
                {"name": "ETH", "assetIndex": 1},
            ]},
            [
                {"name": "BTC", "lastFundingRate": "0.0001", "markPx": "68500", "idxPx": "68480", "openInterest": "2500"},
                {"name": "ETH", "lastFundingRate": "0.00005", "markPx": "2650", "idxPx": "2648", "openInterest": "1800"},
            ],
        ]

        with patch.object(scanner._client, "post", new=AsyncMock(return_value=mock_resp)):
            batch = await scanner.scan_once()

        assert len(batch) >= 2
        assert "BTC" in batch
        assert "ETH" in batch

    @pytest.mark.asyncio
    async def test_scan_once_uses_defaults_on_api_failure(self):
        scanner = HyperliquidFundingScanner()

        with patch.object(scanner._client, "post", new=AsyncMock(side_effect=Exception("API down"))):
            batch = await scanner.scan_once()

        assert len(batch) > 0
        assert "BTC" in batch

    @pytest.mark.asyncio
    async def test_scan_once_funding_valid(self):
        scanner = HyperliquidFundingScanner()

        with patch.object(scanner._client, "post", new=AsyncMock(side_effect=Exception("no network"))):
            batch = await scanner.scan_once()

        for symbol, fr in batch.items():
            assert fr.symbol == symbol
            assert isinstance(fr.funding_rate, float)
            assert isinstance(fr.funding_rate_annual, float)
            assert fr.mark_price > 0
            assert fr.timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_latest_cache_updates(self):
        scanner = HyperliquidFundingScanner()
        assert scanner.latest_cache == {}

        with patch.object(scanner._client, "post", new=AsyncMock(side_effect=Exception("no network"))):
            await scanner.scan_once()

        assert len(scanner.latest_cache) > 0

    @pytest.mark.asyncio
    async def test_close(self):
        scanner = HyperliquidFundingScanner()
        await scanner.scan_once()
        await scanner.close()
        assert not scanner._running

    def test_default_funding_structure(self):
        assert "BTC" in DEFAULT_FUNDING
        for symbol in DEFAULT_FUNDING:
            d = DEFAULT_FUNDING[symbol]
            assert "rate" in d
            assert "annual" in d
            assert "mark" in d
            assert "oi" in d
            assert "index" in d


# ── Opportunity Event schema tests ── #


class TestOpportunityEvent:
    def test_create_yield_spread(self):
        opp = OpportunityEvent(
            opportunity_id="test-001",
            opportunity_type=OpportunityType.YIELD_SPREAD,
            symbol="usdc",  # should be uppercased
            title="USDC yield spread",
            platform_a="aave_v3_sol",
            platform_a_value=4.5,
            platform_b="solend",
            platform_b_value=5.8,
            spread_pct=1.3,
            estimated_apr=1.3,
            risk_level="low",
        )
        assert opp.symbol == "USDC"
        assert opp.opportunity_type == OpportunityType.YIELD_SPREAD
        assert opp.spread_pct == 1.3

    def test_create_funding_arb(self):
        opp = OpportunityEvent(
            opportunity_id="test-002",
            opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
            symbol="ETH",
            title="ETH funding arb",
            platform_a="hyperliquid",
            platform_a_value=-0.5,
            platform_b="solend",
            platform_b_value=1.2,
            spread_pct=1.7,
            estimated_apr=1.7,
            risk_level="medium",
        )
        assert opp.symbol == "ETH"
        assert opp.platform_a == "hyperliquid"

    def test_model_dump(self):
        opp = OpportunityEvent(
            opportunity_id="test-003",
            opportunity_type=OpportunityType.PRICE_DIFFERENTIAL,
            symbol="BTC",
            title="BTC price diff",
            platform_a="hyperliquid_mark",
            platform_a_value=68500,
            platform_b="hyperliquid_index",
            platform_b_value=68480,
            spread_pct=0.03,
            estimated_apr=0.03,
            risk_level="low",
        )
        dump = opp.model_dump(mode="json")
        assert dump["symbol"] == "BTC"
        assert dump["opportunity_type"] == "price_differential"
        assert "detected_at" in dump


# ── Opportunity Scanner integration tests ── #


class TestOpportunityScanner:
    @pytest.mark.asyncio
    async def test_scan_once_detects_yield_spreads(self):
        scanner = OpportunityScanner(min_spread_pct=0.1)

        # Inject test yield data with a spread
        now = datetime.now(timezone.utc)
        scanner._yield_scanner._cache = {
            "aave_v3_sol": {
                "USDC": YieldSnapshot(
                    protocol="aave_v3_sol", asset="USDC",
                    supply_apy=4.0, borrow_apy=5.0,
                    timestamp=now, utilization=0.8,
                ),
            },
            "solend": {
                "USDC": YieldSnapshot(
                    protocol="solend", asset="USDC",
                    supply_apy=6.0, borrow_apy=7.0,
                    timestamp=now, utilization=0.88,
                ),
            },
        }
        scanner._funding_scanner._cache = {}

        opps = await scanner.scan_once()

        # Should detect yield spread between Solend and Aave for USDC
        yield_spreads = [o for o in opps if o.opportunity_type == OpportunityType.YIELD_SPREAD]
        assert len(yield_spreads) > 0
        usdc_spread = [o for o in yield_spreads if o.symbol == "USDC"]
        assert len(usdc_spread) > 0
        assert abs(usdc_spread[0].spread_pct) >= 0.1

    @pytest.mark.asyncio
    async def test_scan_once_detects_funding_arbs(self):
        scanner = OpportunityScanner(min_spread_pct=0.1, min_funding_arb_apr=0.5)

        now = datetime.now(timezone.utc)
        yield_data = {
            "aave_v3_sol": {
                "BTC": YieldSnapshot(
                    protocol="aave_v3_sol", asset="BTC",
                    supply_apy=2.0, borrow_apy=3.0,
                    timestamp=now, utilization=0.5,
                ),
            },
        }
        funding_data = {
            "BTC": FundingRate(
                symbol="BTC",
                funding_rate=-0.001,
                funding_rate_annual=-8.76,
                mark_price=68500,
                open_interest=2500,
                timestamp=now,
                index_price=68480,
            ),
        }

        # Mock sub-scanner scan_once to return our test data
        scanner._yield_scanner.scan_once = AsyncMock(return_value=yield_data)
        scanner._funding_scanner.scan_once = AsyncMock(return_value=funding_data)

        opps = await scanner.scan_once()

        funding_arbs = [o for o in opps if o.opportunity_type == OpportunityType.FUNDING_ARBITRAGE]
        btc_arbs = [o for o in funding_arbs if o.symbol == "BTC"]
        assert len(btc_arbs) > 0
        assert btc_arbs[0].estimated_apr > 0  # Combined should be positive

    @pytest.mark.asyncio
    async def test_scan_once_detects_price_differentials(self):
        scanner = OpportunityScanner(min_spread_pct=0.01)

        now = datetime.now(timezone.utc)
        funding_data = {
            "ETH": FundingRate(
                symbol="ETH",
                funding_rate=0.0001,
                funding_rate_annual=0.876,
                mark_price=2700,
                open_interest=1800,
                timestamp=now,
                index_price=2600,  # 3.8% difference
            ),
        }

        scanner._yield_scanner.scan_once = AsyncMock(return_value={})
        scanner._funding_scanner.scan_once = AsyncMock(return_value=funding_data)

        opps = await scanner.scan_once()

        price_diffs = [o for o in opps if o.opportunity_type == OpportunityType.PRICE_DIFFERENTIAL]
        eth_diffs = [o for o in price_diffs if o.symbol == "ETH"]
        assert len(eth_diffs) > 0

    @pytest.mark.asyncio
    async def test_filter_by_min_spread(self):
        scanner = OpportunityScanner(min_spread_pct=5.0)

        now = datetime.now(timezone.utc)
        scanner._yield_scanner._cache = {
            "aave_v3_sol": {
                "USDC": YieldSnapshot(
                    protocol="aave_v3_sol", asset="USDC",
                    supply_apy=4.0, borrow_apy=5.0,
                    timestamp=now, utilization=0.8,
                ),
            },
            "solend": {
                "USDC": YieldSnapshot(
                    protocol="solend", asset="USDC",
                    supply_apy=4.5, borrow_apy=5.5,  # Only 0.5% spread
                    timestamp=now, utilization=0.88,
                ),
            },
        }
        scanner._funding_scanner._cache = {}

        opps = await scanner.scan_once()

        # 0.5% spread is below 5.0% threshold, so should be filtered out
        yield_spreads = [o for o in opps if o.opportunity_type == OpportunityType.YIELD_SPREAD]
        assert len(yield_spreads) == 0

    @pytest.mark.asyncio
    async def test_publishes_to_kafka(self):
        mock_producer = MagicMock()
        mock_producer.send_message = MagicMock()

        scanner = OpportunityScanner(producer=mock_producer, min_spread_pct=0.1)

        now = datetime.now(timezone.utc)
        scanner._yield_scanner._cache = {
            "aave_v3_sol": {
                "USDC": YieldSnapshot(
                    protocol="aave_v3_sol", asset="USDC",
                    supply_apy=4.0, borrow_apy=5.0,
                    timestamp=now, utilization=0.8,
                ),
            },
            "solend": {
                "USDC": YieldSnapshot(
                    protocol="solend", asset="USDC",
                    supply_apy=7.0, borrow_apy=8.0,
                    timestamp=now, utilization=0.88,
                ),
            },
        }
        scanner._funding_scanner._cache = {}

        await scanner.scan_once()

        # Producer should have been called
        assert mock_producer.send_message.called
        call_args = mock_producer.send_message.call_args
        assert call_args.kwargs["topic"] == KafkaTopics.OPPORTUNITIES

    @pytest.mark.asyncio
    async def test_latest_opportunities_caches(self):
        scanner = OpportunityScanner(min_spread_pct=0.1)

        now = datetime.now(timezone.utc)
        scanner._yield_scanner._cache = {
            "aave_v3_sol": {
                "USDC": YieldSnapshot(
                    protocol="aave_v3_sol", asset="USDC",
                    supply_apy=4.0, borrow_apy=5.0,
                    timestamp=now, utilization=0.8,
                ),
            },
            "solend": {
                "USDC": YieldSnapshot(
                    protocol="solend", asset="USDC",
                    supply_apy=7.0, borrow_apy=8.0,
                    timestamp=now, utilization=0.88,
                ),
            },
        }
        scanner._funding_scanner._cache = {}

        await scanner.scan_once()

        latest = scanner.latest_opportunities
        assert len(latest) > 0
        assert latest[0].opportunity_type == OpportunityType.YIELD_SPREAD

    @pytest.mark.asyncio
    async def test_stop_propagates(self):
        scanner = OpportunityScanner()
        scanner._running = True
        scanner.stop()
        assert not scanner._running
        assert not scanner._yield_scanner._running
        assert not scanner._funding_scanner._running

    @pytest.mark.asyncio
    async def test_close(self):
        scanner = OpportunityScanner()
        await scanner.scan_once()
        await scanner.close()
        assert not scanner._running
