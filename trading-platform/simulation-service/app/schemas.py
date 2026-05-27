"""Pydantic schemas for simulation-service request/response models."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Monte Carlo ────────────────────────────────────────────────────

class MonteCarloRequest(BaseModel):
    """Request body for Monte Carlo simulation."""
    initial_price: float = Field(..., description="Starting asset price")
    drift: float = Field(..., description="Annualized expected return (e.g. 0.10 for 10%)")
    volatility: float = Field(..., description="Annualized volatility (e.g. 0.20 for 20%)")
    time_horizon_days: int = Field(..., ge=1, description="Simulation horizon in trading days")
    n_simulations: int = Field(10000, ge=100, le=500000, description="Number of simulated paths")
    initial_capital: float = Field(100_000.0, gt=0, description="Starting capital")
    position_size_pct: float = Field(1.0, gt=0, le=10.0, description="Fraction of capital in position")
    entry_price: Optional[float] = Field(None, description="Entry price (defaults to initial_price)")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")


class MonteCarloResponse(BaseModel):
    """Response from Monte Carlo simulation."""
    mean_terminal_price: float
    median_terminal_price: float
    mean_pnl: float
    median_pnl: float
    std_pnl: float
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    percentiles: dict[str, float]
    mean_max_drawdown: float
    median_max_drawdown: float
    worst_max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    n_simulations: int
    time_steps: int


# ── Historical Replay ──────────────────────────────────────────────

class ReplayRequest(BaseModel):
    """Request body for historical replay."""
    symbol: str = Field(..., description="Trading symbol (e.g. BTC-USDT)")
    exchange: str = Field(..., description="Exchange (e.g. hyperliquid, solana)")
    start_date: str = Field(..., description="Start date (ISO format)")
    end_date: str = Field(..., description="End date (ISO format)")
    interval: str = Field("1d", description="Candle interval (1d, 1h, etc.)")
    strategy: str = Field("sma_crossover", description="Strategy name")
    initial_capital: float = Field(100_000.0, gt=0)
    position_size_pct: float = Field(1.0, gt=0, le=10.0)
    commission_pct: float = Field(0.001, ge=0, description="Commission fraction")
    strategy_params: Optional[dict[str, object]] = Field(None, description="Strategy-specific params")


class ReplayTradeResponse(BaseModel):
    """Single trade in replay response."""
    timestamp: str
    side: str
    price: float
    quantity: float
    pnl: float
    cumulative_pnl: float


class ReplayResponse(BaseModel):
    """Response from historical replay."""
    initial_capital: float
    final_equity: float
    total_pnl: float
    total_return_pct: float
    annualized_return: float
    volatility: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    profitable_trades: int
    avg_trade_pnl: float
    best_trade_pnl: float
    worst_trade_pnl: float
    trades: list[ReplayTradeResponse]
    equity_curve_points: int


# ── Bootstrap Simulation ───────────────────────────────────────────

class BootstrapRequest(BaseModel):
    """Request body for bootstrap simulation from historical data."""
    symbol: str
    exchange: str
    start_date: str = Field(..., description="Historical data start date (ISO)")
    end_date: str = Field(..., description="Historical data end date (ISO)")
    interval: str = "1d"
    n_simulations: int = Field(10000, ge=100, le=500000)
    time_horizon_days: int = Field(30, ge=1)
    initial_capital: float = Field(100_000.0, gt=0)
    position_size_pct: float = Field(1.0, gt=0, le=10.0)
    seed: Optional[int] = None


# ── What-If Scenario ──────────────────────────────────────────────

class WhatIfRequest(BaseModel):
    """Request body for what-if scenario analysis."""
    symbol: str
    exchange: str
    start_date: str
    end_date: str
    interval: str = "1d"
    scenarios: list["WhatIfScenario"]


class WhatIfScenario(BaseModel):
    """A single what-if scenario definition."""
    name: str = Field(..., description="Scenario label")
    strategy: str = Field("sma_crossover")
    initial_capital: float = Field(100_000.0, gt=0)
    position_size_pct: float = Field(1.0, gt=0, le=10.0)
    commission_pct: float = Field(0.001, ge=0)
    strategy_params: Optional[dict[str, object]] = None


class WhatIfScenarioResult(BaseModel):
    """Result of a single what-if scenario."""
    name: str
    final_equity: float
    total_pnl: float
    total_return_pct: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int


class WhatIfResponse(BaseModel):
    """Response with all scenario results."""
    scenarios: list[WhatIfScenarioResult]
    best_scenario: str
    worst_scenario: str


WhatIfRequest.model_rebuild()
