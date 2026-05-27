"""Monte Carlo simulation engine.

Generates price paths via Geometric Brownian Motion (GBM) and
computes risk metrics: PnL distribution, Value at Risk (VaR),
Conditional VaR (CVaR), max drawdown, Sharpe ratio.
"""
from __future__ import annotations

import numpy as np
from scipy import stats as sp_stats
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SimulationParams:
    """Parameters for Monte Carlo simulation."""
    initial_price: float
    drift: float                     # Annualized expected return
    volatility: float                # Annualized volatility (sigma)
    time_horizon_days: int
    n_simulations: int = 10000
    initial_capital: float = 100_000.0
    position_size_pct: float = 1.0   # Fraction of capital allocated
    entry_price: Optional[float] = None  # If None, == initial_price


@dataclass
class SimulationResult:
    """Aggregated results from a Monte Carlo simulation."""
    # Price paths: shape (n_simulations, time_steps)
    price_paths: np.ndarray

    # Terminal prices: shape (n_simulations,)
    terminal_prices: np.ndarray

    # PnL distribution (dollar PnL per simulation)
    pnl_values: np.ndarray

    # Summary statistics
    mean_terminal_price: float
    median_terminal_price: float
    mean_pnl: float
    median_pnl: float
    std_pnl: float

    # Risk metrics
    var_95: float                    # 95% Value at Risk (loss is negative)
    var_99: float                    # 99% Value at Risk
    cvar_95: float                   # Conditional VaR (Expected Shortfall) at 95%
    cvar_99: float                   # Conditional VaR at 99%

    # Distribution percentiles for terminal price
    percentile_5: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_95: float

    # Max drawdown statistics (across all paths)
    mean_max_drawdown: float
    median_max_drawdown: float
    worst_max_drawdown: float

    # Sharpe ratio (annualized)
    sharpe_ratio: float

    # Win rate
    win_rate: float

    # Total paths
    n_simulations: int

    # Time steps per path
    time_steps: int

    def to_dict(self) -> dict:
        return {
            "mean_terminal_price": round(self.mean_terminal_price, 2),
            "median_terminal_price": round(self.median_terminal_price, 2),
            "mean_pnl": round(self.mean_pnl, 2),
            "median_pnl": round(self.median_pnl, 2),
            "std_pnl": round(self.std_pnl, 2),
            "var_95": round(self.var_95, 2),
            "var_99": round(self.var_99, 2),
            "cvar_95": round(self.cvar_95, 2),
            "cvar_99": round(self.cvar_99, 2),
            "percentiles": {
                "5": round(self.percentile_5, 2),
                "25": round(self.percentile_25, 2),
                "50": round(self.percentile_50, 2),
                "75": round(self.percentile_75, 2),
                "95": round(self.percentile_95, 2),
            },
            "mean_max_drawdown": round(self.mean_max_drawdown, 4),
            "median_max_drawdown": round(self.median_max_drawdown, 4),
            "worst_max_drawdown": round(self.worst_max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "win_rate": round(self.win_rate, 4),
            "n_simulations": self.n_simulations,
            "time_steps": self.time_steps,
        }


def _compute_max_drawdowns(price_paths: np.ndarray) -> np.ndarray:
    """Compute max drawdown for each path. Returns array of shape (n_paths,).

    Drawdown = (peak - price) / peak, so positive values mean loss.
    """
    cummax = np.maximum.accumulate(price_paths, axis=1)
    drawdowns = (cummax - price_paths) / cummax
    return np.max(drawdowns, axis=1)


def run_monte_carlo(params: SimulationParams, seed: Optional[int] = None) -> SimulationResult:
    """Run Monte Carlo simulation using Geometric Brownian Motion.

    GBM: dS = mu*S*dt + sigma*S*dW
    Discrete: S(t+dt) = S(t) * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)

    Args:
        params: Simulation parameters.
        seed: Random seed for reproducibility.

    Returns:
        SimulationResult with aggregated statistics.
    """
    rng = np.random.default_rng(seed)

    S0 = params.entry_price or params.initial_price
    mu = params.drift
    sigma = params.volatility
    T = params.time_horizon_days / 365.0  # Convert to years
    n = params.n_simulations

    # Time discretization (daily steps)
    dt = T / params.time_horizon_days
    time_steps = params.time_horizon_days + 1

    # Generate random shocks: (n_simulations, time_steps)
    Z = rng.standard_normal((n, params.time_horizon_days))

    # Cumulative increments
    drift_term = (mu - 0.5 * sigma ** 2) * dt
    diffusive_term = sigma * np.sqrt(dt) * Z
    log_returns = drift_term + diffusive_term

    # Build price paths via cumulative sum
    log_prices = np.zeros((n, time_steps))
    log_prices[:, 0] = np.log(S0)
    log_prices[:, 1:] = log_prices[:, 0] + np.cumsum(log_returns, axis=1)
    price_paths = np.exp(log_prices)

    terminal_prices = price_paths[:, -1]

    # PnL calculation
    position_value = params.initial_capital * params.position_size_pct
    units = position_value / S0
    pnl_values = units * (terminal_prices - S0)

    # Risk metrics
    var_95 = float(np.percentile(pnl_values, 5))
    var_99 = float(np.percentile(pnl_values, 1))
    cvar_95 = float(np.mean(pnl_values[pnl_values <= var_95]))
    cvar_99 = float(np.mean(pnl_values[pnl_values <= var_99]))

    # Percentiles of terminal price
    percentile_5 = float(np.percentile(terminal_prices, 5))
    percentile_25 = float(np.percentile(terminal_prices, 25))
    percentile_50 = float(np.percentile(terminal_prices, 50))
    percentile_75 = float(np.percentile(terminal_prices, 75))
    percentile_95 = float(np.percentile(terminal_prices, 95))

    # Max drawdowns per path
    path_drawdowns = _compute_max_drawdowns(price_paths)

    # Sharpe ratio from simulated returns
    daily_returns = np.diff(price_paths, axis=1) / price_paths[:, :-1]
    mean_daily_return = float(np.mean(daily_returns))
    std_daily_return = float(np.std(daily_returns))
    daily_risk_free = 0.05 / 252  # 5% risk-free rate
    sharpe = (mean_daily_return - daily_risk_free) / std_daily_return * np.sqrt(252) if std_daily_return > 0 else 0.0

    # Win rate
    win_rate = float(np.mean(pnl_values > 0))

    return SimulationResult(
        price_paths=price_paths,
        terminal_prices=terminal_prices,
        pnl_values=pnl_values,
        mean_terminal_price=float(np.mean(terminal_prices)),
        median_terminal_price=float(np.median(terminal_prices)),
        mean_pnl=float(np.mean(pnl_values)),
        median_pnl=float(np.median(pnl_values)),
        std_pnl=float(np.std(pnl_values)),
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        percentile_5=percentile_5,
        percentile_25=percentile_25,
        percentile_50=percentile_50,
        percentile_75=percentile_75,
        percentile_95=percentile_95,
        mean_max_drawdown=float(np.mean(path_drawdowns)),
        median_max_drawdown=float(np.median(path_drawdowns)),
        worst_max_drawdown=float(np.max(path_drawdowns)),
        sharpe_ratio=sharpe,
        win_rate=win_rate,
        n_simulations=n,
        time_steps=time_steps,
    )


def estimate_params_from_history(
    prices: np.ndarray,
    annualization_factor: int = 252,
) -> tuple[float, float]:
    """Estimate drift and volatility from historical price data.

    Args:
        prices: Array of historical prices (any length).
        annualization_factor: Trading days per year (252 for equities, 365 for crypto).

    Returns:
        (drift, volatility) as annualized values.
    """
    returns = np.diff(np.log(prices))
    dt = 1.0 / annualization_factor

    drift = np.mean(returns) / dt
    volatility = np.std(returns, ddof=1) / np.sqrt(dt)

    return float(drift), float(volatility)


def bootstrap_from_history(
    prices: np.ndarray,
    n_simulations: int,
    time_horizon_days: int,
    initial_capital: float = 100_000.0,
    position_size_pct: float = 1.0,
    seed: Optional[int] = None,
) -> SimulationResult:
    """Bootstrap simulation: resample historical returns to generate paths.

    Unlike GBM, this preserves the actual return distribution (fat tails, skew)
    from the observed data.

    Args:
        prices: Historical price series.
        n_simulations: Number of bootstrap paths.
        time_horizon_days: Simulation horizon in trading days.
        initial_capital: Starting capital.
        position_size_pct: Fraction of capital in position.
        seed: Random seed.

    Returns:
        SimulationResult.
    """
    rng = np.random.default_rng(seed)
    log_returns = np.diff(np.log(prices))

    S0 = prices[-1]
    entry_price = S0
    position_value = initial_capital * position_size_pct
    units = position_value / entry_price

    # Bootstrap paths by resampling returns with replacement
    time_steps = time_horizon_days + 1
    log_prices = np.zeros((n_simulations, time_steps))
    log_prices[:, 0] = np.log(S0)

    for sim in range(n_simulations):
        sampled_returns = rng.choice(log_returns, size=time_horizon_days, replace=True)
        log_prices[sim, 1:] = log_prices[sim, 0] + np.cumsum(sampled_returns)

    price_paths = np.exp(log_prices)
    terminal_prices = price_paths[:, -1]
    pnl_values = units * (terminal_prices - entry_price)

    # Risk metrics
    var_95 = float(np.percentile(pnl_values, 5))
    var_99 = float(np.percentile(pnl_values, 1))
    cvar_95 = float(np.mean(pnl_values[pnl_values <= var_95]))
    cvar_99 = float(np.mean(pnl_values[pnl_values <= var_99]))

    percentile_5 = float(np.percentile(terminal_prices, 5))
    percentile_25 = float(np.percentile(terminal_prices, 25))
    percentile_50 = float(np.percentile(terminal_prices, 50))
    percentile_75 = float(np.percentile(terminal_prices, 75))
    percentile_95 = float(np.percentile(terminal_prices, 95))

    path_drawdowns = _compute_max_drawdowns(price_paths)

    # Sharpe from bootstrapped returns
    daily_returns = np.diff(price_paths, axis=1) / price_paths[:, :-1]
    mean_dr = float(np.mean(daily_returns))
    std_dr = float(np.std(daily_returns))
    daily_rf = 0.05 / 252
    sharpe = (mean_dr - daily_rf) / std_dr * np.sqrt(252) if std_dr > 0 else 0.0

    win_rate = float(np.mean(pnl_values > 0))

    return SimulationResult(
        price_paths=price_paths,
        terminal_prices=terminal_prices,
        pnl_values=pnl_values,
        mean_terminal_price=float(np.mean(terminal_prices)),
        median_terminal_price=float(np.median(terminal_prices)),
        mean_pnl=float(np.mean(pnl_values)),
        median_pnl=float(np.median(pnl_values)),
        std_pnl=float(np.std(pnl_values)),
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        percentile_5=percentile_5,
        percentile_25=percentile_25,
        percentile_50=percentile_50,
        percentile_75=percentile_75,
        percentile_95=percentile_95,
        mean_max_drawdown=float(np.mean(path_drawdowns)),
        median_max_drawdown=float(np.median(path_drawdowns)),
        worst_max_drawdown=float(np.max(path_drawdowns)),
        sharpe_ratio=sharpe,
        win_rate=win_rate,
        n_simulations=n_simulations,
        time_steps=time_steps,
    )
