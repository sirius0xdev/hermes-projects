#!/usr/bin/env python3
"""
Gold Long Setup Scanner
Scans for the exact r/Forexstrategy gold long setup.
Only alerts when ALL conditions are met.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_ta as ta
import yfinance as yf

STATE_PATH = "/opt/data/scripts/gold_scanner_state.json"

def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"last_asian_low": None, "last_asian_date": None, "alerted_setups": []}

def save_state(state: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

def get_asian_session_low(gold_1h: pd.DataFrame, utc_now: datetime) -> float | None:
    """
    Asian session: 00:00-08:00 UTC.
    Use today's Asian if it's >= 08:00 UTC (session complete),
    otherwise use yesterday's Asian session.
    """
    # Determine the Asian session date
    if utc_now.hour >= 8:
        # Today's Asian session is complete
        session_date = utc_now.strftime("%Y-%m-%d")
    else:
        # Use yesterday's Asian session
        session_date = (utc_now - timedelta(days=1)).strftime("%Y-%m-%d")

    session_start = pd.Timestamp(f"{session_date} 00:00:00", tz="UTC")
    session_end = pd.Timestamp(f"{session_date} 08:00:00", tz="UTC")

    mask = (gold_1h.index >= session_start) & (gold_1h.index < session_end)
    session_data = gold_1h.loc[mask]

    if len(session_data) < 2:
        return None

    asian_low = session_data["Low"].min()
    return asian_low

def check_dxy_bearish() -> bool:
    """DXY daily close < 50 EMA"""
    try:
        dxy = yf.download("^DXY", period="3mo", interval="1d", auto_adjust=False, silent=True)
        if dxy is None or len(dxy) < 51:
            return False
        ema50 = ta.ema(dxy["Close"], length=50)
        current_ema = ema50.iloc[-1]
        current_close = dxy["Close"].iloc[-1]
        return current_close < current_ema
    except Exception:
        return False

def check_london_sweep(gold_1h: pd.DataFrame, utc_now: datetime, asian_low: float) -> bool:
    """
    London sweep: 08:00-12:00 UTC
    Price sweeps below Asian low, then reverses (closes back above or forms higher low)
    """
    if utc_now.hour < 8:
        return False

    session_start = pd.Timestamp(f"{utc_now.strftime('%Y-%m-%d')} 08:00:00", tz="UTC")
    session_end = pd.Timestamp(f"{utc_now.strftime('%Y-%m-%d')} 12:00:00", tz="UTC")
    # If current time < 12:00, only look at data up to now
    actual_end = min(session_end, utc_now)

    mask = (gold_1h.index >= session_start) & (gold_1h.index <= actual_end)
    london_data = gold_1h.loc[mask]

    if len(london_data) < 2:
        return False

    # Check if any candle wick went below Asian low
    swept = (london_data["Low"] < asian_low).any()
    if not swept:
        return False

    # Find the sweep candle and check for reversal after
    sweep_indices = london_data[london_data["Low"] < asian_low].index

    for sweep_idx in sweep_indices:
        # Check candles after the sweep
        after_sweep = london_data.loc[sweep_idx:]
        if len(after_sweep) < 2:
            continue
        # Reversal: subsequent close above Asian low, or higher low pattern
        last_close = after_sweep["Close"].iloc[-1]
        if last_close > asian_low:
            return True
        # Also check: last candle low > sweep candle low (higher low)
        sweep_low = after_sweep["Low"].iloc[0]
        last_low = after_sweep["Low"].iloc[-1]
        if last_low > sweep_low and last_close > after_sweep["Open"].iloc[-1]:
            return True

    return False

def find_bullish_fvg(gold_15m: pd.DataFrame, utc_now: datetime, after_hour: int = 8) -> dict | None:
    """
    Bullish FVG on 15m: low[current] > high[2] (3-candle pattern)
    Must form after London sweep starts (after 08:00 UTC)
    Also filter: FVG size > 0.3 * ATR(14)
    """
    # Only look at candles after after_hour
    cutoff = pd.Timestamp(f"{utc_now.strftime('%Y-%m-%d')} {after_hour:02d}:00:00", tz="UTC")
    recent = gold_15m.loc[gold_15m.index >= cutoff].copy()

    if len(recent) < 16:  # Need enough for ATR(14)
        return None

    # Calculate ATR(14)
    atr = ta.atr(recent["High"], recent["Low"], recent["Close"], length=14)

    # Find FVGs: low[i] > high[i-2] for consecutive candles
    # Classic bullish FVG: candle[i] low > candle[i-2] high
    lows = recent["Low"].values
    highs = recent["High"].values
    atrs = atr.values

    results = []
    for i in range(2, len(recent)):
        if pd.isna(atrs[i]):
            continue
        fvg_size = lows[i] - highs[i - 2]
        if fvg_size > 0:  # Bullish FVG
            min_size = 0.3 * atrs[i]
            if fvg_size > min_size:
                results.append({
                    "timestamp": recent.index[i].strftime("%Y-%m-%d %H:%M UTC"),
                    "fvg_top": highs[i - 2],   # high[i-2] is top of gap
                    "fvg_bottom": lows[i],       # low[i] is bottom of gap
                    "fvg_size": fvg_size,
                    "fvg_mid": (highs[i - 2] + lows[i]) / 2,
                    "atr": atrs[i],
                })

    # Return the most recent FVG
    return results[-1] if results else None

def main():
    utc_now = datetime.now(timezone.utc)
    hour = utc_now.hour

    # Only run during active window 07:00-18:00 UTC
    if hour < 7 or hour >= 18:
        print("SLEEP")
        return

    state = load_state()

    # 1. DXY Bias Check
    dxy_bearish = check_dxy_bearish()
    if not dxy_bearish:
        print("SLEEP")
        return

    # Fetch Gold data
    try:
        gold_1h = yf.download("GC=F", period="5d", interval="1h", auto_adjust=False, silent=True)
        gold_15m = yf.download("GC=F", period="5d", interval="15m", auto_adjust=False, silent=True)
        if gold_1h is None or gold_15m is None or len(gold_1h) < 10 or len(gold_15m) < 20:
            print("SLEEP")
            return
    except Exception:
        print("SLEEP")
        return

    # 2. Asian Session Low
    asian_low = get_asian_session_low(gold_1h, utc_now)
    if asian_low is None:
        print("SLEEP")
        return

    # Update state
    today_str = utc_now.strftime("%Y-%m-%d")
    if state.get("last_asian_date") != today_str:
        state["last_asian_low"] = asian_low
        state["last_asian_date"] = today_str
        state["alerted_setups"] = []  # Reset alerts for new day
    save_state(state)

    # 3. London Sweep
    swept = check_london_sweep(gold_1h, utc_now, asian_low)
    if not swept:
        print("SLEEP")
        return

    # 4. 15m FVG Confirmation
    fvg = find_bullish_fvg(gold_15m, utc_now, after_hour=8)
    if fvg is None:
        print("SLEEP")
        return

    # Check if already alerted on this FVG
    fvg_key = fvg["timestamp"]
    if fvg_key in state.get("alerted_setups", []):
        print("SLEEP")
        return

    # 5. Calculate risk management
    current_price = gold_15m["Close"].iloc[-1]
    entry = current_price  # current close
    # SL below Asian low with small buffer (0.1% to avoid right-on-the-line stops)
    sl = asian_low - (asian_low * 0.001)
    risk = entry - sl
    if risk <= 0:
        print("SLEEP")
        return
    tp = entry + (3 * risk)  # 3RR fixed

    # Mark as alerted
    state.setdefault("alerted_setups", []).append(fvg_key)
    save_state(state)

    # Format alert
    alert = (
        f"\U0001f7e2 GOLD LONG SETUP DETECTED\n"
        f"Time: {utc_now.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"DXY Bias: Bearish \u2713\n"
        f"Asian Low Swept: YES \u2713\n"
        f"FVG Confirmed: YES \u2713\n"
        f"Current Price: {current_price:.2f}\n"
        f"Entry: {entry:.2f}\n"
        f"SL: {sl:.2f} (Risk: {risk:.2f})\n"
        f"TP: {tp:.2f} (3RR)"
    )
    print(alert)

if __name__ == "__main__":
    main()
