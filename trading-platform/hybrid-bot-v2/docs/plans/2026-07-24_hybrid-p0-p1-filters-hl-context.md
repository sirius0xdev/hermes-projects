# Hybrid Bot P0/P1 Filters + HL Context Gates — Implementation Plan

> **For Hermes / coding agent:** Implement task-by-task. Prefer `subagent-driven-development` for multi-task runs. Do **not** expand scope into LLM-on-order-path, news auto-entries, or lowering live risk locks without explicit user approval.

**Goal:** Stop the dry-run-proven bleed (upper-band / `vwap_2sigma_fade`, thin HIP-3 alts) and add cheap Hyperliquid context gates (funding, OI Δ, day notional, basis/impact) as **soft vetoes** on the hybrid bot — without inventing new entry alpha.

**Architecture:** Keep hybrid entry = structure (VWAP mood/zone + setup) **AND** order-flow confirm. New HL fields only **block or down-rank** candidates inside `evaluate()` / pre-`maybe_signal`. All knobs env-driven via `data/hybrid.env`. New session tag after deploy so stats stay clean. Live restart only after boot log proves flags + `DRY`/`LIVE` mode intended by env.

**Tech stack:** Python 3.11, `orderflow_bot/hybrid_bot.py`, trader `Scanner`/secrets patterns, Hyperliquid `info` `metaAndAssetCtxs` (+ optional `fundingHistory`), existing Telegram helpers in `trader/telegram_alerts.py`, flock launcher `scripts/run_hybrid_paper.sh`.

**Evidence baseline (2026-07-24, fee-adj hybrid clean book ~n=49):**

| Slice | WR | PF | Note |
|-------|----|----|------|
| All | ~51% | ~1.01 | No robust edge |
| `vwap_2sigma_fade` | ~46% | ~0.80 | Primary drag |
| zone `upper_band` | ~35% | ~0.52 | Toxic |
| `trend_pullback` | ~80% | ~3.84 | Small n — keep |
| `trend_rally_short` | ~56% | ~1.20 | Keep with gates |
| CL multi-asset session | weak | — | Drop from live set |

**Non-goals (YAGNI this pass):**
- Predicted multi-exchange funding arb
- News DB auto entries (blackout-only is a later optional task)
- Rebuilding VWAP trader dry-run
- Changing full-port / max-lev / SL7% TP15% ROE unless user asks
- Restoring readiness bar (live already operator-overridden)

---

## Current live context (do not assume stale)

| Item | Typical path / value |
|------|----------------------|
| Bot code | `/home/hermes/workspace/orderflow_bot/hybrid_bot.py` |
| Env | `/home/hermes/workspace/orderflow_bot/data/hybrid.env` |
| Launcher | `/home/hermes/workspace/orderflow_bot/scripts/run_hybrid_paper.sh` |
| Log | `/tmp/hybrid_vwap_orderflow.log` |
| DB | `/home/hermes/workspace/orderflow_bot/data/hybrid_paper.sqlite` |
| Telegram | `trader/telegram_alerts.py` + secrets `TELEGRAM_*` in `trader/data/bot.sqlite` |
| Session at plan time | `hybrid-live-20260724` (override live) |
| Sizing | `full_port`, port 90%, max lev, max_open=1 |
| SL/TP | 7% / 15% **ROE** → price = ROE/lev |
| Coins now | BTC, xyz:GOLD, xyz:SP500, xyz:CL |

**Safety locks to preserve:**
- `HYB_DRY_RUN` / `HYB_ALLOW_LIVE` dual flag; refuse silent paper when live requested
- Single instance via flock + orphan check
- One open position global (`HYB_MAX_OPEN=1`)
- Telegram live-only by default (`HYB_TELEGRAM_PAPER=0`)
- Never log private keys

---

## Target behavior after this plan

1. **Live coin set default:** `BTC,xyz:GOLD` only (SP500/CL off unless env re-enables).
2. **Fade policy (configurable):**
   - Default A (recommended): **disable** `vwap_2sigma_fade` entirely, **or**
   - Default B: allow fade **only** on `lower_band` (block **all** `upper_band` fades).
