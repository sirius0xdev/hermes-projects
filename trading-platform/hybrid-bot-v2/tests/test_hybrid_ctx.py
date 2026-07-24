import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_ctx import (
    AssetCtx,
    fade_allowed,
    gate_day_ntl,
    gate_funding,
    gate_microstructure,
    gate_oi_fade,
    min_day_ntl_for_coin,
    parse_asset_ctx,
)


def test_fade_lower_only():
    assert fade_allowed("lower_band", "lower_only")
    assert not fade_allowed("upper_band", "lower_only")
    assert not fade_allowed("lower_band", "off")
    assert fade_allowed("upper_band", "all")


def test_funding_blocks_crowded_long():
    ctx = AssetCtx(coin="BTC", funding=0.0001)
    assert gate_funding("LONG", ctx, enabled=True, long_max=5e-5, short_min=-5e-5)
    assert gate_funding("SHORT", ctx, enabled=True, long_max=5e-5, short_min=-5e-5) is None


def test_funding_blocks_crowded_short():
    ctx = AssetCtx(coin="BTC", funding=-0.0001)
    assert gate_funding("SHORT", ctx, enabled=True, long_max=5e-5, short_min=-5e-5)
    assert gate_funding("LONG", ctx, enabled=True, long_max=5e-5, short_min=-5e-5) is None


def test_funding_disabled_noop():
    ctx = AssetCtx(coin="BTC", funding=0.001)
    assert gate_funding("LONG", ctx, enabled=False, long_max=5e-5, short_min=-5e-5) is None


def test_oi_fade_upper_short():
    ctx = AssetCtx(coin="BTC", open_interest=100, prev_open_interest=99)
    r = gate_oi_fade("SHORT", "vwap_2sigma_fade", "upper_band", ctx, enabled=True, rise_block=0.003)
    assert r is not None


def test_oi_fade_lower_band_not_blocked():
    ctx = AssetCtx(coin="BTC", open_interest=100, prev_open_interest=99)
    assert gate_oi_fade("LONG", "vwap_2sigma_fade", "lower_band", ctx, enabled=True, rise_block=0.003) is None
    # trend setups never blocked by OI gate
    assert gate_oi_fade("SHORT", "trend_rally_short", "upper_band", ctx, enabled=True, rise_block=0.003) is None


def test_oi_no_prev_noop():
    ctx = AssetCtx(coin="BTC", open_interest=100)
    assert gate_oi_fade("SHORT", "vwap_2sigma_fade", "upper_band", ctx, enabled=True, rise_block=0.003) is None


def test_parse_impact():
    ctx = parse_asset_ctx("BTC", {
        "funding": "0.00001",
        "openInterest": "1.5",
        "oraclePx": "100",
        "midPx": "100.2",
        "dayNtlVlm": "1e9",
        "impactPxs": ["99.9", "100.1"],
    })
    assert ctx.funding == 0.00001
    assert ctx.impact_bid == 99.9
    assert ctx.impact_ask == 100.1
    assert ctx.day_ntl_vlm == 1e9


def test_universe_and_dex():
    from hybrid_ctx import universe_name, dex_for_coin
    assert universe_name("xyz:GOLD") == "GOLD"
    assert universe_name("BTC") == "BTC"
    assert dex_for_coin("xyz:GOLD") == "xyz"
    assert dex_for_coin("BTC") == ""


def test_day_ntl_gate():
    ctx = AssetCtx(coin="xyz:CL", day_ntl_vlm=1_000_000)
    assert gate_day_ntl(ctx, 5_000_000) is not None
    assert gate_day_ntl(ctx, 500_000) is None
    assert gate_day_ntl(ctx, 0) is None  # disabled
    ctx_unknown = AssetCtx(coin="BTC")
    assert gate_day_ntl(ctx_unknown, 5_000_000) is None  # unknown: no block


def test_min_day_ntl_for_coin():
    assert min_day_ntl_for_coin("BTC", 5e8, 5e6, 1e7) == 5e8
    assert min_day_ntl_for_coin("xyz:GOLD", 5e8, 5e6, 1e7) == 5e6
    assert min_day_ntl_for_coin("ETH", 5e8, 5e6, 1e7) == 1e7


def test_microstructure_gates():
    wide_basis = AssetCtx(coin="BTC", oracle_px=100.0, mid_px=100.5)
    r = gate_microstructure(wide_basis, basis_enabled=True, max_basis=0.0015,
                            impact_enabled=False, max_impact=0.0008)
    assert r and "basis" in r

    wide_spread = AssetCtx(coin="BTC", mid_px=100.0, impact_bid=99.9, impact_ask=100.2)
    r = gate_microstructure(wide_spread, basis_enabled=False, max_basis=0.0015,
                            impact_enabled=True, max_impact=0.0008)
    assert r and "impact_spread" in r

    tight = AssetCtx(coin="BTC", oracle_px=100.0, mid_px=100.05, impact_bid=99.98, impact_ask=100.02)
    assert gate_microstructure(tight, basis_enabled=True, max_basis=0.0015,
                               impact_enabled=True, max_impact=0.0008) is None
