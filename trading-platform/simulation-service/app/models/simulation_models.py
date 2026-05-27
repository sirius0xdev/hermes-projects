"""SQLAlchemy models for simulation results."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SimulationRun(Base):
    """Persisted simulation run results."""
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(50))  # "monte_carlo", "replay", "bootstrap", "what_if"
    symbol: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Parameters as JSON blob
    params: Mapped[str] = mapped_column(Text)

    # Key metrics
    initial_capital: Mapped[float] = mapped_column(Float)
    final_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Full results as JSON
    results_json: Mapped[str] = mapped_column(Text)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_type": self.run_type,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "strategy": self.strategy,
            "params": json.loads(self.params) if self.params else {},
            "initial_capital": self.initial_capital,
            "final_equity": self.final_equity,
            "total_pnl": self.total_pnl,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "results": json.loads(self.results_json) if self.results_json else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