3. **Keep** `trend_pullback` and `trend_rally_short` with flow confirms unchanged unless a context gate vetoes.
4. **Context cache** refreshed every N seconds from HL `metaAndAssetCtxs` (main + `xyz` dex):
   - `funding`, `openInterest`, `premium`, `oraclePx`, `markPx`/`midPx`, `impactPxs`, `dayNtlVlm`
5. **Gates (all soft veto → `flow_reject` / `context_reject` style fail log, no entry):**
   - Min `dayNtlVlm` per coin class (BTC vs HIP-3)
   - Funding vs side (fade and optionally trend)
   - OI rising into upper-band short-fade / continuation risk
   - Wide basis or impact spread → skip **maker** entry (taker ok or skip entirely — pick skip-maker-only first)
6. **New paper/live session id** for clean expectancy after deploy.
7. **Boot log + optional Telegram** lists active gates and coin set.
8. **Tests** for pure gate functions (no network).

---

## Design decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where gates run | After setup candidate chosen, before flow confirm **or** after flow — **after structure candidate, before/with flow** | Fail cheap; log clear reason |
| HL fetch | Sync HTTP in metrics loop + TTL cache on `HybridBot` | Avoid per-tick spam; metrics already periodic |
| Dex routing | `metaAndAssetCtxs` with `dex=""` and `dex="xyz"` | HIP-3 coins need xyz |
| Coin name map | `BTC` → main; `xyz:GOLD` → universe name `GOLD` on xyz | Match existing scanner patterns |
| Fade default | Env `HYB_FADE_MODE=lower_only` (values: `off\|lower_only\|all`) | Data says upper_band kill; keep long-band option |
| OI Δ window | Snapshot OI each refresh; Δ = now - prev (same TTL bucket ~60s) | Simple; document not calendar-hour Δ |
| Basis | `abs(mid-oracle)/oracle` | Skip maker if > `HYB_MAX_BASIS` |
| Impact | `(ask_impact - bid_impact)/mid` if two impact px | Skip maker if > threshold |
| Stats | New `HYB_SESSION=hybrid-live-YYYYMMDD-p1` | Session-clean reporting |
| Risk | Do **not** change full_port / lev / ROE stops this PR | Separate concern |

---

## File map

| Path | Action |
|------|--------|
| `orderflow_bot/hybrid_ctx.py` | **Create** — pure functions: parse ctx, funding/OI/basis/impact gates |
| `orderflow_bot/tests/test_hybrid_ctx.py` | **Create** — unit tests |
| `orderflow_bot/hybrid_bot.py` | **Modify** — config, cache refresh, wire gates in `evaluate`/`maybe_signal`, boot log |
| `orderflow_bot/data/hybrid.env` | **Modify** — new knobs + coins + session |
| `orderflow_bot/HYBRID_README.md` | **Modify** — document gates |
| `orderflow_bot/docs/plans/` | Copy of this plan (optional mirror) |
| `trader/telegram_alerts.py` | **Optional** — `send_hybrid_gate` rate-limited (only if easy; else LOG only) |

---

## Env knobs (final set)

