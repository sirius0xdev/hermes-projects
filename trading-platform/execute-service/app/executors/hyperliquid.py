"""
Hyperliquid SDK integration for trade execution (futures + spot).
Uses the official hyperliquid-python-sdk.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from hyperliquid import info
from hyperliquid.utils import constants
from hyperliquid.exchange import Exchange

from app.config import settings

logger = logging.getLogger(__name__)


class HyperliquidExecutor:
    """Thin wrapper around hyperliquid-python-sdk for unified execution API."""

    def __init__(self) -> None:
        self.testnet = settings.hyperliquid_testnet
        self._info: info.Info | None = None
        self._exchange: Exchange | None = None
        self._initialized = False

    def _require_private_key(self) -> None:
        if not settings.hyperliquid_private_key:
            raise RuntimeError(
                "HYPERLIQUID_PRIVATE_KEY not configured — can only use read-only endpoints"
            )

    async def initialize(self) -> None:
        """Lazy-init SDK clients.

        Updated for current hyperliquid-python-sdk (Info.__init__ no longer accepts `testnet=`).
        Uses constants.MAINNET_API_URL / TESTNET_API_URL + skip_ws=True.
        """
        if self._initialized:
            return

        base_url = constants.TESTNET_API_URL if self.testnet else constants.MAINNET_API_URL
        self._info = info.Info(base_url, skip_ws=True)

        if settings.hyperliquid_private_key:
            self._exchange = Exchange(
                settings.hyperliquid_private_key,
                settings.hyperliquid_wallet_address,
                testnet=self.testnet,
            )
        self._initialized = True
        logger.info(
            "Hyperliquid SDK initialized (testnet=%s, signing=%s)",
            self.testnet,
            bool(settings.hyperliquid_private_key),
        )

    async def place_market_order(
        self,
        coin: str,
        is_buy: bool,
        size: Decimal,
        is_futures: bool = True,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Place a market order on Hyperliquid."""
        await self.initialize()
        self._require_private_key()

        assert self._exchange is not None
        response = self._exchange.market_open(
            coin=coin,
            is_buy=is_buy,
            sz=float(size),
            reduce_only=reduce_only,
            slippage=0.01,  # 1% slippage tolerance
        )
        logger.info("Hyperliquid market order placed: %s", response)
        return {"status": "submitted", "response": response}

    async def place_limit_order(
        self,
        coin: str,
        is_buy: bool,
        size: Decimal,
        price: Decimal,
        is_futures: bool = True,
        reduce_only: bool = False,
        tif: str = "GTC",
    ) -> dict[str, Any]:
        """Place a limit order on Hyperliquid."""
        await self.initialize()
        self._require_private_key()

        assert self._exchange is not None
        response = self._exchange.limit_order(
            coin=coin,
            is_buy=is_buy,
            sz=float(size),
            limit_px=float(price),
            order_type={"limit": {"tif": tif}},
            reduce_only=reduce_only,
        )
        logger.info("Hyperliquid limit order placed: %s", response)
        return {"status": "submitted", "response": response}

    async def place_stop_order(
        self,
        coin: str,
        is_buy: bool,
        size: Decimal,
        trigger_price: Decimal,
        is_futures: bool = True,
        reduce_only: bool = True,
    ) -> dict[str, Any]:
        """Place a trigger/stop order on Hyperliquid."""
        await self.initialize()
        self._require_private_key()

        assert self._exchange is not None
        response = self._exchange.order(
            coin=coin,
            is_buy=is_buy,
            sz=float(size),
            limit_px=float(trigger_price),
            order_type={"trigger": {"triggerPx": float(trigger_price), "isMarket": True, "tpsl": "sl"}},
            reduce_only=reduce_only,
        )
        logger.info("Hyperliquid stop order placed: %s", response)
        return {"status": "submitted", "response": response}

    async def cancel_order(self, coin: str, order_id: int) -> dict[str, Any]:
        """Cancel an order by ID."""
        await self.initialize()
        self._require_private_key()

        assert self._exchange is not None
        response = self._exchange.cancel(coin=coin, order_id=order_id)
        logger.info("Hyperliquid order cancelled: %s", response)
        return {"status": "cancelled", "response": response}

    async def cancel_all_orders(self) -> dict[str, Any]:
        """Cancel all open orders."""
        await self.initialize()
        self._require_private_key()

        assert self._exchange is not None
        response = self._exchange.cancel_open_orders()
        return {"status": "cancelled_all", "response": response}

    async def get_open_orders(self) -> list[dict[str, Any]]:
        """Get all open orders."""
        await self.initialize()
        assert self._info is not None
        return self._info.open_orders(settings.hyperliquid_wallet_address)

    async def get_user_state(self) -> dict[str, Any]:
        """Get user account state (balance, margin)."""
        await self.initialize()
        assert self._info is not None
        return self._info.user_state(settings.hyperliquid_wallet_address)

    async def get_positions(self) -> list[dict[str, Any]]:
        """Get current positions."""
        if not settings.hyperliquid_wallet_address:
            return []
        await self.initialize()
        assert self._info is not None
        user_state = self._info.user_state(settings.hyperliquid_wallet_address)
        return user_state.get("assetPositions", [])

    async def get_market_price(self, coin: str) -> float:
        """Get current market price for a coin from AllMids."""
        await self.initialize()
        assert self._info is not None
        mids = self._info.all_mids()
        return float(mids[coin])

    async def get_fills(self, time: int | None = None) -> list[dict[str, Any]]:
        """Get recent fills/trades."""
        await self.initialize()
        assert self._info is not None
        if time:
            return self._info.user_fills(
                settings.hyperliquid_wallet_address,
                time=time,
            )
        return self._info.user_fills(settings.hyperliquid_wallet_address)
