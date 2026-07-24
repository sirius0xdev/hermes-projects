# Hybrid VWAP + Order-Flow Bot

Standalone paper-first bot built from the best parts of the existing systems:

- **VWAP/trader**: 24h VWAP, ±2σ bands, day mood (`uptrend/range/downtrend`), trend context, max leverage lookup.
- **orderflow_bot**: Hyperliquid WebSocket trades + L2 book imbalance, rolling CVD, real-time timing.

## Current thesis

Only trade when structure + tape agree:

1. VWAP location/mood says the setup is structurally valid.
2. Order-flow confirms with rolling CVD **level**, short-window **acceleration**, and L2 imbalance.
3. One paper trade per coin (atomic + unique index).
4. Single process only (`flock` + orphan check).

## Setups (post 2026-07-09 cleanup)

| Setup | When |
|-------|------|
| `vwap_2sigma_fade` | At true `upper_band`/`lower_band` with mood allowing fade |
| `trend_pullback` | Uptrend + `lower_half`/`lower_band` **and** mid &lt; 24h VWAP |
| `trend_rally_short` | Downtrend + `upper_half`/`upper_band` only (no chase lower half / weak at_vwap) |

## Frozen paper config

See `data/hybrid.env` (`HYB_SESSION=hybrid-btc-gold-sp500-wti-20260721`):

- Coins: **BTC**, **xyz:GOLD**, **xyz:SP500**, **xyz:CL** (WTI crude; `cash:WTI` has no candles)
- 1% / 1% price stops (1:1), max lev cap 40
- BTC CVD ≥ $800k + accel ≥ $200k / 30s
- GOLD CVD ≥ $200k + accel ≥ $40k / 30s
- SP500/CL (alt) CVD ≥ $150k + accel ≥ $30k / 30s
- Maker first, 20s taker upgrade (live path)

## Run (only this path)

```bash
cd /home/hermes/workspace/orderflow_bot
./scripts/run_hybrid_paper.sh
```

Do **not** start bare `python hybrid_bot.py` (bypasses flock).

## Analyze

```bash
./scripts/hybrid_expectancy.py
```

Expectancy reports **clean** (excludes contaminated/test/dups) and **session** stats separately.

## Go-live bar (enforced in code)

- ≥20 **clean session** closed trades
- WR ≥ 55%
- Net PnL after fee model &gt; 0
- Profit factor ≥ 1.2
- `HYB_DRY_RUN=false` **and** `HYB_ALLOW_LIVE=1` required; silent paper fallback refused