```bash
# --- Universe ---
HYB_COINS=BTC,xyz:GOLD
HYB_SESSION=hybrid-live-20260724-p1   # bump on deploy

# --- Fade policy ---
# off | lower_only | all
HYB_FADE_MODE=lower_only

# --- HL context refresh ---
HYB_CTX_REFRESH_SEC=30
HYB_CTX_ENABLED=1

# --- Liquidity floors (USD day notional) ---
HYB_MIN_DAY_NTL_BTC=500000000        # $500M — tune; 0 disables
HYB_MIN_DAY_NTL_HIP3=5000000         # $5M HIP-3 floor
HYB_MIN_DAY_NTL_DEFAULT=10000000

# --- Funding gates (rate as decimal, e.g. 1.25e-5) ---
HYB_FUNDING_GATE=1
# Block LONG if funding > +thr (longs crowded); SHORT if funding < -thr
HYB_FUNDING_LONG_MAX=0.00005
HYB_FUNDING_SHORT_MIN=-0.00005
# If 1, apply funding gate to all setups; if 0, fades only
HYB_FUNDING_GATE_TREND=0

# --- OI gates ---
HYB_OI_GATE=1
# If OI increased by this fraction since last snapshot, block upper_band SHORT fade
HYB_OI_RISE_FADE_BLOCK=0.003         # 0.3% per refresh interval — tune

# --- Microstructure (maker quality) ---
HYB_BASIS_GATE=1
HYB_MAX_BASIS=0.0015                 # 15 bps
HYB_IMPACT_GATE=1
HYB_MAX_IMPACT_SPREAD=0.0008         # 8 bps

# When basis/impact fail: skip_maker | skip_entry
HYB_MICRO_FAIL_MODE=skip_maker
```

---

### Task 1: Add pure context + gate module

**Objective:** Isolatable gate logic with no bot/network imports.

**Files:**
- Create: `/home/hermes/workspace/orderflow_bot/hybrid_ctx.py`
- Create: `/home/hermes/workspace/orderflow_bot/tests/test_hybrid_ctx.py`

**Step 1: Write `hybrid_ctx.py` skeleton**

```python
"""Hyperliquid asset-context helpers and soft entry gates for hybrid_bot."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

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
```

**Step 2: Unit tests**

```python
# tests/test_hybrid_ctx.py
from hybrid_ctx import (
    fade_allowed, gate_funding, gate_oi_fade, gate_day_ntl, parse_asset_ctx,
    gate_microstructure, AssetCtx,
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

def test_oi_fade_upper_short():
    ctx = AssetCtx(coin="BTC", open_interest=100, prev_open_interest=99)
    # delta ~1%
    r = gate_oi_fade("SHORT", "vwap_2sigma_fade", "upper_band", ctx, enabled=True, rise_block=0.003)
    assert r is not None

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
```

**Step 3: Run tests**

```bash
cd /home/hermes/workspace/orderflow_bot
python3 -m pytest tests/test_hybrid_ctx.py -v
# If pytest missing:
python3 -c "from tests.test_hybrid_ctx import *; test_fade_lower_only(); test_funding_blocks_crowded_long(); test_oi_fade_upper_short(); test_parse_impact(); print('OK')"
```

Expected: PASS

**Step 4: Commit** (if git clean policy allows on this repo)

```bash
cd /home/hermes/workspace/orderflow_bot
# or trading-stack mirror if that is the git root
git add hybrid_ctx.py tests/test_hybrid_ctx.py
git commit -m "feat(hybrid): pure HL context gate helpers + unit tests"
```

---

### Task 2: Config fields on `HybridConfig`

**Objective:** All new knobs load from env with safe defaults matching this plan.

**Files:**
- Modify: `/home/hermes/workspace/orderflow_bot/hybrid_bot.py` (`HybridConfig` dataclass)

**Add fields (near other HYB_ knobs):**

