from __future__ import annotations

from typing import Any, Dict, List, Optional

from planner import (
    MarketContext,
    OrderFlowSnapshot,
    TradeProposal,
    VolumeSnapshot,
    WalletSignal,
)
from risk import RiskRouter, RiskInputs


class Quant:
    def __init__(self, risk: RiskRouter) -> None:
        self.risk = risk

    def propose(
        self,
        *,
        volumes: Optional[Dict[str, VolumeSnapshot]] = None,
        wallets: Optional[Dict[str, WalletSignal]] = None,
        market: Optional[Dict[str, MarketContext]] = None,
    ) -> TradeProposal:
        volumes = volumes or {}
        wallets = wallets or {}
        market = market or {}

        if not volumes or not market:
            return self._pass("insufficient market data")

        candidate_asset = self._select_candidate(volumes, market)
        if candidate_asset is None:
            return self._pass("no volume candidate")

        ctx = market[candidate_asset]
        vol = volumes.get(candidate_asset)
        orderflow = ctx.orderflow if ctx else None

        side = self._infer_side(vol, wallets, candidate_asset, orderflow)
        if side == "neutral":
            return self._pass("no orderflow or wallet edge")

        proposal = self._build_proposal(candidate_asset, side, vol, orderflow, ctx, wallets)
        return self.risk.enforce(proposal)

    def _select_candidate(
        self, volumes: Dict[str, VolumeSnapshot], market: Dict[str, MarketContext]
    ) -> Optional[str]:
        # Orderflow pressure prioritized candidate selection with volume z-score as tie-breaker.
        scored: List[Tuple[float, int, str]] = []
        for asset, ctx in market.items():
            of = ctx.orderflow
            vol = volumes.get(asset)
            flow_score = 0.0
            if of:
                flow_score = abs((of.bid_pressure or 0.0) - (of.ask_pressure or 0.0))
            volume_score = abs(vol.z_score) if vol else 0.0
            combined = flow_score * 2.0 + volume_score
            scored.append((combined, int(flow_score * 1000), asset))
        if not scored:
            return None
        scored.sort(reverse=True)
        return scored[0][2]

    def _infer_side(
        self,
        vol: Optional[VolumeSnapshot],
        wallets: Dict[str, WalletSignal],
        asset: str,
        orderflow: Optional[OrderFlowSnapshot],
    ) -> str:
        if orderflow:
            imbalance = orderflow.imbalance if orderflow.imbalance is not None else 0.0
            pressure_diff = 0.0
            if orderflow.bid_pressure is not None and orderflow.ask_pressure is not None:
                pressure_diff = orderflow.bid_pressure - orderflow.ask_pressure
            if imbalance >= 0.65 or pressure_diff >= 0.25:
                return "long"
            if imbalance <= 0.35 or pressure_diff <= -0.25:
                return "short"
        candidates = [w for w in wallets.values() if w.asset == asset and w.expected_impact in {"strong", "medium"}]
        if candidates and any(w.side in {"long", "short"} for w in candidates):
            vals = {"long": 0.0, "short": 0.0}
            for w in candidates:
                if w.side in vals:
                    vals[w.side] += float(w.notional)
            return max(vals, key=vals.get)
        if vol and vol.direction_bias in {"long", "short"}:
            return vol.direction_bias
        return "neutral"

    def _build_proposal(
        self,
        asset: str,
        side: str,
        vol: Optional[VolumeSnapshot],
        orderflow: Optional[OrderFlowSnapshot],
        ctx: Optional[MarketContext],
        wallets: Dict[str, WalletSignal],
    ) -> TradeProposal:
        walist = [w for w in wallets.values() if w.asset == asset]
        connections: List[str] = []
        if vol:
            connections.append(f"volume_z={vol.z_score:.2f}")
            connections.append(f"volume_direction={vol.direction_bias}")
        if orderflow:
            connections.append(f"imbalance={orderflow.imbalance:.2f}")
            connections.append(f"bid_pressure={orderflow.bid_pressure:.2f}")
            connections.append(f"ask_pressure={orderflow.ask_pressure:.2f}")
            connections.append(f"spread={orderflow.spread}")
        if ctx:
            if ctx.funding_rate is not None:
                connections.append(f"funding={ctx.funding_rate:.4f}%")
            if ctx.open_interest_delta_pct is not None:
                connections.append(f"oi_delta={ctx.open_interest_delta_pct:+.2f}%")
        connections.append(f"wallet_signals={len(walist)}")

        entry = ctx.entry_approx if ctx and ctx.entry_approx and ctx.entry_approx > 0 else None
        if orderflow and orderflow.mid:
            entry = orderflow.mid
        proposal = TradeProposal(
            decision=side,
            asset=asset,
            leverage=None,
            confidence=3,
            rationale="Scalping candidate selected by orderflow imbalance + volume + optional wallet alignment.",
            why_now="Liquidity imprint shows bid or ask pressure leading micro direction.",
            risks=["Scalping requires fast execution and tight risk control", "Orderflow advantage can reverse quickly"],
            inputs={
                "volume": vol.to_dict() if vol else None,
                "orderflow": orderflow.to_dict() if orderflow else None,
                "market": ctx.to_dict() if ctx else None,
                "wallet_signals": [w.to_dict() for w in walist],
                "connections": connections,
            },
            tags=["scalping"],
        )
        if entry:
            proposal.entry_approx = entry
        return proposal

    def _pass(self, reason: str) -> TradeProposal:
        return TradeProposal(decision="pass", rationale=reason)
