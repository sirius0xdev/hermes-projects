#!/usr/bin/env python3
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from decimal import Decimal

from dotenv import load_dotenv
from hyperliquid.info import Info
from hyperliquid.utils import constants as hl_constants

from planner import MarketContext, TradeProposal
from scanners import Scanner
from quant import Quant
from executor import Executor
from risk import RiskInputs, RiskRouter
from wallet_tracker import get_wallet_signals
from db import init_db, record_trade, close_trade, get_risk_config, open_trades, get_secret

ASSETS = ["BTC", "ETH", "SOL"]
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "30"))


def _build_market_section(
    scanner: Scanner,
    volumes_section,
) -> dict:
    mids_section = scanner.build_context(ASSETS)
    out = {}
    for asset in ASSETS:
        mids = mids_section.get(asset, {}).get("mids")
        volume = volumes_section.get(asset)
        orderflow = scanner.orderflow_snapshot(asset)
        out[asset] = MarketContext(
            asset=asset,
            orderflow=orderflow,
            volume=volume,
            entry_approx=orderflow.mid or mids,
        )
    return out


def _maybe_close_open_trades(active_positions: int) -> None:
    if active_positions > 0:
        return
    open_trades_list = open_trades(limit=1)
    for t in open_trades_list:
        close_trade(t["id"], pnl=None)


def bootstrap() -> None:
    init_db()
    load_dotenv()
    dry_run = os.getenv("DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "y"}
    scanner = Scanner()
    executor = Executor(
        dry_run=dry_run,
        private_key=get_secret("HL_PRIVATE_KEY"),
        address=get_secret("HL_ADDRESS"),
    )
    print("[Boot] trader starting; scalping orderflow mode")

    active_positions = 0
    while True:
        try:
            # Refresh risk config from DB on each tick (so dashboard changes apply immediately)
            rc = get_risk_config()
            equity = Decimal(str(rc["equity_usd"]))
            risk = RiskRouter(
                RiskInputs(
                    equity=float(equity),
                    current_daily_loss_pct=0.0,  # TODO: compute from daily PnL
                    open_positions=active_positions,
                    max_open_positions=rc["max_concurrent_positions"],
                    risk_pct_min=rc["risk_pct_min"],
                    risk_pct_max=rc["risk_pct_max"],
                    max_daily_loss_pct=rc["max_daily_loss_pct"],
                    default_leverage=rc["leverage"],
                )
            )
            quant = Quant(risk)

            volumes_section = {snap.asset: snap for snap in scanner.snapshot()}
            market_section = _build_market_section(scanner, volumes_section)
            wallets_section = get_wallet_signals()
            proposal = quant.propose(
                volumes=volumes_section,
                wallets=wallets_section,
                market=market_section,
            )
            event = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "asset": proposal.asset,
                "decision": proposal.decision,
                "leverage": proposal.leverage,
                "confidence": proposal.confidence,
                "risk_pct_of_equity": proposal.risk_pct_of_equity,
                "rationale": proposal.rationale,
                "orderflow": proposal.inputs.get("orderflow"),
            }
            print(f"[Tick] {event}")
            if proposal.decision in {"long", "short"}:
                execution = executor.submit(proposal, risk)
                print(f"[Executor] {execution.status}: {execution.message}")
                if execution and execution.proposal:
                    proposal = execution.proposal
                trade = proposal.to_dict()
                trade["status"] = "open" if execution.status not in {"stubbed", "dry_run"} else "dry_run"
                record_trade(trade)
                active_positions += 1
            _maybe_close_open_trades(active_positions)
            active_positions = len(open_trades(limit=200))
        except Exception as e:
            print(f"[Tick] error: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    bootstrap()