```python
fade_mode: str = field(default_factory=lambda: os.getenv("HYB_FADE_MODE", "lower_only").strip().lower() or "lower_only")
ctx_enabled: bool = field(default_factory=lambda: os.getenv("HYB_CTX_ENABLED", "1").strip().lower() in {"1","true","yes"})
ctx_refresh_sec: float = float(os.getenv("HYB_CTX_REFRESH_SEC", "30"))
min_day_ntl_btc: float = float(os.getenv("HYB_MIN_DAY_NTL_BTC", "500000000"))
min_day_ntl_hip3: float = float(os.getenv("HYB_MIN_DAY_NTL_HIP3", "5000000"))
min_day_ntl_default: float = float(os.getenv("HYB_MIN_DAY_NTL_DEFAULT", "10000000"))
funding_gate: bool = field(default_factory=lambda: os.getenv("HYB_FUNDING_GATE", "1").strip().lower() in {"1","true","yes"})
funding_long_max: float = float(os.getenv("HYB_FUNDING_LONG_MAX", "0.00005"))
funding_short_min: float = float(os.getenv("HYB_FUNDING_SHORT_MIN", "-0.00005"))
funding_gate_trend: bool = field(default_factory=lambda: os.getenv("HYB_FUNDING_GATE_TREND", "0").strip().lower() in {"1","true","yes"})
oi_gate: bool = field(default_factory=lambda: os.getenv("HYB_OI_GATE", "1").strip().lower() in {"1","true","yes"})
oi_rise_fade_block: float = float(os.getenv("HYB_OI_RISE_FADE_BLOCK", "0.003"))
basis_gate: bool = field(default_factory=lambda: os.getenv("HYB_BASIS_GATE", "1").strip().lower() in {"1","true","yes"})
max_basis: float = float(os.getenv("HYB_MAX_BASIS", "0.0015"))
impact_gate: bool = field(default_factory=lambda: os.getenv("HYB_IMPACT_GATE", "1").strip().lower() in {"1","true","yes"})
max_impact_spread: float = float(os.getenv("HYB_MAX_IMPACT_SPREAD", "0.0008"))
micro_fail_mode: str = field(default_factory=lambda: os.getenv("HYB_MICRO_FAIL_MODE", "skip_maker").strip().lower() or "skip_maker")
```

**Verify:**

```bash
cd /home/hermes/workspace/orderflow_bot
HYB_FADE_MODE=off python3 -c "from hybrid_bot import HybridConfig; c=HybridConfig(); assert c.fade_mode=='off'; print('ok', c.ctx_enabled)"
```

---

### Task 3: Context cache + refresh on `HybridBot`

**Objective:** Periodic fetch of main + xyz `metaAndAssetCtxs`; store `Dict[str, AssetCtx]`.

**Files:**
- Modify: `hybrid_bot.py` — `HybridBot.__init__`, new methods `_refresh_ctx`, `_ctx_for`

**Implementation sketch:**

```python
import requests
from hybrid_ctx import AssetCtx, parse_asset_ctx, universe_name, dex_for_coin

# in __init__:
self._ctx: Dict[str, AssetCtx] = {}
self._ctx_prev_oi: Dict[str, float] = {}
self._ctx_ts: float = 0.0

def _refresh_ctx(self, force: bool = False) -> None:
    if not self.cfg.ctx_enabled:
        return
    now = time.time()
    if not force and (now - self._ctx_ts) < self.cfg.ctx_refresh_sec:
        return
    base = "https://api.hyperliquid-testnet.xyz" if self.cfg.testnet else "https://api.hyperliquid.xyz"
    # Group coins by dex
    by_dex: Dict[str, List[str]] = {}
    for c in self.cfg.coins:
        by_dex.setdefault(dex_for_coin(c), []).append(c)
    for dex, coins in by_dex.items():
        body = {"type": "metaAndAssetCtxs"}
        if dex:
            body["dex"] = dex
        try:
            r = requests.post(f"{base}/info", json=body, timeout=12)
            r.raise_for_status()
            meta, ctxs = r.json()
            names = [a.get("name") for a in meta.get("universe", [])]
            idx = {n: i for i, n in enumerate(names)}
            for coin in coins:
                uname = universe_name(coin)
                i = idx.get(uname)
                if i is None or i >= len(ctxs):
                    LOG.warning("ctx missing universe name %s for %s", uname, coin)
                    continue
                prev = self._ctx_prev_oi.get(coin)
                raw = ctxs[i] if isinstance(ctxs[i], dict) else {}
                ac = parse_asset_ctx(coin, raw, prev_oi=prev)
                if ac.open_interest is not None:
                    self._ctx_prev_oi[coin] = ac.open_interest
                self._ctx[coin] = ac
        except Exception as e:
            LOG.warning("ctx refresh dex=%r failed: %s", dex, e)
    self._ctx_ts = now
```

