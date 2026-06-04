from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VolumeSnapshot:
    asset: str
    timestamp: float
    notional_volume: float
    z_score: float
    direction_bias: str  # "long" | "short" | "neutral"
    source: str = "scanner"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "timestamp": self.timestamp,
            "notional_volume": self.notional_volume,
            "z_score": self.z_score,
            "direction_bias": self.direction_bias,
            "source": self.source,
        }


@dataclass
class WalletSignal:
    wallet: str
    asset: str
    notional: float
    side: str
    expected_impact: str
    source: str = "wallet_tracker"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wallet": self.wallet,
            "asset": self.asset,
            "notional": self.notional,
            "side": self.side,
            "expected_impact": self.expected_impact,
            "source": self.source,
        }


@dataclass
class OrderFlowSnapshot:
    asset: str
    ts: float
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    mid: Optional[float] = None
    spread: Optional[float] = None
    imbalance: Optional[float] = None
    bid_depth_notional: Optional[float] = None
    ask_depth_notional: Optional[float] = None
    bid_imbalance: Optional[float] = None
    ask_imbalance: Optional[float] = None
    bid_pressure: Optional[float] = None
    ask_pressure: Optional[float] = None
    top_bid_sizes: Optional[List[float]] = None
    top_ask_sizes: Optional[List[float]] = None
    source: str = "scanner.l2"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "ts": self.ts,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "mid": self.mid,
            "spread": self.spread,
            "imbalance": self.imbalance,
            "bid_depth_notional": self.bid_depth_notional,
            "ask_depth_notional": self.ask_depth_notional,
            "bid_imbalance": self.bid_imbalance,
            "ask_imbalance": self.ask_imbalance,
            "bid_pressure": self.bid_pressure,
            "ask_pressure": self.ask_pressure,
            "top_bid_sizes": self.top_bid_sizes,
            "top_ask_sizes": self.top_ask_sizes,
            "source": self.source,
        }


@dataclass
class MarketContext:
    asset: str
    orderflow: Optional[OrderFlowSnapshot] = None
    volume: Optional[VolumeSnapshot] = None
    wallet: Optional[Dict[str, WalletSignal]] = None
    entry_approx: Optional[float] = None
    funding_rate: Optional[float] = None
    open_interest_delta_pct: Optional[float] = None
    rsi_1h: Optional[float] = None
    rsi_5m: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "orderflow": self.orderflow.to_dict() if self.orderflow else None,
            "volume": self.volume.to_dict() if self.volume else None,
            "wallet": {k: v.to_dict() for k, v in self.wallet.items()} if self.wallet else None,
            "entry_approx": self.entry_approx,
            "funding_rate": self.funding_rate,
            "open_interest_delta_pct": self.open_interest_delta_pct,
            "rsi_1h": self.rsi_1h,
            "rsi_5m": self.rsi_5m,
            "notes": self.notes,
        }


@dataclass
class TradeProposal:
    decision: str  # "long" | "short" | "pass"
    asset: Optional[str] = None
    size_usd_notional: Optional[float] = None
    leverage: Optional[int] = None
    entry_approx: Optional[float] = None
    stop_loss_idea: Optional[str] = None
    take_profit_idea: Optional[str] = None
    risk_pct_of_equity: Optional[float] = None
    confidence: Optional[int] = None
    rationale: Optional[str] = None
    why_now: Optional[str] = None
    risks: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "asset": self.asset,
            "size_usd_notional": self.size_usd_notional,
            "leverage": self.leverage,
            "entry_approx": self.entry_approx,
            "stop_loss_idea": self.stop_loss_idea,
            "take_profit_idea": self.take_profit_idea,
            "risk_pct_of_equity": self.risk_pct_of_equity,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "why_now": self.why_now,
            "risks": self.risks,
            "inputs": self.inputs,
            "tags": self.tags,
        }