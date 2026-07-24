"""Hyperliquid asset-context helpers and soft entry gates for hybrid_bot v2.

Pure functions only — no bot/network imports — so the gate logic is unit-testable.
Implements plan: docs/plans/2026-07-24_hybrid-p0-p1-filters-hl-context.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AssetCtx:
    coin: str           # bot coin id e.g. BTC or xyz:GOLD
    funding: Optional[float] = None
    open_interest: Optional[float] = None
    premium: Optional[float] = None
    oracle_px: Optional[float] = None
    mark_px: Optional[float] = None
    mid_px: Optional[float] = None
    day_ntl_vlm: Optional[float] = None
    impact_bid: Optional[float] = None
    impact_ask: Optional[float] = None
    prev_open_interest: Optional[float] = None


def universe_name(coin: str) -> str:
    """xyz:GOLD -> GOLD; BTC -> BTC."""
    return coin.split(":", 1)[-1] if ":" in coin else coin


def dex_for_coin(coin: str) -> str:
    return coin.split(":", 1)[0] if ":" in coin else ""


def parse_asset_ctx(coin: str, raw: Dict[str, Any], prev_oi: Optional[float] = None) -> AssetCtx:
    imp = raw.get("impactPxs") or [None, None]

    def f(key):
        v = raw.get(key)
        try:
            return float(v) if v is not None and v != "" else None
        except (TypeError, ValueError):
            return None

    bid = ask = None
    if isinstance(imp, (list, tuple)) and len(imp) >= 2:
        try:
            bid = float(imp[0]) if imp[0] is not None else None
            ask = float(imp[1]) if imp[1] is not None else None
        except (TypeError, ValueError):
            pass
    return AssetCtx(
        coin=coin,
        funding=f("funding"),
        open_interest=f("openInterest"),
        premium=f("premium"),
        oracle_px=f("oraclePx"),
        mark_px=f("markPx"),
        mid_px=f("midPx"),
        day_ntl_vlm=f("dayNtlVlm"),
        impact_bid=bid,
        impact_ask=ask,
        prev_open_interest=prev_oi,
    )


def oi_delta_frac(ctx: AssetCtx) -> Optional[float]:
    if ctx.open_interest is None or ctx.prev_open_interest is None:
        return None
    if ctx.prev_open_interest <= 0:
        return None
    return (ctx.open_interest - ctx.prev_open_interest) / ctx.prev_open_interest


def basis_abs(ctx: AssetCtx) -> Optional[float]:
    ref = ctx.mid_px or ctx.mark_px
    if not ctx.oracle_px or not ref or ctx.oracle_px <= 0:
        return None
    return abs(ref - ctx.oracle_px) / ctx.oracle_px


def impact_spread(ctx: AssetCtx) -> Optional[float]:
    mid = ctx.mid_px or ctx.mark_px
    if not mid or mid <= 0 or ctx.impact_bid is None or ctx.impact_ask is None:
        return None
    return (ctx.impact_ask - ctx.impact_bid) / mid


def min_day_ntl_for_coin(coin: str, btc: float, hip3: float, default: float) -> float:
    if coin == "BTC":
        return btc
    if ":" in coin:
        return hip3
    return default


def gate_day_ntl(ctx: AssetCtx, min_ntl: float) -> Optional[str]:
    if min_ntl <= 0:
        return None
    if ctx.day_ntl_vlm is None:
        return None  # unknown: do not block
    if ctx.day_ntl_vlm < min_ntl:
        return f"day_ntl ${ctx.day_ntl_vlm:,.0f} < min ${min_ntl:,.0f}"
    return None


def gate_funding(
    side: str,
    ctx: AssetCtx,
    *,
    enabled: bool,
    long_max: float,
    short_min: float,
) -> Optional[str]:
    if not enabled or ctx.funding is None:
        return None
    side_u = side.upper()
    if side_u == "LONG" and ctx.funding > long_max:
        return f"funding {ctx.funding:.2e} > long_max {long_max:.2e} (longs crowded)"
    if side_u == "SHORT" and ctx.funding < short_min:
        return f"funding {ctx.funding:.2e} < short_min {short_min:.2e} (shorts crowded)"
    return None


def gate_oi_fade(
    side: str,
    setup: str,
    zone: str,
    ctx: AssetCtx,
    *,
    enabled: bool,
    rise_block: float,
) -> Optional[str]:
    if not enabled or setup != "vwap_2sigma_fade":
        return None
    if zone != "upper_band" or side.upper() != "SHORT":
        return None
    d = oi_delta_frac(ctx)
    if d is None:
        return None
    if d >= rise_block:
        return f"oi_rise {d:.4f} >= {rise_block:.4f} into upper_band short fade"
    return None


def gate_microstructure(
    ctx: AssetCtx,
    *,
    basis_enabled: bool,
    max_basis: float,
    impact_enabled: bool,
    max_impact: float,
) -> Optional[str]:
    if basis_enabled:
        b = basis_abs(ctx)
        if b is not None and b > max_basis:
            return f"basis {b:.5f} > max {max_basis:.5f}"
    if impact_enabled:
        s = impact_spread(ctx)
        if s is not None and s > max_impact:
            return f"impact_spread {s:.5f} > max {max_impact:.5f}"
    return None


def fade_allowed(zone: str, fade_mode: str) -> bool:
    mode = (fade_mode or "lower_only").strip().lower()
    if mode in {"off", "none", "disable", "disabled"}:
        return False
    if mode in {"all", "on"}:
        return True
    # lower_only
    return zone == "lower_band"
