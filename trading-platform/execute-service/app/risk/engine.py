"""
Risk engine: position size limits, daily loss circuit breaker, token safety.

Uses Redis-backed counters for cross-request state persistence with
in-memory fallback when Redis is unavailable.

Checks run BEFORE order submission to prevent execution of orders
that violate risk parameters.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class RiskViolationError(Exception):
    """Raised when a risk check fails."""

    def __init__(self, reason: str, check_type: str, details: dict[str, Any] | None = None) -> None:
        self.reason = reason
        self.check_type = check_type
        self.details = details or {}
        super().__init__(f"[{check_type}] {reason}")


class RedisRiskStore:
    """Redis-backed risk state store for daily loss tracking."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis = None
        self._fallback = InMemoryRiskStore()

    async def initialize(self) -> None:
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=1,
            )
            await self._redis.ping()
            logger.info("Redis risk store connected")
        except Exception:
            logger.warning("Redis unavailable for risk store — using in-memory fallback")
            self._redis = None

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    async def get_daily_loss(self, wallet: str) -> float:
        """Get accumulated daily loss for a wallet."""
        if self._redis is None:
            return self._fallback.get_daily_loss(wallet)
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"risk:daily_loss:{wallet}:{today}"
            val = await self._redis.get(key)
            return float(val) if val else 0.0
        except Exception:
            return self._fallback.get_daily_loss(wallet)

    async def add_daily_loss(self, wallet: str, loss_usd: float) -> float:
        """Add to daily loss accumulator. Returns new total."""
        if self._redis is None:
            return self._fallback.add_daily_loss(wallet, loss_usd)
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"risk:daily_loss:{wallet}:{today}"
            new_total = await self._redis.incrbyfloat(key, loss_usd)
            # Auto-expire at end of day (26h buffer covers timezone edge)
            await self._redis.expire(key, 93600)
            return float(new_total)
        except Exception:
            return self._fallback.add_daily_loss(wallet, loss_usd)

    async def get_position_count(self, wallet: str) -> int:
        """Get current open position count for a wallet."""
        if self._redis is None:
            return self._fallback.get_position_count(wallet)
        try:
            key = f"risk:positions:{wallet}"
            val = await self._redis.get(key)
            return int(val) if val else 0
        except Exception:
            return self._fallback.get_position_count(wallet)

    async def increment_position_count(self, wallet: str) -> int:
        """Increment open position count."""
        if self._redis is None:
            return self._fallback.increment_position_count(wallet)
        try:
            key = f"risk:positions:{wallet}"
            new_count = await self._redis.incr(key)
            # Keep this key longer — it tracks state
            await self._redis.expire(key, 3600)
            return int(new_count)
        except Exception:
            return self._fallback.increment_position_count(wallet)

    async def decrement_position_count(self, wallet: str) -> None:
        """Decrement open position count (on close/cancel)."""
        if self._redis is None:
            self._fallback.decrement_position_count(wallet)
            return
        try:
            key = f"risk:positions:{wallet}"
            await self._redis.decr(key)
        except Exception:
            self._fallback.decrement_position_count(wallet)


class InMemoryRiskStore:
    """In-memory risk state store (fallback when Redis is unavailable)."""

    def __init__(self) -> None:
        self._daily_loss: dict[str, float] = {}
        self._position_counts: dict[str, int] = {}

    def get_daily_loss(self, wallet: str) -> float:
        return self._daily_loss.get(wallet, 0.0)

    def add_daily_loss(self, wallet: str, loss_usd: float) -> float:
        current = self._daily_loss.get(wallet, 0.0)
        new_total = current + loss_usd
        self._daily_loss[wallet] = new_total
        return new_total

    def get_position_count(self, wallet: str) -> int:
        return self._position_counts.get(wallet, 0)

    def increment_position_count(self, wallet: str) -> int:
        current = self._position_counts.get(wallet, 0)
        new_count = current + 1
        self._position_counts[wallet] = new_count
        return new_count

    def decrement_position_count(self, wallet: str) -> None:
        current = self._position_counts.get(wallet, 0)
        self._position_counts[wallet] = max(0, current - 1)


