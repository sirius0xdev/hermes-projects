from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

from hyperliquid.info import Info
from hyperliquid.utils import constants as hl_constants

from planner import VolumeSnapshot, OrderFlowSnapshot


class Scanner:
    def __init__(self) -> None:
        self.info = Info(hl_constants.MAINNET_API_URL, skip_ws=True)

    def get_meta(self) -> Dict[str, Any]:
        return self.info.meta()

    def get_mids(self, assets: List[str]) -> Dict[str, Optional[float]]:
        try:
            all_mids = self.info.all_mids()
            return {asset: float(all_mids[asset]) if asset in all_mids else None for asset in assets}
        except Exception:
            return {asset: None for asset in assets}

    def build_context(self, assets: List[str]) -> Dict[str, Any]:
        mids = self.get_mids(assets)
        ctx: Dict[str, Any] = {}
        for asset, price in mids.items():
            ctx[asset] = {
                "mids": price,
                "meta": self._asset_meta(asset),
            }
        return ctx

    def _asset_meta(self, asset: str) -> Dict[str, Any]:
        try:
            meta = self.get_meta()
            perp = meta.get("universe", [])
            for item in perp:
                if item.get("name") == asset:
                    return item
        except Exception:
            pass
        return {}

    def snapshot(self, assets: Optional[List[str]] = None) -> List[VolumeSnapshot]:
        if assets is None:
            assets = ["BTC", "ETH", "SOL"]
        now_ts = time.time()
        end_ms = int(now_ts * 1000)
        start_ms = int(end_ms - 20 * 60 * 1000)
        results: List[VolumeSnapshot] = []

        for asset in assets:
            candles: List[Dict[str, Any]] = []
            try:
                candles = self.info.candles_snapshot(asset, "1m", start_ms, end_ms) or []
            except Exception:
                candles = []

            if not candles:
                results.append(
                    VolumeSnapshot(
                        asset=asset,
                        timestamp=now_ts,
                        notional_volume=0.0,
                        z_score=0.0,
                        direction_bias="neutral",
                    )
                )
                continue

            notional_volumes: List[float] = []
            latest_candle = candles[-1]
            for candle in candles:
                candle_volume = float(candle.get("v", 0) or 0)
                close_price = float(candle.get("c", 0) or 0)
                notional_volumes.append(candle_volume * close_price)

            last_notional = float(latest_candle.get("v", 0) or 0) * float(latest_candle.get("c", 0) or 0)
            z = 0.0
            if notional_volumes:
                mean = sum(notional_volumes) / len(notional_volumes)
                variance = sum((x - mean) ** 2 for x in notional_volumes) / len(notional_volumes)
                std = math.sqrt(variance)
                if std > 1e-9:
                    z = (last_notional - mean) / std

            bias = "neutral"
            if z > 1.5:
                bias = "long"
            elif z < -1.5:
                bias = "short"

            results.append(
                VolumeSnapshot(
                    asset=asset,
                    timestamp=float(latest_candle.get("T", end_ms)) / 1000.0,
                    notional_volume=last_notional,
                    z_score=z,
                    direction_bias=bias,
                )
            )
        return results

    def orderflow_snapshot(self, asset: str) -> OrderFlowSnapshot:
        now_ts = time.time()
        l2 = None
        try:
            l2 = self.info.l2_snapshot(asset)
        except Exception:
            l2 = None

        # Hyperliquid L2 snapshot format:
        # {"coin": "BTC", "time": 123456, "levels": [
        #   [{"px": "63404.0", "sz": "0.69394", "n": 2}, ...],  # bids (descending price)
        #   [{"px": "63405.0", "sz": "1.04976", "n": 3}, ...]   # asks (ascending price)
        # ]}
        bids: List[List[float]] = []
        asks: List[List[float]] = []
        if l2 and isinstance(l2, dict) and "levels" in l2:
            levels = l2["levels"]
            if isinstance(levels, list) and len(levels) >= 2:
                # levels[0] = bids, levels[1] = asks
                for level in levels[0]:
                    if isinstance(level, dict) and "px" in level and "sz" in level:
                        bids.append([float(level["px"]), float(level["sz"])])
                for level in levels[1]:
                    if isinstance(level, dict) and "px" in level and "sz" in level:
                        asks.append([float(level["px"]), float(level["sz"])])

        best_bid, best_ask = self._best_prices(bids, asks)
        mid, spread = self._mid_spread(best_bid, best_ask)

        bid_sizes = [size for _, size in bids[:5]]
        ask_sizes = [size for _, size in asks[:5]]
        bid_depth_notional = self._depth_notional(bids[:10])
        ask_depth_notional = self._depth_notional(asks[:10])

        bid_pressure = self._pressure_at_levels(bids[:5])
        ask_pressure = self._pressure_at_levels(asks[:5])
        bid_imbalance = self._normalized_pressure(bid_pressure, ask_pressure)
        ask_imbalance = self._normalized_pressure(ask_pressure, bid_pressure)

        imbalance = 0.0
        if bid_depth_notional + ask_depth_notional > 1e-9:
            imbalance = bid_depth_notional / (bid_depth_notional + ask_depth_notional)

        return OrderFlowSnapshot(
            asset=asset,
            ts=now_ts,
            best_bid=best_bid,
            best_ask=best_ask,
            mid=mid,
            spread=spread,
            imbalance=imbalance,
            bid_depth_notional=bid_depth_notional,
            ask_depth_notional=ask_depth_notional,
            bid_imbalance=bid_imbalance,
            ask_imbalance=ask_imbalance,
            bid_pressure=bid_pressure,
            ask_pressure=ask_pressure,
            top_bid_sizes=bid_sizes,
            top_ask_sizes=ask_sizes,
        )

    def _best_prices(self, bids: List[List[float]], asks: List[List[float]]) -> Tuple[Optional[float], Optional[float]]:
        best_bid = bids[0][0] if bids else None
        best_ask = asks[0][0] if asks else None
        return best_bid, best_ask

    def _mid_spread(self, best_bid: Optional[float], best_ask: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
        if best_bid is None or best_ask is None:
            return best_ask or best_bid, None
        if best_ask <= best_bid:
            return best_ask, 0.0
        mid = (best_bid + best_ask) / 2
        return mid, best_ask - best_bid

    def _depth_notional(self, levels: List[List[float]]) -> float:
        return sum(price * size for price, size in levels if price > 0 and size > 0)

    def _pressure_at_levels(self, levels: List[List[float]]) -> float:
        if not levels:
            return 0.0
        return sum(size for _, size in levels if size > 0)

    def _normalized_pressure(self, target: float, other: float) -> float:
        total = target + other
        if total <= 1e-9:
            return 0.0
        return max(-1.0, min(1.0, (target - other) / (total + 1e-9)))