from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants as hl_constants

from planner import TradeProposal
from risk import RiskRouter, RiskInputs


@dataclass
class ExecutionResult:
    status: str
    message: str
    order_id: Optional[str] = None
    tx: Optional[str] = None
    proposal: TradeProposal = None


class Executor:
    def __init__(self, dry_run: bool, private_key: Optional[str], address: Optional[str]) -> None:
        self.dry_run = dry_run or private_key is None
        self.private_key = private_key
        self.address = address
        self.info = Info(hl_constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = Exchange(hl_constants.MAINNET_API_URL)

    def submit(self, proposal: TradeProposal, risk: RiskRouter) -> ExecutionResult:
        if proposal.decision not in {"long", "short"}:
            return ExecutionResult(status="skipped", message="proposal discarded by quant/risk", proposal=proposal)
        if self.dry_run:
            return ExecutionResult(
                status="dry_run",
                message=f"no order sent; decision={proposal.decision} asset={proposal.asset}",
                proposal=proposal,
            )

        # Determine entry price
        entry_price = proposal.entry_approx
        if entry_price is None or entry_price <= 0:
            # Fallback to current mid from info
            mids = self.info.all_mids()
            entry_price = float(mids.get(proposal.asset, 0))
        if entry_price <= 0:
            return ExecutionResult(status="error", message="could not determine entry price", proposal=proposal)

        # Calculate size in base currency (not USD)
        size_usd = proposal.size_usd_notional
        if size_usd is None or size_usd <= 0:
            return ExecutionResult(status="error", message="invalid size_usd_notional", proposal=proposal)

        sz = round(size_usd / entry_price, 8)  # Hyperliquid uses 8 decimal sz for most assets

        # Get asset metadata for sz precision
        meta = self.info.meta()
        sz_decimals = 8
        perp = meta.get("universe", [])
        for item in perp:
            if item.get("name") == proposal.asset:
                sz_decimals = item.get("szDecimals", 8)
                break

        # Round to correct precision
        sz = round(sz, sz_decimals)
        if sz <= 0:
            return ExecutionResult(status="error", message=f"size too small after rounding: {sz}", proposal=proposal)

        # Round entry price to appropriate precision (default 2 decimals, but use 1 for high-value assets)
        px_decimals = 1 if entry_price >= 10000 else (2 if entry_price >= 1000 else 3)
        limit_px = round(entry_price, px_decimals)

        is_buy = proposal.decision == "long"
        order_type = {"limit": {"tif": "Gtc"}}

        try:
            order_result = self.exchange.order(
                coin=proposal.asset,
                is_buy=is_buy,
                sz=sz,
                limit_px=limit_px,
                order_type=order_type,
                reduce_only=False,
            )
        except Exception as e:
            return ExecutionResult(status="error", message=f"order failed: {e}", proposal=proposal)

        # Parse response
        # Typical response: {"status": "ok", "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 12345}}]}}}
        oid = None
        if isinstance(order_result, dict):
            if order_result.get("status") == "ok":
                resp = order_result.get("response", {})
                data = resp.get("data", {})
                statuses = data.get("statuses", [])
                if statuses:
                    status_obj = statuses[0]
                    if "resting" in status_obj:
                        oid = str(status_obj["resting"]["oid"])
                    elif "filled" in status_obj:
                        oid = str(status_obj["filled"]["oid"])

        if oid:
            return ExecutionResult(
                status="submitted",
                message=f"order placed: oid={oid} sz={sz} @ {limit_px}",
                order_id=oid,
                proposal=proposal,
            )
        else:
            return ExecutionResult(
                status="error",
                message=f"order response unexpected: {order_result}",
                proposal=proposal,
            )