class RiskEngine:
    """Central risk checks executed before order placement."""

    def __init__(self, store: RedisRiskStore) -> None:
        self._store = store

    async def check_order(
        self,
        wallet_address: str,
        chain: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None = None,
        estimated_usd: float | None = None,
    ) -> None:
        """Run all risk checks. Raises RiskViolationError on failure.

        Checks:
        1. Token safety (blocked/allowed mints for Solana)
        2. Position size limit
        3. Daily loss circuit breaker
        4. Max open positions
        5. Solana max transaction size
        """
        await self._check_token_safety(chain, symbol)
        await self._check_position_size(wallet_address, quantity, price, estimated_usd)
        await self._check_daily_loss_circuit(wallet_address)
        await self._check_max_positions(wallet_address)
        await self._check_solana_tx_limit(chain, quantity)

    async def _check_token_safety(self, chain: str, symbol: str) -> None:
        """Block trades on sanctioned/rug-pulled tokens (Solana only)."""
        if chain != "solana":
            return

        # Map symbol to mint
        mint_map = {
            "SOL": "So11111111111111111111111111111111111111112",
            "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        }
        mint = mint_map.get(symbol.upper(), symbol)

        # Check blocklist
        for blocked in settings.blocked_token_mints:
            if mint.lower() == blocked.lower():
                raise RiskViolationError(
                    f"Token {symbol} (mint {mint}) is on the blocked list",
                    "token_safety",
                    {"mint": mint, "reason": "blocked"},
                )

        # Check allowlist (if enabled)
        if settings.allowed_token_mints is not None:
            mint_in_allowlist = any(
                mint.lower() == allowed.lower()
                for allowed in settings.allowed_token_mints
            )
            if not mint_in_allowlist:
                raise RiskViolationError(
                    f"Token {symbol} (mint {mint}) is not on the allowed list",
                    "token_safety",
                    {"mint": mint, "reason": "not_in_allowlist"},
                )

    async def _check_position_size(
        self,
        wallet: str,
        quantity: Decimal,
        price: Decimal | None,
        estimated_usd: float | None,
    ) -> None:
        """Reject orders exceeding max position size in USD."""
        # Calculate position value
        if estimated_usd:
            position_usd = estimated_usd
        elif price:
            position_usd = float(quantity * price)
        else:
            # No price/estimate available — skip check but log warning
            logger.warning(
                "Position size check skipped for %s: no price estimate available for %s",
                wallet, quantity,
            )
            return

        if position_usd > settings.max_position_size_usd:
            raise RiskViolationError(
                f"Position size ${position_usd:,.2f} exceeds max ${settings.max_position_size_usd:,.2f}",
                "position_size",
                {
                    "position_usd": position_usd,
                    "max_usd": settings.max_position_size_usd,
                    "wallet": wallet,
                },
            )

    async def _check_daily_loss_circuit(self, wallet: str) -> None:
        """Halt trading if daily loss exceeds threshold."""
        daily_loss = await self._store.get_daily_loss(wallet)

        if daily_loss >= settings.max_daily_loss_usd:
            raise RiskViolationError(
                f"Daily loss circuit breaker tripped: ${daily_loss:,.2f} / ${settings.max_daily_loss_usd:,.2f} limit",
                "daily_loss_circuit",
                {
                    "daily_loss": daily_loss,
                    "max_loss": settings.max_daily_loss_usd,
                    "wallet": wallet,
                },
            )

    async def _check_max_positions(self, wallet: str) -> None:
        """Reject if wallet already has max open positions."""
        count = await self._store.get_position_count(wallet)
        if count >= settings.max_open_positions:
            raise RiskViolationError(
                f"Max open positions ({settings.max_open_positions}) reached for wallet",
                "max_positions",
                {
                    "current_count": count,
                    "max_positions": settings.max_open_positions,
                    "wallet": wallet,
                },
            )

    async def _check_solana_tx_limit(self, chain: str, quantity: Decimal) -> None:
        """Reject Solana transactions exceeding max lamport transfer."""
        if chain != "solana":
            return

        # If quantity looks like lamports (large number), check against limit
        lamports = int(float(quantity))
        if lamports > 0 and lamports < 1_000_000_000:
            # Likely already in lamports
            pass
        elif lamports > settings.solana_max_tx_lamports:
            raise RiskViolationError(
                f"Solana transfer {lamports} lamports exceeds max {settings.solana_max_tx_lamports}",
                "solana_tx_limit",
                {
                    "lamports": lamports,
                    "max_lamports": settings.solana_max_tx_lamports,
                },
            )

    async def record_loss(self, wallet: str, loss_usd: float) -> float:
        """Record a realized loss. Returns new daily total."""
        return await self._store.add_daily_loss(wallet, abs(loss_usd))

    async def position_opened(self, wallet: str) -> int:
        """Track a new open position. Returns new count."""
        return await self._store.increment_position_count(wallet)

    async def position_closed(self, wallet: str) -> None:
        """Track a closed position."""
        await self._store.decrement_position_count(wallet)


# --- Module-level singleton ---
_risk_engine: RiskEngine | None = None


def get_risk_engine() -> RiskEngine:
    """Get the risk engine singleton (lazy init with in-memory store)."""
    global _risk_engine
    if _risk_engine is None:
        store = RedisRiskStore(settings.redis_url)
        _risk_engine = RiskEngine(store)
    return _risk_engine
