#!/usr/bin/env python3
"""Hybrid VWAP + order-flow bot (paper-first).

Best parts combined:
- VWAP bot: 24h VWAP ±2σ location, day mood, trend/range context.
- Order-flow bot: real-time Hyperliquid WS trades + L2 book imbalance for timing/veto.

Default is paper-only. Live execution is intentionally disabled unless HYB_ALLOW_LIVE=1
and HYB_DRY_RUN=false are both set; validate paper edge first.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

import websockets

try:
    import orjson

    def _loads(b):
        return orjson.loads(b)

    def _dumps(obj):
        return orjson.dumps(obj).decode()
except ImportError:

    def _loads(b):
        return json.loads(b)

    def _dumps(obj):
        return json.dumps(obj)

# Live-only SDK helpers (imported lazily-guarded; only used when executor.is_live).
try:
    from hyperliquid.exchange import _get_dex  # type: ignore
    from hyperliquid.utils import constants as hl_constants  # type: ignore
except Exception:  # pragma: no cover - SDK optional unless trading live
    _get_dex = None
    hl_constants = None

ROOT = Path(__file__).resolve().parent
# Trader deps (planner/scanners/vwap_*/telegram_alerts/secrets DB). Prefer the live
# workspace trader dir; fall back to the repo copy when running from a checkout.
_TRADER_CANDIDATES = [
    Path(os.getenv("HYB_TRADER_DIR", "")).expanduser() if os.getenv("HYB_TRADER_DIR") else None,
    Path("/home/hermes/workspace/trader"),
    ROOT.parent / "trader",
]
TRADER = next((p for p in _TRADER_CANDIDATES if p is not None and (p / "scanners.py").exists()), ROOT.parent / "trader")
sys.path.insert(0, str(TRADER))
sys.path.insert(0, str(ROOT))

# Optional Telegram alerts (trader/telegram_alerts.py + secrets DB).
try:
    import telegram_alerts as _tg  # noqa: E402
except Exception:  # pragma: no cover
    _tg = None

# Load live credentials from env first, then the trader secrets DB (same source as orderflow_bot).
TRADER_SECRETS_DB = TRADER / "data" / "bot.sqlite"


def _hyb_secret(key: str, default: str = "") -> str:
    v = os.getenv(key, "").strip()
    if v:
        return v
    if TRADER_SECRETS_DB.is_file():
        try:
            conn = sqlite3.connect(str(TRADER_SECRETS_DB))
            row = conn.execute("SELECT value FROM secrets WHERE key=?", (key,)).fetchone()
            conn.close()
            if row and row[0]:
                return str(row[0]).strip()
        except Exception:
            pass
    return default


def _dex_for_coin(coin: str) -> List[str]:
    """HIP-3 DEX suffix (e.g. 'xyz') must be passed to the SDK so the right perp is targeted."""
    if ":" in coin:
        dex = coin.split(":", 1)[0]
        return ["", dex]
    return [""]


def _perp_dexs_for_coins(coins: List[str]) -> List[str]:
    """Union of mainnet '' + all HIP-3 DEX prefixes needed for the coin set."""
    dexs: List[str] = [""]
    for c in coins:
        if ":" in c:
            d = c.split(":", 1)[0]
            if d and d not in dexs:
                dexs.append(d)
    return dexs
from planner import MarketContext, OrderFlowSnapshot, VolumeSnapshot
from scanners import Scanner
from vwap_day_mood import band_zone, mood_context
from vwap_trend_context import compute_session_trend

# v2: pure HL context gates (plan: docs/plans/2026-07-24_hybrid-p0-p1-filters-hl-context.md)
try:
    from hybrid_ctx import (
        AssetCtx,
        dex_for_coin,
        fade_allowed,
        gate_day_ntl,
        gate_funding,
        gate_microstructure,
        gate_oi_fade,
        min_day_ntl_for_coin,
        parse_asset_ctx,
        universe_name,
    )
except Exception:  # pragma: no cover - gates disabled if module missing
    AssetCtx = None  # type: ignore
    dex_for_coin = universe_name = parse_asset_ctx = None  # type: ignore
    gate_day_ntl = gate_funding = gate_microstructure = gate_oi_fade = None  # type: ignore
    min_day_ntl_for_coin = None  # type: ignore
    fade_allowed = None  # type: ignore

LOG = logging.getLogger("hybrid_bot")
DB_PATH = ROOT / "data" / "hybrid_paper.sqlite"


def _extract_oid(res: Any) -> Optional[int]:
    """Pull an order id from a Hyperliquid SDK order response (shape varies by SDK)."""
    if not isinstance(res, dict):
        return None
    # Common shapes: {"status":"ok","response":{"data":{"statuses":[{"filled":{...}},
    #   {"resting":{"oid":N}}, ...]}}}  or {"oid": N}
    if "oid" in res and isinstance(res.get("oid"), int):
        return res["oid"]
    resp = res.get("response", {})
    data = resp.get("data", {}) if isinstance(resp, dict) else {}
    statuses = data.get("statuses") if isinstance(data, dict) else None
    if isinstance(statuses, list):
        for s in statuses:
            if isinstance(s, dict) and "resting" in s and "oid" in s["resting"]:
                return int(s["resting"]["oid"])
    return None


@dataclass
class Trade:
    coin: str
    side: str
    px: float
    sz: float
    time_ms: int


@dataclass
class BookLevel:
    px: float
    sz: float


@dataclass
class OrderBook:
    bids: List[BookLevel] = field(default_factory=list)
    asks: List[BookLevel] = field(default_factory=list)
    last_update: float = 0.0

    def update_from_hl(self, data: Dict[str, Any]) -> None:
        bids: List[BookLevel] = []
        asks: List[BookLevel] = []
        if "levels" in data and isinstance(data["levels"], list) and len(data["levels"]) >= 2:
            for level in data["levels"][0]:
                if isinstance(level, dict):
                    bids.append(BookLevel(float(level["px"]), float(level["sz"])))
            for level in data["levels"][1]:
                if isinstance(level, dict):
                    asks.append(BookLevel(float(level["px"]), float(level["sz"])))
        bids.sort(key=lambda x: -x.px)
        asks.sort(key=lambda x: x.px)
        self.bids = bids
        self.asks = asks
        self.last_update = time.time()

    def weighted_mid(self) -> float:
        if not self.bids or not self.asks:
            return 0.0
        bb, ba = self.bids[0], self.asks[0]
        if bb.sz + ba.sz < 1e-12:
            return (bb.px + ba.px) / 2
        return (bb.px * ba.sz + ba.px * bb.sz) / (bb.sz + ba.sz)

    def imbalance_ratio(self, levels: int) -> float:
        bid_vol = sum(l.sz for l in self.bids[:levels])
        ask_vol = sum(l.sz for l in self.asks[:levels])
        if ask_vol < 1e-12:
            return 99.0
        return bid_vol / ask_vol


class FlowState:
    def __init__(self, cvd_window_seconds: int, cvd_max_trades: int):
        self.cvd_window_seconds = cvd_window_seconds
        self.cvd_usd = 0.0
        self._last_cvd = 0.0
        self._deltas: Deque[Tuple[float, float]] = deque(maxlen=cvd_max_trades)

    def on_trade(self, trade: Trade) -> None:
        notional = trade.px * trade.sz
        side = trade.side.upper()
        delta = notional if side in {"B", "BUY", "BID"} else -notional
        # Prefer exchange trade time; fall back to wall clock if missing/stale.
        ts = trade.time_ms / 1000.0 if trade.time_ms else time.time()
        if ts <= 0:
            ts = time.time()
        self._deltas.append((ts, delta))
        self.cvd_usd += delta

    def rolling_cvd(self) -> float:
        cutoff = time.time() - self.cvd_window_seconds
        return sum(d for ts, d in self._deltas if ts >= cutoff)

    def cvd_window(self, seconds: float) -> float:
        """Sum of signed notional over the last `seconds` (acceleration proxy)."""
        cutoff = time.time() - max(1.0, float(seconds))
        return sum(d for ts, d in self._deltas if ts >= cutoff)

    def snapshot(self) -> None:
        self._last_cvd = self.cvd_usd


@dataclass
class HybridConfig:
    coins: List[str] = field(
        default_factory=lambda: [
            c.strip()
            for c in os.getenv("HYB_COINS", "BTC,xyz:GOLD").split(",")
            if c.strip()
        ]
    )
    dry_run: bool = field(default_factory=lambda: os.getenv("HYB_DRY_RUN", "true").strip().lower() in {"1", "true", "yes"})
    allow_live: bool = field(default_factory=lambda: os.getenv("HYB_ALLOW_LIVE", "0").strip().lower() in {"1", "true", "yes"})
    testnet: bool = field(default_factory=lambda: os.getenv("HYB_TESTNET", "false").strip().lower() in {"1", "true", "yes"})
    account_address: str = field(default_factory=lambda: _hyb_secret("HL_ADDRESS", os.getenv("HL_ACCOUNT_ADDRESS", "")))
    private_key: str = field(default_factory=lambda: _hyb_secret("HL_PRIVATE_KEY", os.getenv("HL_API_KEY", "")))
    # Paper session tag — readiness/expectancy can filter to this session only.
    session_id: str = field(
        default_factory=lambda: os.getenv("HYB_SESSION", "hybrid-btc-gold-sp500-wti-20260721").strip()
        or "hybrid-btc-gold-sp500-wti-20260721"
    )
    cvd_window_seconds: int = int(os.getenv("HYB_CVD_WINDOW_SEC", "120"))
    cvd_max_trades: int = int(os.getenv("HYB_CVD_MAX_TRADES", "4000"))
    # Recent-flow acceleration windows (shorter than full CVD window).
    cvd_accel_seconds: int = int(os.getenv("HYB_CVD_ACCEL_SEC", "30"))
    cvd_accel_usd: float = float(os.getenv("HYB_CVD_ACCEL_USD", "200000"))
    cvd_accel_gold_usd: float = float(os.getenv("HYB_CVD_ACCEL_GOLD_USD", "40000"))
    cvd_accel_alt_usd: float = float(os.getenv("HYB_CVD_ACCEL_ALT_USD", "30000"))
    imbalance_levels: int = int(os.getenv("HYB_IMB_LEVELS", "5"))
    imb_long: float = float(os.getenv("HYB_IMB_LONG", "1.35"))
    imb_short: float = float(os.getenv("HYB_IMB_SHORT", "0.74"))
    imb_max: float = float(os.getenv("HYB_IMB_MAX", "4.5"))
    cvd_confirm_usd: float = float(os.getenv("HYB_CVD_CONFIRM_USD", "800000"))
    cvd_confirm_gold_usd: float = float(os.getenv("HYB_CVD_CONFIRM_GOLD_USD", "200000"))
    # HIP-3 / cash alts (SP500, WTI, …) — thinner tape than BTC
    cvd_confirm_alt_usd: float = float(os.getenv("HYB_CVD_CONFIRM_ALT_USD", "150000"))
    signal_confirm: int = int(os.getenv("HYB_SIGNAL_CONFIRM", "2"))
    # Min wall-clock gap between confirm samples (prevents same-tick multi-fires).
    confirm_gap_ms: int = int(os.getenv("HYB_CONFIRM_GAP_MS", "400"))
    cooldown_seconds: int = int(os.getenv("HYB_COOLDOWN_SEC", "300"))
    max_position_usd: float = float(os.getenv("HYB_MAX_POSITION_USD", "0"))  # 0 = no hard notional cap
    risk_pct: float = float(os.getenv("HYB_RISK_PCT", "0.05"))
    # full_port: notional = equity * port_fraction * lev (user default / locked preference)
    # risk:       notional = equity * risk_pct / sl_price_pct  (fixed $ risk at price stop)
    sizing_mode: str = field(
        default_factory=lambda: os.getenv("HYB_SIZING_MODE", "full_port").strip().lower() or "full_port"
    )
    port_fraction: float = float(os.getenv("HYB_PORT_FRACTION", "0.90"))
    # Cap concurrent opens (full-port needs 1 — multi-coin full port over-margins a small book).
    max_open_positions: int = int(os.getenv("HYB_MAX_OPEN", "1"))
    max_leverage_cap: int = int(os.getenv("HYB_MAX_LEVERAGE", "50"))
    # Use MAX leverage by default (user: tiny account, maker fees dwarf ROE otherwise).
    use_max_leverage: bool = field(default_factory=lambda: os.getenv("HYB_USE_MAX_LEV", "1").strip().lower() in {"1", "true", "yes"})
    maker_orders: bool = field(default_factory=lambda: os.getenv("HYB_MAKER", "1").strip().lower() in {"1", "true", "yes"})
    maker_fill_timeout_seconds: float = float(os.getenv("HYB_MAKER_FILL_TIMEOUT", "20"))
    sl_roe: float = float(os.getenv("HYB_SL_ROE", "0.07"))
    tp_roe: float = float(os.getenv("HYB_TP_ROE", "0.07"))
    sl_price_pct: float = float(os.getenv("HYB_SL_PRICE_PCT", "0.01"))
    tp_price_pct: float = float(os.getenv("HYB_TP_PRICE_PCT", "0.01"))
    no_sl: bool = field(default_factory=lambda: os.getenv("HYB_NO_SL", "0").strip().lower() in {"1", "true", "yes"})
    fee_bps_rt: float = float(os.getenv("HYB_FEE_BPS_RT", "2.0"))
    min_profit_factor: float = float(os.getenv("HYB_MIN_PF", "1.2"))
    min_closed_trades: int = int(os.getenv("HYB_MIN_CLOSED_TRADES", "20"))
    min_win_rate: float = float(os.getenv("HYB_MIN_WIN_RATE", "0.55"))
    readiness_session_only: bool = field(
        default_factory=lambda: os.getenv("HYB_READINESS_SESSION_ONLY", "1").strip().lower() in {"1", "true", "yes"}
    )
    vwap_refresh_seconds: int = int(os.getenv("HYB_VWAP_REFRESH_SEC", "60"))
    metrics_seconds: int = int(os.getenv("HYB_METRICS_SEC", "30"))
    equity_fallback: float = float(os.getenv("HYB_EQUITY_FALLBACK", "41.0"))
    fail_log_seconds: float = float(os.getenv("HYB_FAIL_LOG_SEC", "60"))
    log_level: str = os.getenv("HYB_LOG_LEVEL", "INFO")
    # Telegram: uses trader secrets TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
    telegram_enabled: bool = field(
        default_factory=lambda: os.getenv("HYB_TELEGRAM", "1").strip().lower() in {"1", "true", "yes"}
    )
    telegram_paper: bool = field(
        default_factory=lambda: os.getenv("HYB_TELEGRAM_PAPER", "0").strip().lower() in {"1", "true", "yes"}
    )

    # --- v2: fade policy (off | lower_only | all) ---
    fade_mode: str = field(
        default_factory=lambda: os.getenv("HYB_FADE_MODE", "lower_only").strip().lower() or "lower_only"
    )
    # --- v2: HL context cache + gates ---
    ctx_enabled: bool = field(
        default_factory=lambda: os.getenv("HYB_CTX_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
    )
    ctx_refresh_sec: float = float(os.getenv("HYB_CTX_REFRESH_SEC", "30"))
    min_day_ntl_btc: float = float(os.getenv("HYB_MIN_DAY_NTL_BTC", "500000000"))
    min_day_ntl_hip3: float = float(os.getenv("HYB_MIN_DAY_NTL_HIP3", "5000000"))
    min_day_ntl_default: float = float(os.getenv("HYB_MIN_DAY_NTL_DEFAULT", "10000000"))
    funding_gate: bool = field(
        default_factory=lambda: os.getenv("HYB_FUNDING_GATE", "1").strip().lower() in {"1", "true", "yes"}
    )
    funding_long_max: float = float(os.getenv("HYB_FUNDING_LONG_MAX", "0.00005"))
    funding_short_min: float = float(os.getenv("HYB_FUNDING_SHORT_MIN", "-0.00005"))
    funding_gate_trend: bool = field(
        default_factory=lambda: os.getenv("HYB_FUNDING_GATE_TREND", "0").strip().lower() in {"1", "true", "yes"}
    )
    oi_gate: bool = field(
        default_factory=lambda: os.getenv("HYB_OI_GATE", "1").strip().lower() in {"1", "true", "yes"}
    )
    oi_rise_fade_block: float = float(os.getenv("HYB_OI_RISE_FADE_BLOCK", "0.003"))
    basis_gate: bool = field(
        default_factory=lambda: os.getenv("HYB_BASIS_GATE", "1").strip().lower() in {"1", "true", "yes"}
    )
    max_basis: float = float(os.getenv("HYB_MAX_BASIS", "0.0015"))
    impact_gate: bool = field(
        default_factory=lambda: os.getenv("HYB_IMPACT_GATE", "1").strip().lower() in {"1", "true", "yes"}
    )
    max_impact_spread: float = float(os.getenv("HYB_MAX_IMPACT_SPREAD", "0.0008"))
    # skip_maker | skip_entry — what to do when basis/impact gates fail
    micro_fail_mode: str = field(
        default_factory=lambda: os.getenv("HYB_MICRO_FAIL_MODE", "skip_maker").strip().lower() or "skip_maker"
    )

    @property
    def ws_url(self) -> str:
        override = os.getenv("HYB_WS_URL", "").strip()
        if override:
            return override
        return "wss://api.hyperliquid-testnet.xyz/ws" if self.testnet else "wss://api.hyperliquid.xyz/ws"


class HybridExecutor:
    """SDK-backed executor for live entries + exchange-native SL/TP (live only).

    Reuses the official Hyperliquid SDK exactly like orderflow_bot/main.py.
    In paper mode every method short-circuits to a no-op-shaped dict so the
    caller logic is identical for paper and live. Live requires
    HYB_DRY_RUN=false AND HYB_ALLOW_LIVE=1 (enforced in HybridBot.run).
    """

    def __init__(self, cfg: HybridConfig):
        self.cfg = cfg
        self.exchange = None
        self.info = None
        self._live = (not cfg.dry_run) and cfg.allow_live and bool(cfg.private_key)
        if self._live:
            try:
                from eth_account import Account
                from hyperliquid.exchange import Exchange
                from hyperliquid.info import Info
                from hyperliquid.utils import constants as hl_constants

                acct = Account.from_key(cfg.private_key)
                base = hl_constants.TESTNET_API_URL if cfg.testnet else hl_constants.MAINNET_API_URL
                perp_dexs = _perp_dexs_for_coins(cfg.coins) if cfg.coins else [""]
                self.info = Info(base, skip_ws=True, perp_dexs=perp_dexs)
                self.exchange = Exchange(
                    acct,
                    base_url=base,
                    account_address=cfg.account_address or acct.address,
                    perp_dexs=perp_dexs,
                )
                LOG.info("HYBRID EXECUTOR LIVE mode (testnet=%s, dex=%s)", cfg.testnet, perp_dexs)
            except Exception as e:
                LOG.error("HYBRID EXECUTOR init failed, forcing paper: %s", e)
                self._live = False
                self.exchange = None
                self.info = None
        else:
            LOG.info("HYBRID EXECUTOR paper mode (live=%s)", self._live)

    @property
    def is_live(self) -> bool:
        return self._live

    def equity_usd(self) -> float:
        """Account equity for sizing.

        Unified accounts often report clearinghouse accountValue=0 while
        collateral sits in spot USDC / availableToTrade. Fall through those
        sources before equity_fallback so live sizing is not zeroed.
        """
        addr = self.cfg.account_address
        if self.info and addr:
            # 1) Classic perp margin summary
            try:
                st = self.info.user_state(addr)
                margin = st.get("marginSummary", {}) if isinstance(st, dict) else {}
                av = float(margin.get("accountValue", 0) or 0)
                if av > 0:
                    return av
            except Exception as e:
                LOG.warning("equity user_state failed: %s", e)
            # 2) Unified: activeAssetData.availableToTrade (BTC as probe)
            try:
                import requests

                base = (
                    "https://api.hyperliquid-testnet.xyz"
                    if self.cfg.testnet
                    else "https://api.hyperliquid.xyz"
                )
                r = requests.post(
                    f"{base}/info",
                    json={"type": "activeAssetData", "user": addr, "coin": "BTC"},
                    timeout=10,
                )
                if r.ok:
                    raw = r.json()
                    data = raw if isinstance(raw, dict) else {}
                    avail = data.get("availableToTrade") or [0, 0]
                    if isinstance(avail, (list, tuple)) and avail:
                        v = float(avail[0] or 0)
                        if v > 0:
                            return v
            except Exception as e:
                LOG.warning("equity activeAssetData failed: %s", e)
            # 3) Spot USDC balance (unified collateral)
            try:
                spot = self.info.spot_user_state(addr)
                for b in spot.get("balances") or []:
                    if str(b.get("coin", "")).upper() == "USDC":
                        v = float(b.get("total") or 0)
                        if v > 0:
                            return v
            except Exception as e:
                LOG.warning("equity spot_user_state failed: %s", e)
        fb = float(self.cfg.equity_fallback)
        LOG.warning("equity fell back to HYB_EQUITY_FALLBACK=%.4f", fb)
        return fb

    def open_orders(self, coin: str) -> list:
        """Return the account's open orders for `coin` (used to detect unfilled makers)."""
        if not self.info or not self.cfg.account_address:
            return []
        try:
            return list(self.info.open_orders(self.cfg.account_address, _get_dex(coin)) or [])
        except Exception as e:
            LOG.warning("open_orders failed %s: %s", coin, e)
            return []

    def cancel(self, coin: str, oid: int) -> dict:
        """Cancel a resting order by oid (used to upgrade timed-out maker entries)."""
        if not self._live or not self.exchange:
            return {"status": "dry_run", "coin": coin, "oid": oid}
        try:
            res = self.exchange.cancel(coin, oid)
            LOG.info("LIVE CANCEL %s oid=%s -> %s", coin, oid, res)
            return res
        except Exception as e:
            LOG.error("LIVE CANCEL FAILED %s oid=%s: %s", coin, oid, e)
            return {"status": "error", "error": str(e)}

    def _live_sz(self, coin: str, size_usd: float, px: float) -> float:
        """Convert a USD notional into base-asset size, using the asset's sz decimals."""
        if not self.info or px <= 0:
            return round(size_usd / px, 6) if px > 0 else 0.0
        try:
            meta = self.info.meta()
            for m in meta.get("universe", []):
                if m.get("name") == coin:
                    dec = m.get("szDecimals", 6)
                    return round(size_usd / px, dec)
        except Exception:
            pass
        return round(size_usd / px, 6) if px > 0 else 0.0

    def enter(self, coin: str, is_buy: bool, size_usd: float, px: float, lev: int, maker: bool = False) -> dict:
        """Entry order. Marketable IOC (taker) by default, or a passive post-only maker
        limit when `maker=True` (pays ~0.01% instead of ~0.035%, often a rebate)."""
        if not self._live or not self.exchange:
            return {"status": "dry_run", "coin": coin, "is_buy": is_buy, "size_usd": size_usd, "px": px, "maker": maker}
        try:
            self.exchange.update_leverage(lev, coin, is_cross=True)
        except Exception as e:
            LOG.warning("leverage update %s: %s", coin, e)
        sz = self._live_sz(coin, size_usd, px)
        if maker:
            # Passive maker: post at the reference price, fill only if price comes to us.
            limit_px = round(px, 6)
            order_type = {"limit": {"tif": "Gtc", "postOnly": True}}
        else:
            limit_px = px * (1.0005 if is_buy else 0.9995)
            order_type = {"limit": {"tif": "Ioc"}}
        try:
            res = self.exchange.order(coin, is_buy, sz, limit_px, order_type=order_type, reduce_only=False)
            LOG.info("LIVE ENTER (maker=%s) %s %s sz=%s px=%.4f -> %s", maker, coin, "BUY" if is_buy else "SELL", sz, limit_px, res)
            return res
        except Exception as e:
            LOG.error("LIVE ENTER FAILED %s %s: %s", coin, "BUY" if is_buy else "SELL", e)
            return {"status": "error", "error": str(e)}

    def attach_tpsl(self, coin: str, is_long: bool, sl_px: float, tp_px: float) -> dict:
        """Place exchange-native stop-loss + take-profit trigger orders (reduce-only)."""
        if not self._live or not self.exchange:
            return {"status": "dry_run", "sl": sl_px, "tp": tp_px}
        is_buy = not is_long  # TP/SL that close a long are sells
        try:
            sl = self.exchange.order(
                coin, is_buy, 0, sl_px,
                order_type={"trigger": {"triggerPx": sl_px, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True,
            )
            tp = self.exchange.order(
                coin, not is_buy, 0, tp_px,
                order_type={"trigger": {"triggerPx": tp_px, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True,
            )
            LOG.info("LIVE TPSL %s sl=%s tp=%s", coin, sl, tp)
            return {"sl": sl, "tp": tp}
        except Exception as e:
            LOG.error("LIVE TPSL FAILED %s: %s", coin, e)
            return {"status": "error", "error": str(e)}

    def attach_tp_only(self, coin: str, is_long: bool, tp_px: float) -> dict:
        """Place only the take-profit trigger order (used when the hard stop is disabled)."""
        if not self._live or not self.exchange:
            return {"status": "dry_run", "tp": tp_px}
        is_buy = not is_long
        try:
            tp = self.exchange.order(
                coin, is_buy, 0, tp_px,
                order_type={"trigger": {"triggerPx": tp_px, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True,
            )
            LOG.info("LIVE TP-ONLY %s tp=%s (no SL)", coin, tp)
            return {"tp": tp}
        except Exception as e:
            LOG.error("LIVE TP-ONLY FAILED %s: %s", coin, e)
            return {"status": "error", "error": str(e)}

    def exit(self, coin: str, is_long: bool, px: float) -> dict:
        """Marketable limit close of the full position (used if we must exit programmatically)."""
        if not self._live or not self.exchange:
            return {"status": "dry_run", "coin": coin, "px": px}
        is_buy = not is_long
        try:
            res = self.exchange.order(
                coin, is_buy, 0, px * (1.0005 if is_buy else 0.9995),
                order_type={"limit": {"tif": "Ioc"}}, reduce_only=True,
            )
            LOG.info("LIVE EXIT %s px=%.4f -> %s", coin, px, res)
            return res
        except Exception as e:
            LOG.error("LIVE EXIT FAILED %s: %s", coin, e)
            return {"status": "error", "error": str(e)}


@dataclass
class CoinState:
    flow: FlowState
    book: OrderBook = field(default_factory=OrderBook)
    # (side, setup, sample_ts) for spaced multi-tick confirmation
    signal_hist: Deque[Tuple[str, str, float]] = field(default_factory=lambda: deque(maxlen=16))
    last_signal_ts: float = 0.0
    last_vwap_refresh: float = 0.0
    last_fail_log_ts: float = 0.0
    last_fail_reason: str = ""
    bands: Dict[str, float] = field(default_factory=dict)
    ib: Dict[str, float] = field(default_factory=dict)
    volume: Optional[VolumeSnapshot] = None
    trend_context: Dict[str, Any] = field(default_factory=dict)
    trade_count: int = 0


class HybridStore:
    def __init__(self, path: Path = DB_PATH, session_id: str = "default"):
        self.path = path
        self.session_id = session_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()
        self.sanitize_open_duplicates()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    coin TEXT NOT NULL,
                    mid REAL,
                    vwap REAL,
                    upper_trade REAL,
                    lower_trade REAL,
                    zone TEXT,
                    mood TEXT,
                    rolling_cvd REAL,
                    imb REAL,
                    trade_count INTEGER
                );
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    coin TEXT NOT NULL,
                    side TEXT NOT NULL,
                    setup TEXT,
                    mid REAL,
                    vwap REAL,
                    upper_trade REAL,
                    lower_trade REAL,
                    zone TEXT,
                    mood TEXT,
                    rolling_cvd REAL,
                    imb REAL,
                    reason TEXT
                );
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    coin TEXT NOT NULL,
                    side TEXT NOT NULL,
                    setup TEXT,
                    entry REAL,
                    size_usd REAL,
                    leverage REAL,
                    sl_price REAL,
                    tp_price REAL,
                    status TEXT,
                    exit_ts REAL,
                    exit_price REAL,
                    exit_reason TEXT,
                    pnl_usd REAL,
                    pnl_roe REAL,
                    reason TEXT,
                    live INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS gate_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    coin TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    mid REAL,
                    mood TEXT,
                    zone TEXT,
                    rolling_cvd REAL,
                    imb REAL
                );
                CREATE INDEX IF NOT EXISTS idx_hyb_metrics_ts ON metrics(ts);
                CREATE INDEX IF NOT EXISTS idx_hyb_signals_ts ON signals(ts);
                CREATE INDEX IF NOT EXISTS idx_hyb_trades_status ON paper_trades(status);
                CREATE INDEX IF NOT EXISTS idx_hyb_gate_ts ON gate_events(ts);
                """
            )
            for col_sql in (
                "ALTER TABLE paper_trades ADD COLUMN live INTEGER DEFAULT 0",
                "ALTER TABLE paper_trades ADD COLUMN session_id TEXT DEFAULT ''",
                "ALTER TABLE paper_trades ADD COLUMN contaminated INTEGER DEFAULT 0",
                "ALTER TABLE signals ADD COLUMN session_id TEXT DEFAULT ''",
            ):
                try:
                    conn.execute(col_sql)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
            try:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_hyb_one_open_per_coin "
                    "ON paper_trades(coin) WHERE status='open'"
                )
                conn.commit()
            except sqlite3.OperationalError as e:
                LOG.warning("unique open index deferred (will sanitize first): %s", e)
            conn.commit()
        finally:
            conn.close()

    def sanitize_open_duplicates(self) -> int:
        """Keep earliest open per coin; mark rest contaminated+closed (multi-instance cleanup)."""
        conn = self._conn()
        closed = 0
        try:
            conn.execute("BEGIN IMMEDIATE")
            coins = [
                r[0]
                for r in conn.execute(
                    "SELECT coin FROM paper_trades WHERE status='open' GROUP BY coin HAVING COUNT(*) > 1"
                ).fetchall()
            ]
            now = time.time()
            for coin in coins:
                rows = conn.execute(
                    "SELECT id FROM paper_trades WHERE coin=? AND status='open' ORDER BY id ASC",
                    (coin,),
                ).fetchall()
                for r in rows[1:]:
                    conn.execute(
                        """
                        UPDATE paper_trades
                        SET status='closed', exit_ts=?, exit_price=entry, exit_reason='contaminated_dup',
                            pnl_usd=0, pnl_roe=0, contaminated=1
                        WHERE id=?
                        """,
                        (now, r[0]),
                    )
                    closed += 1
            conn.execute(
                "UPDATE paper_trades SET contaminated=1 WHERE setup='test' AND IFNULL(contaminated,0)=0"
            )
            dups = conn.execute(
                """
                SELECT a.id
                FROM paper_trades a
                JOIN paper_trades b
                  ON a.coin=b.coin AND a.side=b.side AND IFNULL(a.setup,'')=IFNULL(b.setup,'')
                 AND a.id > b.id
                 AND abs(a.ts - b.ts) < 2.0
                WHERE IFNULL(a.contaminated,0)=0
                """
            ).fetchall()
            for r in dups:
                conn.execute("UPDATE paper_trades SET contaminated=1 WHERE id=?", (r[0],))
            conn.commit()
            try:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_hyb_one_open_per_coin "
                    "ON paper_trades(coin) WHERE status='open'"
                )
                conn.commit()
            except sqlite3.OperationalError as e:
                LOG.warning("unique open index still blocked: %s", e)
            if closed:
                LOG.warning("sanitized %d duplicate open trades (contaminated_dup)", closed)
        finally:
            conn.close()
        return closed

    def record_metrics(self, coin: str, st: CoinState) -> None:
        mid = st.book.weighted_mid()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO metrics(ts,coin,mid,vwap,upper_trade,lower_trade,zone,mood,rolling_cvd,imb,trade_count)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    time.time(), coin, mid, st.bands.get("mid"), _upper(st.bands), _lower(st.bands),
                    st.trend_context.get("band_zone"), st.trend_context.get("day_mood"),
                    st.flow.rolling_cvd(), safe_imb(st.book, 5), st.trade_count,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def record_gate(self, coin: str, reason: str, st: CoinState, mid: float) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO gate_events(ts,coin,reason,mid,mood,zone,rolling_cvd,imb)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    time.time(), coin, reason[:500], mid,
                    st.trend_context.get("day_mood"), st.trend_context.get("band_zone"),
                    st.flow.rolling_cvd(), safe_imb(st.book, 5),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def record_signal(self, coin: str, side: str, setup: str, mid: float, st: CoinState, reason: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO signals(ts,coin,side,setup,mid,vwap,upper_trade,lower_trade,zone,mood,rolling_cvd,imb,reason,session_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    time.time(), coin, side, setup, mid, st.bands.get("mid"), _upper(st.bands), _lower(st.bands),
                    st.trend_context.get("band_zone"), st.trend_context.get("day_mood"),
                    st.flow.rolling_cvd(), safe_imb(st.book, 5), reason[:1000], self.session_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def has_open(self, coin: str) -> bool:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM paper_trades WHERE coin=? AND status='open' LIMIT 1", (coin,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def try_open_trade(
        self,
        coin: str,
        side: str,
        setup: str,
        entry: float,
        size_usd: float,
        lev: int,
        sl_roe: float,
        tp_roe: float,
        reason: str,
        live: bool = False,
        sl_price: float = 0.0,
        tp_price: float = 0.0,
    ) -> Optional[int]:
        """Atomic open: one open row per coin. Returns trade id or None if blocked."""
        entry = float(entry)
        size_usd = float(size_usd)
        lev = float(lev)
        sl_roe = float(sl_roe)
        tp_roe = float(tp_roe)
        # Prefer explicit price stops when provided (incl. no_sl: sl_price=0, tp_price set).
        if tp_price:
            sl, tp = float(sl_price), float(tp_price)
        elif side == "LONG":
            sl = entry * (1 - sl_roe / max(lev, 1e-9))
            tp = entry * (1 + tp_roe / max(lev, 1e-9))
        else:
            sl = entry * (1 + sl_roe / max(lev, 1e-9))
            tp = entry * (1 - tp_roe / max(lev, 1e-9))
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT 1 FROM paper_trades WHERE coin=? AND status='open' LIMIT 1",
                (coin,),
            ).fetchone()
            if row is not None:
                conn.rollback()
                LOG.info("OPEN BLOCKED %s — already have open paper trade", coin)
                return None
            cur = conn.execute(
                """
                INSERT INTO paper_trades(
                    ts,coin,side,setup,entry,size_usd,leverage,sl_price,tp_price,status,reason,live,session_id,contaminated
                )
                VALUES (?,?,?,?,?,?,?,?,?,'open',?,?,?,0)
                """,
                (
                    time.time(), coin, side, setup, entry, size_usd, lev, sl, tp,
                    reason[:1000], 1 if live else 0, self.session_id,
                ),
            )
            conn.commit()
            tid = cur.lastrowid
        except sqlite3.IntegrityError:
            try:
                conn.rollback()
            except Exception:
                pass
            LOG.info("OPEN BLOCKED %s — unique open constraint", coin)
            return None
        finally:
            conn.close()
        LOG.info(
            "%s OPEN %s %s %s entry=%.4f size=$%.2f lev=%sx SL=%.4f TP=%.4f session=%s",
            "LIVE" if live else "PAPER", coin, side, setup, entry, size_usd, lev, sl, tp, self.session_id,
        )
        return tid

    def count_open_trades(self) -> int:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM paper_trades WHERE status='open'"
            ).fetchone()
            return int(row[0] if row is not None else 0)
        finally:
            conn.close()

    def open_trade(self, *args, **kwargs) -> int:
        """Backward-compatible wrapper; prefer try_open_trade."""
        tid = self.try_open_trade(*args, **kwargs)
        return int(tid or 0)

    def enforce_exits(self, mids: Dict[str, float], executor: "HybridExecutor | None" = None) -> List[dict]:
        """Close open rows that hit SL/TP. Returns list of closed trade dicts for alerts."""
        closed: List[dict] = []
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM paper_trades WHERE status='open'").fetchall()
            for r in rows:
                mid = mids.get(r["coin"])
                if not mid or mid <= 0:
                    continue
                side = r["side"]
                reason = None
                px = None
                no_sl = not r["sl_price"]  # sl_price == 0 means stop disabled
                if side == "LONG":
                    if not no_sl and mid <= r["sl_price"]:
                        px, reason = r["sl_price"], "stop_loss"
                    elif mid >= r["tp_price"]:
                        px, reason = r["tp_price"], "take_profit"
                else:
                    if not no_sl and mid >= r["sl_price"]:
                        px, reason = r["sl_price"], "stop_loss"
                    elif mid <= r["tp_price"]:
                        px, reason = r["tp_price"], "take_profit"
                if px is None:
                    continue
                price_ret = (px - r["entry"]) / r["entry"] if side == "LONG" else (r["entry"] - px) / r["entry"]
                pnl_roe = price_ret * r["leverage"]
                pnl_usd = price_ret * r["size_usd"]
                exit_ts = time.time()
                if r["live"] and executor is not None and executor.is_live:
                    executor.exit(r["coin"], side == "LONG", px)
                conn.execute(
                    """
                    UPDATE paper_trades SET status='closed', exit_ts=?, exit_price=?, exit_reason=?, pnl_usd=?, pnl_roe=? WHERE id=?
                    """,
                    (exit_ts, px, reason, pnl_usd, pnl_roe, r["id"]),
                )
                LOG.info(
                    "%s CLOSE %s %s %s reason=%s pnl=$%+.4f roe=%+.2f%%",
                    "LIVE" if r["live"] else "PAPER", r["coin"], side, r["setup"], reason, pnl_usd, pnl_roe * 100,
                )
                hold_min = 0.0
                try:
                    hold_min = max(0.0, (exit_ts - float(r["ts"])) / 60.0)
                except Exception:
                    pass
                closed.append(
                    {
                        "id": r["id"],
                        "coin": r["coin"],
                        "side": side,
                        "setup": r["setup"],
                        "entry": float(r["entry"]),
                        "exit_price": float(px),
                        "size_usd": float(r["size_usd"]),
                        "pnl_usd": float(pnl_usd),
                        "pnl_roe": float(pnl_roe),
                        "exit_reason": reason,
                        "live": bool(r["live"]),
                        "session_id": r["session_id"] or self.session_id,
                        "hold_min": hold_min,
                    }
                )
            conn.commit()
        finally:
            conn.close()
        return closed

    def readiness_rows(self, session_id: Optional[str] = None, session_only: bool = True) -> List[sqlite3.Row]:
        conn = self._conn()
        try:
            q = """
                SELECT coin, setup, pnl_usd, size_usd, status, exit_price, contaminated, session_id, exit_reason
                FROM paper_trades
                WHERE status='closed'
                  AND exit_price IS NOT NULL
                  AND IFNULL(contaminated,0)=0
                  AND IFNULL(setup,'') != 'test'
                  AND IFNULL(exit_reason,'') NOT IN ('contaminated_dup')
            """
            params: List[Any] = []
            if session_only and session_id:
                q += " AND session_id=?"
                params.append(session_id)
            return list(conn.execute(q, params).fetchall())
        finally:
            conn.close()


def _upper(bands: Dict[str, float]) -> float:
    return float(bands.get("upper_trade") or bands.get("upper_2.0") or bands.get("upper_1.0") or 0.0)


def _lower(bands: Dict[str, float]) -> float:
    return float(bands.get("lower_trade") or bands.get("lower_2.0") or bands.get("lower_1.0") or 0.0)


def safe_imb(book: OrderBook, levels: int) -> float:
    try:
        return float(book.imbalance_ratio(levels))
    except Exception:
        return 0.0


def cvd_threshold_for(coin: str, cfg: HybridConfig) -> float:
    if coin in {"xyz:GOLD", "GOLD", "PAXG", "cash:GOLD"}:
        return cfg.cvd_confirm_gold_usd
    if coin in {"BTC", "ETH"} or ":" not in coin:
        # mainnet majors use full BTC threshold; unknown mainnet names still BTC-scale
        if coin in {"BTC", "ETH"}:
            return cfg.cvd_confirm_usd
        return cfg.cvd_confirm_usd
    # HIP-3 / cash alts (SP500, WTI, …)
    return cfg.cvd_confirm_alt_usd


def cvd_accel_threshold_for(coin: str, cfg: HybridConfig) -> float:
    if coin in {"xyz:GOLD", "GOLD", "PAXG", "cash:GOLD"}:
        return cfg.cvd_accel_gold_usd
    if coin in {"BTC", "ETH"}:
        return cfg.cvd_accel_usd
    if ":" in coin:
        return cfg.cvd_accel_alt_usd
    return cfg.cvd_accel_usd

def orderflow_confirms(side: str, st: CoinState, cfg: HybridConfig, coin: str) -> Tuple[bool, str]:
    imb = safe_imb(st.book, cfg.imbalance_levels)
    if imb <= 0 or imb > cfg.imb_max:
        return False, f"imb {imb:.2f} invalid/thin-book"
    rcvd = st.flow.rolling_cvd()
    accel = st.flow.cvd_window(cfg.cvd_accel_seconds)
    thr = cvd_threshold_for(coin, cfg)
    ath = cvd_accel_threshold_for(coin, cfg)
    if side == "LONG":
        ok = (
            imb >= cfg.imb_long
            and rcvd >= thr
            and accel >= ath
        )
        return ok, (
            f"flow long imb={imb:.2f}>={cfg.imb_long} rcvd=${rcvd:,.0f}>={thr:,.0f} "
            f"accel{cfg.cvd_accel_seconds}s=${accel:,.0f}>={ath:,.0f}"
        )
    ok = (
        imb <= cfg.imb_short
        and rcvd <= -thr
        and accel <= -ath
    )
    return ok, (
        f"flow short imb={imb:.2f}<={cfg.imb_short} rcvd=${rcvd:,.0f}<=-{thr:,.0f} "
        f"accel{cfg.cvd_accel_seconds}s=${accel:,.0f}<=-{ath:,.0f}"
    )


class HybridBot:
    def __init__(self, cfg: HybridConfig):
        self.cfg = cfg
        self.scanner = Scanner()
        self.store = HybridStore(session_id=cfg.session_id)
        self.executor = HybridExecutor(cfg)
        self.states: Dict[str, CoinState] = {
            c: CoinState(flow=FlowState(cfg.cvd_window_seconds, cfg.cvd_max_trades))
            for c in cfg.coins
        }
        self._last_metrics = 0.0
        # Pending maker entries: oid -> {coin, is_buy, size_usd, px, lev, ts, sl_px, tp_px, side, setup}
        # Used to detect unfilled maker orders and upgrade them to taker fills.
        self.pending_entries: Dict[int, dict] = {}
        # v2: HL asset-context cache (funding / OI / basis / impact / day notional).
        self._ctx: Dict[str, Any] = {}
        self._ctx_prev_oi: Dict[str, float] = {}
        self._ctx_ts: float = 0.0

    def _refresh_ctx(self, force: bool = False) -> None:
        """Fetch metaAndAssetCtxs (main + per-dex) into self._ctx. TTL-throttled.

        Gates no-op on missing fields, so a failed refresh never blocks entries —
        it just leaves the previous snapshot (or None) in place.
        """
        if not self.cfg.ctx_enabled or AssetCtx is None:
            return
        assert dex_for_coin is not None and universe_name is not None and parse_asset_ctx is not None
        now = time.time()
        if not force and (now - self._ctx_ts) < self.cfg.ctx_refresh_sec:
            return
        try:
            import requests
        except Exception:
            return
        base = "https://api.hyperliquid-testnet.xyz" if self.cfg.testnet else "https://api.hyperliquid.xyz"
        by_dex: Dict[str, List[str]] = {}
        for c in self.cfg.coins:
            by_dex.setdefault(dex_for_coin(c), []).append(c)
        for dex, coins in by_dex.items():
            body: Dict[str, Any] = {"type": "metaAndAssetCtxs"}
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
                    # HIP-3 dexes keep the prefix in universe names (e.g. "xyz:GOLD");
                    # try prefixed first, then bare.
                    i = idx.get(coin)
                    if i is None:
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

    def _tg_enabled_for(self, live: bool) -> bool:
        if not self.cfg.telegram_enabled or _tg is None:
            return False
        if live:
            return True
        return bool(self.cfg.telegram_paper)

    def _tg_open(
        self,
        *,
        coin: str,
        side: str,
        setup: str,
        size_usd: float,
        lev: float,
        entry: float,
        sl: float,
        tp: float,
        live: bool,
        reason: str,
        trade_id: Optional[int],
    ) -> None:
        if not self._tg_enabled_for(live):
            return
        try:
            ok = _tg.send_hybrid_trade_open(
                coin=coin,
                side=side,
                setup=setup,
                size_usd=size_usd,
                leverage=lev,
                entry_price=entry,
                sl_price=sl,
                tp_price=tp,
                session=self.cfg.session_id,
                live=live,
                reason=reason,
                trade_id=trade_id,
            )
            if not ok:
                LOG.warning("Telegram OPEN alert failed %s %s", coin, side)
        except Exception as e:
            LOG.warning("Telegram OPEN alert error: %s", e)

    def _tg_close(self, c: dict) -> None:
        if not self._tg_enabled_for(bool(c.get("live"))):
            return
        try:
            ok = _tg.send_hybrid_trade_close(
                coin=c["coin"],
                side=c["side"],
                setup=c.get("setup") or "",
                pnl_usd=float(c.get("pnl_usd") or 0),
                pnl_roe=float(c.get("pnl_roe") or 0),
                entry_price=float(c.get("entry") or 0),
                exit_price=float(c.get("exit_price") or 0),
                size_usd=float(c.get("size_usd") or 0),
                exit_reason=str(c.get("exit_reason") or ""),
                session=str(c.get("session_id") or self.cfg.session_id),
                live=bool(c.get("live")),
                hold_min=float(c.get("hold_min") or 0),
                trade_id=c.get("id"),
            )
            if not ok:
                LOG.warning("Telegram CLOSE alert failed %s", c.get("coin"))
        except Exception as e:
            LOG.warning("Telegram CLOSE alert error: %s", e)

    def _tg_error(self, title: str, details: str = "", coin: str = "") -> None:
        if not self.cfg.telegram_enabled or _tg is None:
            return
        try:
            ok = _tg.send_hybrid_error(title=title, details=details, coin=coin)
            if not ok:
                LOG.warning("Telegram ERROR alert failed: %s", title)
        except Exception as e:
            LOG.warning("Telegram ERROR alert error: %s", e)

    def _tg_status(self, status: str, details: str = "") -> None:
        if not self.cfg.telegram_enabled or _tg is None:
            return
        try:
            ok = _tg.send_bot_status(status, details)
            if not ok:
                LOG.warning("Telegram STATUS alert failed: %s", status)
        except Exception as e:
            LOG.warning("Telegram STATUS alert error: %s", e)

    def _parse_trades(self, coin: str, data: Any) -> Iterable[Trade]:
        rows = data if isinstance(data, list) else [data]
        for t in rows:
            if not isinstance(t, dict) or t.get("coin") != coin:
                continue
            try:
                yield Trade(coin=coin, side=str(t.get("side", "")), px=float(t["px"]), sz=float(t["sz"]), time_ms=int(t.get("time", 0)))
            except Exception:
                continue

    def refresh_vwap(self, coin: str, st: CoinState) -> None:
        now = time.time()
        if now - st.last_vwap_refresh < self.cfg.vwap_refresh_seconds and st.bands:
            return
        st.last_vwap_refresh = now
        st.bands = self.scanner.compute_vwap_bands(coin) or {}
        st.ib = self.scanner.compute_initial_balance(coin) or {}
        vols = {v.asset: v for v in (self.scanner.snapshot([coin]) or [])}
        st.volume = vols.get(coin)
        mid = st.book.weighted_mid() or st.bands.get("mid") or 0.0
        if not st.bands or mid <= 0:
            return
        of = self._orderflow_snapshot(coin, st)
        ctx = MarketContext(
            asset=coin,
            orderflow=of,
            volume=st.volume,
            entry_approx=mid,
            session_vwap=st.bands.get("mid"),
            session_vwap_slope=st.bands.get("slope", 0.0),
            vwap_bands=st.bands,
            ib_high=st.ib.get("high"),
            ib_low=st.ib.get("low"),
            ib_mid=st.ib.get("mid"),
            rolling_cvd_usd=st.flow.rolling_cvd(),
        )
        trend = compute_session_trend(
            mid=mid,
            vwap=st.bands.get("mid", 0.0),
            slope=st.bands.get("slope", 0.0),
            ctx=ctx,
            vol=st.volume,
            recent_candles=self.scanner._get_volume_baseline(coin),
        )
        st.trend_context = mood_context(trend, mid, st.bands.get("mid", 0.0), st.bands)
        st.trend_context["preferred_side"] = trend.preferred_side

    def _orderflow_snapshot(self, coin: str, st: CoinState) -> OrderFlowSnapshot:
        bids, asks = st.book.bids, st.book.asks
        bb = bids[0].px if bids else None
        ba = asks[0].px if asks else None
        mid = st.book.weighted_mid() or None
        bid_notional = sum(l.px * l.sz for l in bids[: self.cfg.imbalance_levels])
        ask_notional = sum(l.px * l.sz for l in asks[: self.cfg.imbalance_levels])
        imb01 = bid_notional / (bid_notional + ask_notional) if bid_notional + ask_notional > 0 else None
        return OrderFlowSnapshot(
            asset=coin,
            ts=time.time(),
            best_bid=bb,
            best_ask=ba,
            mid=mid,
            spread=(ba - bb) if bb and ba else None,
            imbalance=imb01,
            bid_depth_notional=bid_notional,
            ask_depth_notional=ask_notional,
        )

    def _note_fail(self, coin: str, st: CoinState, mid: float, reason: str) -> None:
        st.last_fail_reason = reason
        now = time.time()
        if now - st.last_fail_log_ts < self.cfg.fail_log_seconds:
            return
        st.last_fail_log_ts = now
        LOG.info("NO_SIGNAL %s: %s", coin, reason)
        try:
            self.store.record_gate(coin, reason, st, mid)
        except Exception as e:
            LOG.debug("gate log failed: %s", e)

    def evaluate(self, coin: str) -> Optional[Tuple[str, str, str]]:
        st = self.states[coin]
        mid = st.book.weighted_mid()
        if mid <= 0:
            return None
        self.refresh_vwap(coin, st)
        if not st.bands or st.bands.get("mid", 0) <= 0:
            self._note_fail(coin, st, mid, "no_vwap_bands")
            return None
        if self.store.has_open(coin):
            return None
        if time.time() - st.last_signal_ts < self.cfg.cooldown_seconds:
            return None

        mood = st.trend_context.get("day_mood") or "range"
        zone = st.trend_context.get("band_zone") or band_zone(mid, st.bands.get("mid", 0), st.bands)
        vwap = float(st.bands.get("mid") or 0.0)
        rcvd = st.flow.rolling_cvd()
        thr = cvd_threshold_for(coin, self.cfg)
        imb = safe_imb(st.book, self.cfg.imbalance_levels)

        candidates: List[Tuple[str, str, str]] = []
        # Highest-quality idea: range/reversal only at actual 2σ bands.
        # v2: fade policy — HYB_FADE_MODE off|lower_only|all. Evidence: upper_band
        # fades were the primary drag (PF ~0.52); default lower_only blocks them.
        fades_on = fade_allowed is None or fade_allowed(zone, self.cfg.fade_mode)
        if fades_on and zone == "upper_band" and mood in {"range", "downtrend"}:
            candidates.append(("SHORT", "vwap_2sigma_fade", f"upper 2σ fade allowed by mood+fade_mode={self.cfg.fade_mode}"))
        if fades_on and zone == "lower_band" and mood in {"range", "uptrend"}:
            candidates.append(("LONG", "vwap_2sigma_fade", f"lower 2σ fade allowed by mood+fade_mode={self.cfg.fade_mode}"))
        # Trend continuation: pullbacks only in discount zones; rally shorts only into premium.
        # Dropped at_vwap / lower_half shorts (chase) — paper WR ~17–33% there.
        if mood == "uptrend" and zone in {"lower_half", "lower_band"} and mid < vwap:
            candidates.append(("LONG", "trend_pullback", "uptrend pullback under value"))
        if mood == "downtrend" and zone in {"upper_half", "upper_band"}:
            candidates.append(("SHORT", "trend_rally_short", "downtrend short into premium"))

        if not candidates:
            self._note_fail(
                coin, st, mid,
                f"no_setup mood={mood} zone={zone} mid={mid:.4f} vwap={vwap:.4f} rcvd=${rcvd:,.0f} imb={imb:.2f}",
            )
            return None

        fails: List[str] = []
        for side, setup, why in candidates:
            # Level CVD gate first (fast reject messaging), then full flow+accel.
            if side == "LONG" and rcvd < thr:
                fails.append(f"{setup}:cvd_level")
                continue
            if side == "SHORT" and rcvd > -thr:
                fails.append(f"{setup}:cvd_level")
                continue
            ok, flow_reason = orderflow_confirms(side, st, self.cfg, coin)
            if not ok:
                fails.append(f"{setup}:{flow_reason}")
                continue
            return side, setup, f"{why}; mood={mood} zone={zone}; {flow_reason}; cvd_thr=${thr:,.0f}"
        self._note_fail(coin, st, mid, f"flow_reject mood={mood} zone={zone} " + " | ".join(fails[:3]))
        return None

    def maybe_signal(self, coin: str) -> None:
        decision = self.evaluate(coin)
        if not decision:
            return
        side, setup, reason = decision
        st = self.states[coin]
        now = time.time()
        # Spaced confirmation: same side+setup across distinct book samples.
        if st.signal_hist:
            last_side, last_setup, last_ts = st.signal_hist[-1]
            if (last_side, last_setup) == (side, setup) and (now - last_ts) * 1000.0 < self.cfg.confirm_gap_ms:
                return  # too soon to count another confirm sample
        st.signal_hist.append((side, setup, now))
        if len(st.signal_hist) < self.cfg.signal_confirm:
            return
        tail = list(st.signal_hist)[-self.cfg.signal_confirm :]
        if not all(s == side and su == setup for s, su, _ in tail):
            return
        mid = st.book.weighted_mid()

        # --- v2: HL context gates (soft veto) — after structure+flow, before sizing/entry.
        # Failures log via _note_fail as context_reject; microstructure failures
        # either force taker (skip_maker) or reject the entry (skip_entry).
        use_maker = self.cfg.maker_orders
        if self.cfg.ctx_enabled and AssetCtx is not None:
            self._refresh_ctx()
            ctx = self._ctx.get(coin)
            if ctx is not None:
                assert (min_day_ntl_for_coin is not None and gate_day_ntl is not None
                        and gate_oi_fade is not None and gate_funding is not None
                        and gate_microstructure is not None)
                zone = (st.trend_context or {}).get("band_zone") or ""
                min_ntl = min_day_ntl_for_coin(
                    coin, self.cfg.min_day_ntl_btc, self.cfg.min_day_ntl_hip3, self.cfg.min_day_ntl_default
                )
                rejected = False
                for r in (
                    gate_day_ntl(ctx, min_ntl),
                    gate_oi_fade(side, setup, zone, ctx, enabled=self.cfg.oi_gate, rise_block=self.cfg.oi_rise_fade_block),
                ):
                    if r:
                        self._note_fail(coin, st, mid, f"context_reject {r}")
                        rejected = True
                        break
                if rejected:
                    st.signal_hist.clear()
                    return
                apply_funding = self.cfg.funding_gate and (
                    setup == "vwap_2sigma_fade" or self.cfg.funding_gate_trend
                )
                fr = gate_funding(
                    side, ctx, enabled=apply_funding,
                    long_max=self.cfg.funding_long_max, short_min=self.cfg.funding_short_min,
                )
                if fr:
                    self._note_fail(coin, st, mid, f"context_reject {fr}")
                    st.signal_hist.clear()
                    return
                micro = gate_microstructure(
                    ctx,
                    basis_enabled=self.cfg.basis_gate, max_basis=self.cfg.max_basis,
                    impact_enabled=self.cfg.impact_gate, max_impact=self.cfg.max_impact_spread,
                )
                if micro:
                    if self.cfg.micro_fail_mode == "skip_entry":
                        self._note_fail(coin, st, mid, f"context_reject {micro}")
                        st.signal_hist.clear()
                        return
                    use_maker = False
                    LOG.info("MICRO %s forcing taker: %s", coin, micro)
        # Leverage: MAX exchange leverage (capped by HYB_MAX_LEVERAGE). update_leverage runs in enter().
        derived_lev = max(1, round(self.cfg.sl_roe / max(self.cfg.sl_price_pct, 1e-9)))
        max_lev = min(self.scanner.get_max_leverage(coin), self.cfg.max_leverage_cap)
        lev = max_lev if self.cfg.use_max_leverage else min(max_lev, derived_lev)
        equity = self.executor.equity_usd() if self.executor.is_live else self.cfg.equity_fallback
        mode = (self.cfg.sizing_mode or "full_port").strip().lower()
        if mode in {"full_port", "fullport", "full"}:
            # Full-port: margin ≈ equity * port_fraction; notional = margin * lev
            size_usd = float(equity) * float(self.cfg.port_fraction) * float(lev)
        else:
            # Fixed $ risk at the price stop: risk_usd = size * sl_price_pct
            size_usd = float(equity) * float(self.cfg.risk_pct) / max(self.cfg.sl_price_pct, 1e-6)
        if self.cfg.max_position_usd and self.cfg.max_position_usd > 0:
            size_usd = min(float(self.cfg.max_position_usd), size_usd)
        if size_usd <= 0:
            LOG.warning("SKIP %s — size_usd<=0 equity=%.4f mode=%s", coin, equity, mode)
            return
        # Global concurrent open cap (critical for full-port on small equity).
        if self.cfg.max_open_positions > 0:
            n_open = self.store.count_open_trades()
            if n_open >= self.cfg.max_open_positions:
                LOG.info(
                    "OPEN BLOCKED %s — max_open_positions=%s (have %s)",
                    coin, self.cfg.max_open_positions, n_open,
                )
                return
        LOG.info(
            "SIZE %s mode=%s equity=$%.2f port=%.0f%% lev=%sx notional=$%.2f",
            coin, mode, equity, self.cfg.port_fraction * 100, lev, size_usd,
        )
        # Stops are ROE targets mapped through actual leverage → price distance.
        # e.g. SL 7% ROE @ 40x => 0.175% price; TP 15% ROE @ 40x => 0.375% price.
        sl_px_pct = float(self.cfg.sl_roe) / max(float(lev), 1e-9)
        tp_px_pct = float(self.cfg.tp_roe) / max(float(lev), 1e-9)
        if side == "LONG":
            sl = mid * (1 - sl_px_pct) if not self.cfg.no_sl else 0.0
            tp = mid * (1 + tp_px_pct)
        else:
            sl = mid * (1 + sl_px_pct) if not self.cfg.no_sl else 0.0
            tp = mid * (1 - tp_px_pct)
        LOG.info(
            "STOPS %s %s SL=%.2f%%ROE TP=%.2f%%ROE -> priceSL/TP=%.4f%%/%.4f%% sl=%.6f tp=%.6f",
            coin, side, self.cfg.sl_roe * 100, self.cfg.tp_roe * 100,
            sl_px_pct * 100, tp_px_pct * 100, sl, tp,
        )
        self.store.record_signal(coin, side, setup, mid, st, reason)
        if self.executor.is_live:
            is_buy = side == "LONG"
            res = self.executor.enter(coin, is_buy, size_usd, mid, lev, maker=use_maker)
            if isinstance(res, dict) and res.get("status") == "error":
                LOG.error("entry rejected, skipping trade %s %s", coin, side)
                self._tg_error(
                    "Entry rejected",
                    details=str(res.get("error") or res)[:500],
                    coin=coin,
                )
                st.signal_hist.clear()
                st.last_signal_ts = time.time()
                return
            if not self.cfg.no_sl:
                self.executor.attach_tpsl(coin, is_long=is_buy, sl_px=sl, tp_px=tp)
            else:
                self.executor.attach_tp_only(coin, is_long=is_buy, tp_px=tp)
            tid = self.store.try_open_trade(
                coin, side, setup, mid, size_usd, lev, self.cfg.sl_roe, self.cfg.tp_roe,
                reason, live=True, sl_price=sl, tp_price=tp,
            )
            if not tid:
                st.signal_hist.clear()
                st.last_signal_ts = time.time()
                return
            self._tg_open(
                coin=coin, side=side, setup=setup, size_usd=size_usd, lev=lev,
                entry=mid, sl=sl, tp=tp, live=True, reason=reason, trade_id=tid,
            )
            if use_maker and isinstance(res, dict):
                oid = _extract_oid(res)
                if oid is not None:
                    self.pending_entries[oid] = {
                        "coin": coin, "is_buy": is_buy, "side": side, "setup": setup,
                        "size_usd": size_usd, "px": mid, "lev": lev,
                        "sl_px": sl, "tp_px": tp, "ts": time.time(), "reason": reason,
                    }
                    LOG.info(
                        "MAKER PENDING oid=%s %s %s (upgrade to taker if unfilled in %.0fs)",
                        oid, coin, side, self.cfg.maker_fill_timeout_seconds,
                    )
        else:
            tid = self.store.try_open_trade(
                coin, side, setup, mid, size_usd, lev, self.cfg.sl_roe, self.cfg.tp_roe,
                reason, sl_price=sl, tp_price=tp,
            )
            if not tid:
                st.signal_hist.clear()
                st.last_signal_ts = time.time()
                return
            self._tg_open(
                coin=coin, side=side, setup=setup, size_usd=size_usd, lev=lev,
                entry=mid, sl=sl, tp=tp, live=False, reason=reason, trade_id=tid,
            )
        st.signal_hist.clear()
        st.last_signal_ts = time.time()

    async def check_pending_entries(self) -> None:
        """Upgrade unfilled maker entries to taker fills after HYB_MAKER_FILL_TIMEOUT.

        For each tracked maker order, check whether it has filled (still open & resting =
        unfilled). If it has sat longer than the timeout, cancel it and re-enter as a
        marketable IOC so the signal isn't missed. SL/TP were already attached at entry.
        """
        if not self.pending_entries:
            return
        if not self.executor.is_live or self.cfg.maker_fill_timeout_seconds <= 0:
            self.pending_entries.clear()
            return
        now = time.time()
        for oid, info in list(self.pending_entries.items()):
            age = now - info["ts"]
            if age < self.cfg.maker_fill_timeout_seconds:
                continue
            try:
                open_orders = self.executor.open_orders(info["coin"]) or []
                still_open = any(int(o.get("oid", -1)) == oid for o in open_orders)
            except Exception as e:
                LOG.warning("open_orders check failed %s: %s", info["coin"], e)
                still_open = True
            if not still_open:
                self.pending_entries.pop(oid, None)
                continue
            try:
                self.executor.cancel(info["coin"], oid)
                LOG.info("MAKER TIMEOUT oid=%s %s %s -> upgrading to taker", oid, info["coin"], info["side"])
            except Exception as e:
                LOG.warning("maker cancel failed %s oid=%s: %s", info["coin"], oid, e)
            self.executor.enter(info["coin"], info["is_buy"], info["size_usd"], info["px"], info["lev"], maker=False)
            self.pending_entries.pop(oid, None)

    async def metrics_loop(self) -> None:
        while True:
            await asyncio.sleep(self.cfg.metrics_seconds)
            self._refresh_ctx()
            mids = {}
            for coin, st in self.states.items():
                self.refresh_vwap(coin, st)
                st.flow.snapshot()
                mid = st.book.weighted_mid()
                if mid > 0:
                    mids[coin] = mid
                self.store.record_metrics(coin, st)
                LOG.info(
                    "METRICS %s mood=%s zone=%s mid=%.4f vwap=%.4f rcvd=$%.0f imb=%.2f",
                    coin, st.trend_context.get("day_mood"), st.trend_context.get("band_zone"),
                    mid, st.bands.get("mid", 0.0), st.flow.rolling_cvd(), safe_imb(st.book, self.cfg.imbalance_levels),
                )
            for c in self.store.enforce_exits(mids, executor=self.executor):
                self._tg_close(c)

    def _readiness_report(self) -> Tuple[bool, str]:
        """Read clean paper track record and check go-live bar.

        Excludes contaminated/test/dup trades. Optionally session-scoped.
        Applies a simple round-trip fee drag on notional for expectancy.
        """
        rows = self.store.readiness_rows(
            session_id=self.cfg.session_id,
            session_only=self.cfg.readiness_session_only,
        )
        n = len(rows)
        fee_frac = self.cfg.fee_bps_rt / 10000.0
        nets = []
        for r in rows:
            pnl = float(r["pnl_usd"] or 0.0)
            size = float(r["size_usd"] or 0.0)
            nets.append(pnl - size * fee_frac)
        wins = [x for x in nets if x > 0]
        losses = [x for x in nets if x <= 0]
        net = sum(nets) if nets else 0.0
        wr = (len(wins) / n) if n else 0.0
        gross_win = sum(x for x in nets if x > 0)
        gross_loss = abs(sum(x for x in nets if x < 0))
        pf = (gross_win / gross_loss) if gross_loss > 1e-9 else (999.0 if gross_win > 0 else 0.0)
        checks = [
            n >= self.cfg.min_closed_trades,
            wr >= self.cfg.min_win_rate,
            # Empty book is only allowed when operator sets min_closed_trades<=0 (explicit override).
            (net > 0) if n > 0 else (self.cfg.min_closed_trades <= 0),
            pf >= self.cfg.min_profit_factor if n > 0 else (self.cfg.min_closed_trades <= 0 or pf >= self.cfg.min_profit_factor),
        ]
        scope = f"session={self.cfg.session_id}" if self.cfg.readiness_session_only else "all_clean"
        lines = [
            f"  scope        : {scope} (excludes contaminated/test/dup)",
            f"  closed trades: {n}  (need >= {self.cfg.min_closed_trades})",
            f"  win rate     : {wr*100:.1f}%  (need >= {self.cfg.min_win_rate*100:.0f}%)",
            f"  net PnL fee  : ${net:+.2f}  (need > 0; fee={self.cfg.fee_bps_rt:.1f}bps rt)",
            f"  profit factor: {pf:.2f}  (need >= {self.cfg.min_profit_factor:.2f})",
        ]
        return all(checks), "\n".join(lines)

    async def _pending_entries_loop(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            try:
                await self.check_pending_entries()
            except Exception as e:
                LOG.warning("pending_entries loop error: %s", e)

    async def run(self) -> None:
        if not self.cfg.dry_run and not self.cfg.allow_live:
            raise SystemExit("HYB_DRY_RUN=false requires HYB_ALLOW_LIVE=1; paper validate first")
        # If the operator explicitly asked for live but the executor couldn't arm
        # (missing key, SDK import failure, etc.), REFUSE — never silently paper-trade
        # when real funds were intended. This guards against the msgpack/key-name class
        # of failures that would otherwise downgrade live to paper unnoticed.
        if (not self.cfg.dry_run) and self.cfg.allow_live and not self.executor.is_live:
            raise SystemExit(
                "GO-LIVE REQUESTED but executor is NOT live (missing key / SDK init failed). "
                "Refusing to run rather than silently paper-trade. Fix credentials, then retry."
            )
        # Hard go-live gate: never trade real funds until the paper track record
        # clears the readiness bar (your rule: >=N closed trades AND WR >= threshold).
        if self.executor.is_live:
            ok, report = self._readiness_report()
            if not ok:
                raise SystemExit(
                    "GO-LIVE BLOCKED — paper track record does not meet the readiness bar:\n"
                    + report
                    + "\nPaper-validate until the bar is met, then re-enable live."
                )
            LOG.info("GO-LIVE GATE PASSED:\n%s", report)
        pid_path = ROOT / "data" / "hybrid.pid"
        try:
            pid_path.write_text(str(os.getpid()))
        except Exception as e:
            LOG.warning("pid file write failed: %s", e)
        LOG.info(
            "hybrid bot start session=%s coins=%s dry_run=%s ws=%s pid=%s",
            self.cfg.session_id, self.cfg.coins, self.cfg.dry_run, self.cfg.ws_url, os.getpid(),
        )
        LOG.info(
            "v2 gates: fade_mode=%s ctx=%s refresh=%ss funding_gate=%s(trend=%s) oi_gate=%s "
            "basis_gate=%s impact_gate=%s micro_fail=%s min_day_ntl(btc/hip3/def)=%.0f/%.0f/%.0f",
            self.cfg.fade_mode, self.cfg.ctx_enabled, self.cfg.ctx_refresh_sec,
            self.cfg.funding_gate, self.cfg.funding_gate_trend, self.cfg.oi_gate,
            self.cfg.basis_gate, self.cfg.impact_gate, self.cfg.micro_fail_mode,
            self.cfg.min_day_ntl_btc, self.cfg.min_day_ntl_hip3, self.cfg.min_day_ntl_default,
        )
        self._refresh_ctx(force=True)
        mode = "LIVE" if self.executor.is_live else "PAPER"
        eq = 0.0
        try:
            eq = float(self.executor.equity_usd())
        except Exception:
            eq = float(self.cfg.equity_fallback)
        self._tg_status(
            "started",
            details=(
                f"Hybrid {mode}\n"
                f"session=<code>{self.cfg.session_id}</code>\n"
                f"coins={', '.join(self.cfg.coins)}\n"
                f"sizing={self.cfg.sizing_mode} port={self.cfg.port_fraction*100:.0f}% "
                f"maxlev={self.cfg.max_leverage_cap}x\n"
                f"SL/TP={self.cfg.sl_roe*100:.0f}%/{self.cfg.tp_roe*100:.0f}% ROE\n"
                f"equity≈${eq:.2f} · pid={os.getpid()}\n"
                f"telegram={'on' if self.cfg.telegram_enabled else 'off'}"
            ),
        )
        asyncio.create_task(self.metrics_loop())
        asyncio.create_task(self._pending_entries_loop())
        delay = 1.0
        while True:
            try:
                async with websockets.connect(self.cfg.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    delay = 1.0
                    for coin in self.cfg.coins:
                        for sub in (
                            {"method": "subscribe", "subscription": {"type": "trades", "coin": coin}},
                            {"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}},
                        ):
                            await ws.send(_dumps(sub))
                            await asyncio.sleep(0.05)
                    async for raw in ws:
                        msg = _loads(raw)
                        channel = msg.get("channel")
                        data = msg.get("data")
                        if channel == "trades":
                            # HL trade messages are per subscription but include coin.
                            for coin in self.cfg.coins:
                                st = self.states[coin]
                                for tr in self._parse_trades(coin, data):
                                    st.trade_count += 1
                                    st.flow.on_trade(tr)
                        elif channel == "l2Book" and isinstance(data, dict):
                            coin = data.get("coin")
                            if coin in self.states:
                                st = self.states[coin]
                                st.book.update_from_hl(data)
                                for c in self.store.enforce_exits({coin: st.book.weighted_mid()}, executor=self.executor):
                                    self._tg_close(c)
                                self.maybe_signal(coin)
                        elif channel == "subscriptionResponse":
                            LOG.info("subscribed: %s", data)
            except Exception as e:
                LOG.error("ws error: %s — reconnect in %.1fs", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 30)


def main() -> None:
    cfg = HybridConfig()
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(message)s")
    LOG.info(
        "boot session=%s coins=%s dry=%s live=%s testnet=%s cvd_thr=$%.0f/$%.0f accel=$%.0f/$%.0f "
        "imb=%s/%s confirm=%s gap=%sms cooldown=%ss SL/TP=%.1f%%/%.1f%%ROE "
        "sizing=%s port=%.0f%% maxlev=%s use_max_lev=%s max_open=%s maker=%s "
        "fade_mode=%s ctx=%s funding_gate=%s oi_gate=%s basis/impact=%s/%s micro_fail=%s",
        cfg.session_id, cfg.coins, cfg.dry_run, cfg.allow_live and not cfg.dry_run, cfg.testnet,
        cfg.cvd_confirm_usd, cfg.cvd_confirm_gold_usd, cfg.cvd_accel_usd, cfg.cvd_accel_gold_usd,
        cfg.imb_long, cfg.imb_short, cfg.signal_confirm, cfg.confirm_gap_ms, cfg.cooldown_seconds,
        cfg.sl_roe * 100, cfg.tp_roe * 100,
        cfg.sizing_mode, cfg.port_fraction * 100, cfg.max_leverage_cap, cfg.use_max_leverage,
        cfg.max_open_positions, cfg.maker_orders,
        cfg.fade_mode, cfg.ctx_enabled, cfg.funding_gate, cfg.oi_gate,
        cfg.basis_gate, cfg.impact_gate, cfg.micro_fail_mode,
    )
    asyncio.run(HybridBot(cfg).run())


if __name__ == "__main__":
    main()