**Call sites:**
- Start of `metrics_loop` iteration
- Optionally once at end of `run()` before WS loop
- Light touch in `maybe_signal` via `_refresh_ctx()` (TTL no-ops)

**Verify (manual):**

```bash
cd /home/hermes/workspace/orderflow_bot
python3 - <<'PY'
import os
for line in open('data/hybrid.env'):
    ...
# after implement: construct bot, call _refresh_ctx(force=True), print BTC funding/OI
PY
```

---

### Task 4: Wire fade_mode into `evaluate()`

**Objective:** Stop proposing toxic fades per env.

**Files:**
- Modify: `hybrid_bot.py` `evaluate()` (~lines where `vwap_2sigma_fade` candidates append)

**Current logic (reference):**
```python
if zone == "upper_band" and mood in {"range", "downtrend"}:
    candidates.append(("SHORT", "vwap_2sigma_fade", ...))
if zone == "lower_band" and mood in {"range", "uptrend"}:
    candidates.append(("LONG", "vwap_2sigma_fade", ...))
```

**Replace with:**

```python
from hybrid_ctx import fade_allowed
# ...
if zone in {"upper_band", "lower_band"} and fade_allowed(zone, self.cfg.fade_mode):
    if zone == "upper_band" and mood in {"range", "downtrend"}:
        candidates.append(("SHORT", "vwap_2sigma_fade", "upper 2σ fade allowed by mood+fade_mode"))
    if zone == "lower_band" and mood in {"range", "uptrend"}:
        candidates.append(("LONG", "vwap_2sigma_fade", "lower 2σ fade allowed by mood+fade_mode"))
elif zone in {"upper_band", "lower_band"} and not fade_allowed(zone, self.cfg.fade_mode):
    # optional: don't spam — only note if you would have faded
    pass
```

**Verify:** unit-style by calling `evaluate` is hard (needs state); instead assert `fade_allowed` + log line when a candidate would have been upper fade under `lower_only`.

---

### Task 5: Wire context gates before entry

**Objective:** After structure+flow decide side/setup, apply ctx gates; on micro fail honor `skip_maker` vs `skip_entry`.

**Files:**
- Modify: `hybrid_bot.py` `maybe_signal()` after `evaluate()` returns and flow path already validated — cleanest: **at start of sizing block** once `side, setup, reason` known and mid valid.

**Pseudo:**

```python
self._refresh_ctx()
ctx = self._ctx.get(coin)
zone = (st.trend_context or {}).get("band_zone") or ""
if ctx:
    from hybrid_ctx import (
        gate_day_ntl, gate_funding, gate_oi_fade, gate_microstructure,
        min_day_ntl_for_coin,
    )
    min_ntl = min_day_ntl_for_coin(
        coin, self.cfg.min_day_ntl_btc, self.cfg.min_day_ntl_hip3, self.cfg.min_day_ntl_default
    )
    for reason in (
        gate_day_ntl(ctx, min_ntl),
        gate_oi_fade(side, setup, zone, ctx, enabled=self.cfg.oi_gate, rise_block=self.cfg.oi_rise_fade_block),
    ):
        if reason:
            self._note_fail(coin, st, mid, f"context_reject {reason}")
            return
    apply_funding = self.cfg.funding_gate and (
        setup == "vwap_2sigma_fade" or self.cfg.funding_gate_trend
    )
    if apply_funding:
        fr = gate_funding(side, ctx, enabled=True, long_max=self.cfg.funding_long_max, short_min=self.cfg.funding_short_min)
        if fr:
            self._note_fail(coin, st, mid, f"context_reject {fr}")
            return
    micro = gate_microstructure(
        ctx,
        basis_enabled=self.cfg.basis_gate,
        max_basis=self.cfg.max_basis,
        impact_enabled=self.cfg.impact_gate,
        max_impact=self.cfg.max_impact_spread,
    )
    use_maker = self.cfg.maker_orders
    if micro:
        if self.cfg.micro_fail_mode == "skip_entry":
            self._note_fail(coin, st, mid, f"context_reject {micro}")
            return
        # skip_maker
        use_maker = False
        LOG.info("MICRO %s forcing taker: %s", coin, micro)
else:
    use_maker = self.cfg.maker_orders

# later enter(..., maker=use_maker)
```

