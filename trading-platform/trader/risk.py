from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from planner import TradeProposal


@dataclass
class RiskInputs:
    equity: float
    current_daily_loss_pct: float
    open_positions: int
    max_open_positions: int
    risk_pct_min: float
    risk_pct_max: float
    max_daily_loss_pct: float
    default_leverage: int = 5


class RiskRouter:
    def __init__(self, inputs: RiskInputs) -> None:
        self.inputs = inputs

    def enforce(self, proposal: TradeProposal) -> TradeProposal:
        if proposal.decision not in {"long", "short"}:
            return proposal
        if not self._can_trade():
            return TradeProposal(decision="pass", rationale="risk router blocked trade", inputs=proposal.inputs)

        risk_pct = max(self.inputs.risk_pct_min, min(self.inputs.risk_pct_max, 0.10))
        if proposal.risk_pct_of_equity is None:
            proposal.risk_pct_of_equity = risk_pct
        if proposal.leverage is None:
            proposal.leverage = self.inputs.default_leverage
        if proposal.stop_loss_idea is None:
            proposal.stop_loss_idea = "about 2% adverse move"
        if proposal.take_profit_idea is None:
            proposal.take_profit_idea = "rough 2x risk; later refined by execution policy"
        if proposal.size_usd_notional is None:
            proposal.size_usd_notional = round(self.inputs.equity * risk_pct, 2)
        if proposal.confidence is None:
            proposal.confidence = max(1, min(5, proposal.confidence or 3))
        proposal.risks = list(proposal.risks or []) + [
            "This is a draft size. Execution needs exact mark price, slippage tolerance, and margin checks before live orders."
        ]
        return proposal

    def _can_trade(self) -> bool:
        if self.inputs.open_positions >= self.inputs.max_open_positions:
            return False
        if self.inputs.current_daily_loss_pct >= self.inputs.max_daily_loss_pct:
            return False
        return True
