#!/usr/bin/env python3
"""Wallet tracker: provider-agnostic watchlist lookup returning WalletSignal dicts."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Dict

# Use the planner's WalletSignal dataclass without coupling to a live provider.
from planner import WalletSignal


# ---------------------------------------------------------------------------
# Abstract data-source contract
# ---------------------------------------------------------------------------
class WalletDataSource(ABC):
    """Fetch wallet movements and normalise them into WalletSignal instances."""

    @abstractmethod
    def fetch(self, watchlist: Dict[str, Dict]) -> Dict[str, WalletSignal]:
        """Return {wallet_address: WalletSignal} for the given watchlist config."""



# ---------------------------------------------------------------------------
# Built-in dummy source
# ---------------------------------------------------------------------------
_DUMMY_WATCHLIST: Dict[str, Dict] = {
    "0x1111111111111111111111111111111111111111": {
        "asset": "BTC",
        "notional": 250_000.0,
        "side": "buy",
        "expected_impact": "up",
        "label": "Whale Alpha",
    },
    "0x2222222222222222222222222222222222222222": {
        "asset": "ETH",
        "notional": 120_000.0,
        "side": "sell",
        "expected_impact": "down",
        "label": "Fund Beta",
    },
}


class DummySource(WalletDataSource):
    """Deterministic offline source. Great for tests, CI, and demos."""

    def fetch(self, watchlist: Dict[str, Dict] | None = None) -> Dict[str, WalletSignal]:
        watchlist = watchlist or _DUMMY_WATCHLIST
        signals: Dict[str, WalletSignal] = {}
        for wallet, cfg in watchlist.items():
            signals[wallet] = WalletSignal(
                wallet=wallet,
                asset=cfg["asset"],
                notional=float(cfg.get("notional", 0.0)),
                side=str(cfg.get("side", "unknown")).lower(),
                expected_impact=str(cfg.get("expected_impact", "neutral")).lower(),
                source="wallet_tracker:",
            )
        return signals



# ---------------------------------------------------------------------------
# Public free-source implementation
# ---------------------------------------------------------------------------
_DEFAULT_PUBLIC_ENDPOINT = "https://api.example.com/v1/wallets/moves"


class FreePublicSource(WalletDataSource):
    """
    Best-effort fetch from a free/public endpoint.

    Designed to be swapped for any REST feed (Etherscan, Arkham, etc.)
    without touching the rest of the codebase. If the network call fails
    or returns nothing usable, falls back silently to DummySource so the
    caller always gets a non-empty dict.
    """

    def __init__(self, endpoint: str = _DEFAULT_PUBLIC_ENDPOINT, timeout: float = 4.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._fallback = DummySource()

    def fetch(self, watchlist: Dict[str, Dict] | None = None) -> Dict[str, WalletSignal]:
        watchlist = watchlist or _DUMMY_WATCHLIST

        try:
            import urllib.request

            req = urllib.request.Request(
                self.endpoint,
                headers={"Accept": "application/json", "User-Agent": "wallet-tracker/0.1"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except Exception:
            # Network/DNS/HTTP error -> fine, just use fallback
            return self._fallback.fetch(watchlist)

        # Try to parse; on any parse problem, fall back too.
        try:
            import json

            payload = json.loads(raw)
        except Exception:
            return self._fallback.fetch(watchlist)

        if not isinstance(payload, list) or len(payload) == 0:
            return self._fallback.fetch(watchlist)

        # Minimal normalisation: accept list of dicts with wallet address.
        signals: Dict[str, WalletSignal] = {}
        now = time.time()
        unknown_asset = watchlist[next(iter(watchlist))]["asset"] if watchlist else "UNKNOWN"
        for item in payload:
            wallet = str(item.get("wallet") or item.get("address") or "").lower()
            if not wallet:
                continue
            watchlist.setdefault(wallet, {"asset": unknown_asset, "notional": 0.0, "side": "buy", "expected_impact": "neutral"})
            cfg = watchlist[wallet]
            signals[wallet] = WalletSignal(
                wallet=wallet,
                asset=cfg["asset"],
                notional=float(cfg.get("notional", 0.0)),
                side=str(cfg.get("side", "buy")).lower(),
                expected_impact=str(cfg.get("expected_impact", "neutral")).lower(),
                source=f"wallet_tracker:{self.endpoint}",
            )
        return signals or self._fallback.fetch(watchlist)


# ---------------------------------------------------------------------------
# Provider-agnostic runner
# ---------------------------------------------------------------------------
_default_source: WalletDataSource = DummySource()


def get_wallet_signals(
    watchlist: Dict[str, Dict] | None = None,
    source: WalletDataSource | None = None,
) -> Dict[str, WalletSignal]:
    """
    Return wallet signals keyed by wallet address.

    - watchlist: optional override mapping of address -> config dict.
      If omitted, the built-in tiny dummy watchlist is used.
    - source: optional WalletDataSource override. If omitted, uses the
      module-level default, which is DummySource for offline reliability.
    """
    resolver = source or _default_source
    return resolver.fetch(watchlist=watchlist)



# ---------------------------------------------------------------------------
# Tiny demo / sanity check
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    signals = get_wallet_signals()
    print(f"Loaded {len(signals)} wallet signal(s):")
    for addr, sig in signals.items():
        print(f"  {sig.wallet}  asset={sig.asset}  notional={sig.notional:.0f}  side={sig.side}  impact={sig.expected_impact}")