**Important:** Thread `use_maker` into `self.executor.enter(..., maker=use_maker)` instead of always `self.cfg.maker_orders`.

**Logging:** `context_reject ...` must show in fail log / gate_events if `_note_fail` already writes DB.

---

### Task 6: Update `hybrid.env` + session + coins

**Objective:** Production flags for deploy.

**Files:**
- Modify: `/home/hermes/workspace/orderflow_bot/data/hybrid.env`

**Required edits:**
```bash
HYB_SESSION=hybrid-live-20260724-p1
HYB_COINS=BTC,xyz:GOLD
HYB_FADE_MODE=lower_only
HYB_CTX_ENABLED=1
HYB_CTX_REFRESH_SEC=30
# ... paste remaining knobs from Env knobs section ...
```

**Preserve existing live locks unless user says otherwise:**
- `HYB_DRY_RUN=false`, `HYB_ALLOW_LIVE=1` if still live
- full_port / port 0.90 / max lev / SL ROE 0.07 / TP ROE 0.15 / telegram on

**If deploying paper-first (recommended once before trusting live):**
```bash
HYB_DRY_RUN=true
HYB_ALLOW_LIVE=0
HYB_SESSION=hybrid-paper-p1-YYYYMMDD
```

---

### Task 7: Boot banner + README

**Objective:** Operator can see gates in first log lines and docs.

**Boot log additions** (extend existing `main()` / `run()` log):
```
fade_mode=lower_only ctx=1 coins=['BTC','xyz:GOLD'] funding_gate=1 oi_gate=1
```

**HYBRID_README.md** section:

```markdown
## Context gates (P1)
- HYB_FADE_MODE: off | lower_only | all
- HL metaAndAssetCtxs: funding, OI Δ, dayNtlVlm, basis, impact
- Failures log as context_reject / force taker on micro
```

---

### Task 8: Deploy procedure (coding agent MUST follow)

**Preflight**
```bash
pgrep -af 'python3 -u hybrid_bot.py' || true
# Note open LIVE positions on exchange — do not flatten without user ask
curl -s https://api.hyperliquid.xyz/info -H 'content-type: application/json' \
  -d '{"type":"metaAndAssetCtxs"}' | head -c 200
```

**If live position open:** finish deploy but **do not** change SL/TP on existing legs unless asked; new gates apply to **new** entries only.

**Restart**
```bash
cd /home/hermes/workspace/orderflow_bot
# stop
kill $(cat data/hybrid.pid) 2>/dev/null || true
pkill -f '[p]ython3 -u hybrid_bot.py' || true
sleep 2
rm -f data/hybrid_paper.lock
# start
bash scripts/run_hybrid_paper.sh   # via Hermes terminal background=true
```

**Verify boot log `/tmp/hybrid_vwap_orderflow.log`:**
- [ ] `dry=False live=True` **or** intentional paper
- [ ] `HYBRID EXECUTOR LIVE mode` if live
- [ ] `fade_mode=lower_only` (or chosen)
- [ ] `coins=['BTC', 'xyz:GOLD']`
- [ ] `sizing=full_port` still
- [ ] `SL/TP=7.0%/15.0%ROE` still
- [ ] No traceback
- [ ] Within 60s: either METRICS lines or explicit ctx warning (not crash)
- [ ] Telegram started alert if `HYB_TELEGRAM=1`

**Functional smoke**
```bash
grep -E 'context_reject|fade_mode|ctx refresh|MICRO|GO-LIVE|LIVE OPEN' /tmp/hybrid_vwap_orderflow.log | tail -40
python3 scripts/hybrid_expectancy.py | head -40
```

---

### Task 9: Optional rate-limited gate Telegram

