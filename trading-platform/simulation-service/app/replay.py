"""Historical replay engine.

Fetches historical price data and replays trading strategies
against it, computing realized PnL, drawdowns, and risk metrics.
Supports what-if scenarios with custom entry/exit rules.
"""
from __future__ import annotations

import httpx
import numpy as np
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

logger = structlog.get_logger()


@dataclass
class TradeRecord:
    """A single trade in a replay."""
    timestamp: datetime
    side: str                    # "buy" or "sell"
    price: float
    quantity: float
    pnl: float = 0.0
    cumulative_pnl: float = 0.0


@dataclass
class ReplayResult:
    """Results from a historical replay."""
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    initial_capital: float = 100_000.0
    final_equity: float = 0.0
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profitable_trades: int = 0
    avg_trade_pnl: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    annualized_return: float = 0.0
    volatility: float = 0.0

    def to_dict(self) -> dict:
        return {
            "initial_capital": round(self.initial_capital, 2),
            "final_equity": round(self.final_equity, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_return_pct": round(self.total_return_pct, 4),
            "annualized_return": round(self.annualized_return, 4),
            "volatility": round(self.volatility, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "win_rate": round(self.win_rate, 4),
            "total_trades": self.total_trades,
            "profitable_trades": self.profitable_trades,
            "avg_trade_pnl": round(self.avg_trade_pnl, 2),
            "best_trade_pnl": round(self.best_trade_pnl, 2),
            "worst_trade_pnl": round(self.worst_trade_pnl, 2),
            "trades": [
                {
                    "timestamp": t.timestamp.isoformat(),
                    "side": t.side,
                    "price": round(t.price, 2),
                    "quantity": round(t.quantity, 4),
                    "pnl": round(t.pnl, 2),
                    "cumulative_pnl": round(t.cumulative_pnl, 2),
                }
                for t in self.trades[-20:]  # Last 20 trades
            ],
            "equity_curve_points": len(self.equity_curve),
        }


async def fetch_historical_prices(
    symbol: str,
    exchange: str,
    start_date: str,
    end_date: str,
    interval: str = "1d",
) -> dict[str, Any]:
    """Fetch historical price data from data-service.

    Args:
        symbol: Trading symbol (e.g. "BTC-USDT").
        exchange: Exchange identifier (e.g. "hyperliquid", "solana").
        start_date: Start date (ISO format).
        end_date: End date (ISO format).
        interval: Candle interval (e.g. "1d", "1h").

    Returns:
        Dict with 'timestamps', 'open', 'high', 'low', 'close', 'volume'.
    """
    url = f"{settings.data_service_url}/api/v1/marketdata/candles/{exchange}/{symbol}/{interval}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(url, params={
                "start_date": start_date,
                "end_date": end_date,
            })
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch candles", symbol=symbol, exchange=exchange, error=str(e))
            raise

    # Parse candle data
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []

    for candle in data.get("candles", []):
        timestamps.append(datetime.fromisoformat(candle["ts"]).replace(tzinfo=timezone.utc))
        opens.append(float(candle["open"]))
        highs.append(float(candle["high"]))
        lows.append(float(candle["low"]))
        closes.append(float(candle["close"]))
        volumes.append(float(candle.get("volume", 0)))

    return {
        "timestamps": timestamps,
        "open": np.array(opens),
        "high": np.array(highs),
        "low": np.array(lows),
        "close": np.array(closes),
        "volume": np.array(volumes),
    }


