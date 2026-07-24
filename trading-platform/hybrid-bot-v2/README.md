# Hybrid Bot v2 — P0/P1 filters + Hyperliquid context gates

New version of `orderflow_bot/hybrid_bot.py` implementing
[docs/plans/2026-07-24_hybrid-p0-p1-filters-hl-context.md](docs/plans/2026-07-24_hybrid-p0-p1-filters-hl-context.md).

**This is a new version — the live v1 bot in `~/workspace/orderflow_bot` is untouched.**

## What changed vs v1

1. **Live coin set default:** `BTC,xyz:GOLD` only (SP500/CL off unless env re-enables).
2. **Fade policy** `HYB_FADE_MODE=off|lower_only|all` (default `lower_only` — blocks all
   `upper_band` fades, the primary loss drag in the clean book).
3. **HL context cache** refreshed every `HYB_CTX_REFRESH_SEC` from `metaAndAssetCtxs`
   (main + `xyz` dex): funding, openInterest, premium, oraclePx, markPx/midPx,
   impactPxs, dayNtlVlm.
4. **Soft-veto gates** (log as `context_reject`, no entry):
   - Min `dayNtlVlm` per coin class (BTC vs HIP-3 vs default)
   - Funding vs side (fades by default; `HYB_FUNDING_GATE_TREND=1` extends to trend)
   - OI rising into `upper_band` short fade
   - Wide basis / impact spread → `HYB_MICRO_FAIL_MODE=skip_maker` (force taker) or `skip_entry`
5. **New session tag** for clean expectancy after deploy.
6. **Boot log** lists active gates + coin set.

Gate logic lives in `hybrid_ctx.py` — pure functions, unit-tested in
`tests/test_hybrid_ctx.py` (no network). Gates no-op when a field is missing,
so a failed ctx refresh never blocks all entries.

## Layout

```
hybrid-bot-v2/
  hybrid_bot.py          # v2 bot (v1 + gates)
  hybrid_ctx.py          # pure context/gate helpers
  tests/test_hybrid_ctx.py
  scripts/run_hybrid_paper.sh   # flock launcher (v2 paths, v2 log)
  scripts/hybrid_expectancy.py
  data/hybrid.env        # env knobs (paper defaults — review before live)
  docs/plans/            # the plan this implements
```

Trader deps (`planner`, `scanners`, `vwap_*`, `telegram_alerts`, secrets DB) resolve
from `/home/hermes/workspace/trader` by default, or set `HYB_TRADER_DIR` / drop the
bot next to a `trader/` checkout.

## Run tests

```bash
cd hybrid-bot-v2
python3 -m pytest tests/test_hybrid_ctx.py -v
```

## Run paper (dry-run)

```bash
bash scripts/run_hybrid_paper.sh
# log: /tmp/hybrid_vwap_orderflow_v2.log
```

Boot checklist: `dry=True` · `fade_mode=lower_only` · `coins=['BTC', 'xyz:GOLD']` ·
`v2 gates:` line present · no traceback · METRICS lines within 60s.

## Env knobs

See `data/hybrid.env` for the full set with defaults. Safety locks preserved from v1:
`HYB_DRY_RUN`/`HYB_ALLOW_LIVE` dual flag, flock single instance, `HYB_MAX_OPEN=1`,
Telegram live-only by default, no private keys in logs.