**Only if Tasks 1–8 done and user still wants alerts.**

- Add `send_hybrid_gate(coin, reason)` in `telegram_alerts.py`
- Hybrid: at most 1 msg / coin / 10 minutes (`self._tg_gate_ts`)
- Default **off**: `HYB_TELEGRAM_GATES=0`

---

### Task 10: Post-deploy observation checklist (human / next agent)

After ≥24h or ≥10 new session closes:

```bash
cd /home/hermes/workspace/orderflow_bot
python3 scripts/hybrid_expectancy.py
sqlite3 data/hybrid_paper.sqlite \
  "SELECT setup, COUNT(*), SUM(pnl_usd>0), ROUND(SUM(pnl_usd),4)
   FROM paper_trades
   WHERE session_id='hybrid-live-20260724-p1' AND status='closed'
     AND IFNULL(contaminated,0)=0
   GROUP BY setup;"
```

**Pass criteria (paper or live session_clean):**
- No new `vwap_2sigma_fade` upper_band shorts if `lower_only`/`off`
- Fade share of losses down vs prior session
- No crash loops; ctx refresh errors &lt; 5% of cycles
- If still PF &lt; 1.1 on core BTC+GOLD trend setups after n≥20 → **do not** scale size; revisit

---

## Out-of-scope follow-ups (separate plans)

1. News blackout from `newsscraper` `latest_summary.json` (`HYB_NEWS_BLACKOUT`)
2. Re-enable VWAP trader dry-run BTC+GOLD playbook
3. Restore hybrid readiness bar (WR≥55%, PF≥1.2) before live
4. Fill reconcile via `userFills` for maker assumed size
5. Widen ROE stops if noise-stop rate high at 40–50x

---

## Risks

| Risk | Mitigation |
|------|------------|
| Gates too tight → zero trades | Log reject reasons; start with `lower_only` not full fade off; funding thresholds loose |
| ctx API fail → stale None | Gates no-op when field missing; don't block all entries on fetch fail |
| HIP-3 name mismatch | Log missing universe; verify GOLD/CL/SP500 names on xyz meta |
| Live full-port still dangerous | max_open=1; BTC+GOLD only; user accepted override |
| Changing env mid-position | Gates only on new entries |

---

## Implementation order (checklist)

- [ ] Task 1: `hybrid_ctx.py` + tests
- [ ] Task 2: config fields
- [ ] Task 3: ctx cache refresh
- [ ] Task 4: fade_mode in evaluate
- [ ] Task 5: gates in maybe_signal + maker maker path
- [ ] Task 6: hybrid.env session/coins/knobs
- [ ] Task 7: boot banner + README
- [ ] Task 8: restart + verify
- [ ] Task 9: optional gate Telegram
- [ ] Task 10: observation notes in session / Telegram summary to user

---

## Coding agent prompt (copy-paste)

```
Implement the plan at:
  /home/hermes/.hermes/plans/2026-07-24_221849-hybrid-p0-p1-filters-hl-context.md
(mirror: workspace/orderflow_bot/docs/plans/ if present)

Work in /home/hermes/workspace/orderflow_bot.
Follow tasks 1→8 in order. Run unit tests before restart.
Prefer paper session first if any doubt about live positions.
Preserve: full_port, max lev, SL 7% TP 15% ROE, HYB_MAX_OPEN=1, telegram live alerts.
Do not print private keys. Do not re-enable xyz:CL/SP500 unless env explicitly set.
After boot, paste verification checklist results.
```

---

## References

- Dry-run expectancy: `orderflow_bot/scripts/hybrid_expectancy.py`
- Hybrid ops skill: `trading-bot-operations`, `trading-bot-monitor-refine` (session_clean only)
- HL info: `metaAndAssetCtxs` fields `funding`, `openInterest`, `premium`, `oraclePx`, `markPx`, `impactPxs`, `dayNtlVlm`
- Prior live override session: `hybrid-live-20260724` (gates were zeroed — do not treat as edge proof)
