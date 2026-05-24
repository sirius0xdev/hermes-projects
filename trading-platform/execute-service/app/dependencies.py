"""
FastAPI dependency providers for executors and order manager.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from app.executors.hyperliquid import HyperliquidExecutor
from app.executors.solana import SolanaExecutor
from app.order.manager import OrderManager


@lru_cache(maxsize=1)
def get_hyperliquid_executor() -> HyperliquidExecutor:
    """Singleton: one Hyperliquid executor per service lifetime."""
    return HyperliquidExecutor()


@lru_cache(maxsize=1)
def get_solana_executor() -> SolanaExecutor:
    """Singleton: one Solana executor per service lifetime."""
    return SolanaExecutor()


def get_order_manager(
    hl: HyperliquidExecutor = Depends(get_hyperliquid_executor),
    sol: SolanaExecutor = Depends(get_solana_executor),
) -> OrderManager:
    """Order manager wired with both executors via FastAPI DI."""
    return OrderManager(hl_exec=hl, sol_exec=sol)