def generate_signals(
    close_prices: np.ndarray,
    strategy: str = "sma_crossover",
    short_window: int = 20,
    long_window: int = 50,
    **kwargs: Any,
) -> np.ndarray:
    """Generate trading signals from price data.

    Supported strategies:
    - sma_crossover: Buy when short MA crosses above long MA, sell when below.
    - rsi_reversion: Buy when RSI < oversold, sell when RSI > overbought.
    - momentum: Buy when price > N-day high, sell when price < N-day low.

    Args:
        close_prices: Array of closing prices.
        strategy: Strategy name.
        short_window: Shorter lookback window.
        long_window: Longer lookback window / RSI period.
        **kwargs: Additional strategy parameters.

    Returns:
        Signal array: 1 = buy, -1 = sell, 0 = hold.
    """
    n = len(close_prices)
    signals = np.zeros(n, dtype=int)

    if strategy == "sma_crossover":
        if n < long_window + 1:
            return signals
        sma_short = np.convolve(close_prices, np.ones(short_window) / short_window, mode="valid")
        sma_long = np.convolve(close_prices, np.ones(long_window) / long_window, mode="valid")

        # Align lengths
        offset = long_window - short_window
        sma_short_aligned = sma_short[offset:]
        sma_long_aligned = sma_long

        # Cross-over detection
        for i in range(1, len(sma_long_aligned)):
            global_idx = long_window + i
            if global_idx >= n:
                break
            if sma_short_aligned[i] > sma_long_aligned[i] and sma_short_aligned[i - 1] <= sma_long_aligned[i - 1]:
                signals[global_idx] = 1   # Buy
            elif sma_short_aligned[i] < sma_long_aligned[i] and sma_short_aligned[i - 1] >= sma_long_aligned[i - 1]:
                signals[global_idx] = -1  # Sell

    elif strategy == "rsi_reversion":
        rsi_period = kwargs.get("rsi_period", 14)
        oversold = kwargs.get("oversold", 30)
        overbought = kwargs.get("overbought", 70)

        if n < rsi_period + 1:
            return signals

        rsi = _compute_rsi(close_prices, rsi_period)
        for i in range(1, n):
            if rsi[i] is None or rsi[i - 1] is None:
                continue
            if rsi[i] > oversold and rsi[i - 1] <= oversold:
                signals[i] = 1   # Buy (RSI crosses above oversold)
            elif rsi[i] < overbought and rsi[i - 1] >= overbought:
                signals[i] = -1  # Sell (RSI crosses below overbought)

    elif strategy == "momentum":
        lookback = kwargs.get("lookback", long_window)
        if n < lookback + 1:
            return signals
        rolling_high = np.maximum.accumulate(close_prices[1:lookback + 1])
        # Full rolling high
        rolling_high = np.zeros(n)
        rolling_low = np.zeros(n)
        for i in range(lookback, n):
            rolling_high[i] = np.max(close_prices[i - lookback:i])
            rolling_low[i] = np.min(close_prices[i - lookback:i])

        in_position = False
        for i in range(lookback, n):
            if not in_position and close_prices[i] > rolling_high[i - 1]:
                signals[i] = 1
                in_position = True
            elif in_position and close_prices[i] < rolling_low[i - 1]:
                signals[i] = -1
                in_position = False

    else:
        logger.warning("Unknown strategy, returning no signals", strategy=strategy)

    return signals


def _compute_rsi(prices: np.ndarray, period: int = 14) -> list[float | None]:
    """Compute Relative Strength Index."""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    rsi = [None] * len(prices)
    if len(gains) < period:
        return rsi

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period, len(prices) - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def run_replay(
    price_data: dict[str, Any],
    strategy: str = "sma_crossover",
    initial_capital: float = 100_000.0,
    position_size_pct: float = 1.0,
    commission_pct: float = 0.001,  # 10 bps
    strategy_params: Optional[dict[str, Any]] = None,
) -> ReplayResult:
    """Run a historical backtest with the given strategy and price data.

    Args:
        price_data: Dict with 'timestamps', 'close', etc. (from fetch_historical_prices).
        strategy: Strategy name.
        initial_capital: Starting capital.
        position_size_pct: Fraction of equity to allocate per trade.
        commission_pct: Commission as fraction of trade value.
        strategy_params: Extra params forwarded to generate_signals.

    Returns:
        ReplayResult with full metrics.
    """
    closes = price_data["close"]
    timestamps = price_data["timestamps"]
    params = strategy_params or {}

    signals = generate_signals(closes, strategy=strategy, **params)

    equity = initial_capital
    position = 0.0  # Units held
    trades: list[TradeRecord] = []
    equity_curve: list[float] = [initial_capital]
    cumulative_pnl = 0.0
    trade_pnls = []

    for i in range(1, len(closes)):
        signal = signals[i]
        price = closes[i]

        if signal == 1 and position == 0:
            # Buy
            trade_value = equity * position_size_pct
            quantity = trade_value / price
            commission = trade_value * commission_pct
            position = quantity
            equity -= commission
            trades.append(TradeRecord(
                timestamp=timestamps[i],
                side="buy",
                price=price,
                quantity=quantity,
                pnl=0.0,
                cumulative_pnl=cumulative_pnl,
            ))

        elif signal == -1 and position > 0:
            # Sell
            trade_value = position * price
            commission = trade_value * commission_pct
            pnl = trade_value - (trades[-1].quantity * trades[-1].price) - commission
            trades[-1].pnl = pnl
            cumulative_pnl += pnl
            trades[-1].cumulative_pnl = cumulative_pnl
            trade_pnls.append(pnl)

            equity += trade_value - commission
            position = 0.0

        # Track equity (mark-to-market if in position)
        mtm = equity + position * price
        equity_curve.append(mtm)

    # Close any open position at final price
    if position > 0 and trades:
        price = closes[-1]
        trade_value = position * price
        commission = trade_value * commission_pct
        pnl = trade_value - (trades[-1].quantity * trades[-1].price) - commission
        trades[-1].pnl = pnl
        cumulative_pnl += pnl
        trades[-1].cumulative_pnl = cumulative_pnl
        trade_pnls.append(pnl)
        equity += trade_value - commission

    # Compute metrics
    final_equity = equity
    total_pnl = final_equity - initial_capital
    total_return_pct = (total_pnl / initial_capital) * 100

    # Max drawdown from equity curve
    equity_arr = np.array(equity_curve)
    cummax = np.maximum.accumulate(equity_arr)
    drawdowns = (cummax - equity_arr) / cummax
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Win rate and trade stats
    total_trades = len(trade_pnls)
    profitable = sum(1 for p in trade_pnls if p > 0)
    win_rate = profitable / total_trades if total_trades > 0 else 0.0
    avg_pnl = np.mean(trade_pnls) if trade_pnls else 0.0
    best_pnl = max(trade_pnls) if trade_pnls else 0.0
    worst_pnl = min(trade_pnls) if trade_pnls else 0.0

    # Sharpe ratio (annualized)
    if len(equity_curve) > 1:
        equity_returns = np.diff(equity_arr) / equity_arr[:-1]
        mean_ret = float(np.mean(equity_returns))
        std_ret = float(np.std(equity_returns, ddof=1)) if len(equity_returns) > 1 else 0.0
        daily_rf = 0.05 / 252
        sharpe = (mean_ret - daily_rf) / std_ret * np.sqrt(252) if std_ret > 0 else 0.0
    else:
        sharpe = 0.0
        equity_returns = np.array([])

    # Annualized return
    n_days = len(timestamps) if timestamps else 252
    annualized_return = ((final_equity / initial_capital) ** (365 / max(n_days, 1))) - 1

    # Volatility (annualized)
    vol = float(np.std(equity_returns, ddof=1) * np.sqrt(252)) if len(equity_returns) > 1 else 0.0

    return ReplayResult(
        trades=trades,
        equity_curve=equity_curve,
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_pnl=total_pnl,
        total_return_pct=total_return_pct,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        win_rate=win_rate,
        total_trades=total_trades,
        profitable_trades=profitable,
        avg_trade_pnl=avg_pnl,
        best_trade_pnl=best_pnl,
        worst_trade_pnl=worst_pnl,
        annualized_return=annualized_return,
        volatility=vol,
    )
