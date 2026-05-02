# Gold Long Setup Scanner – Hermes Agent Brief

**Goal**  
Create a Python cronjob/script that automatically scans for the **exact gold long trading setup** described in the r/Forexstrategy post.  
Only alert when **all** conditions are met. Most days should produce zero signals.

---

## Instruments
- **Gold**: `GC=F` (Gold futures) or `XAUUSD=X` (spot as fallback)
- **DXY**: `^DXY` or `DX-Y.NYB`

---

## Timezone
All logic must use **UTC**.

---

## Exact Rules (ALL must be TRUE for valid signal)

### 1. DXY Bias Check (Daily)
- DXY daily close < 50-period EMA  
- If false → skip (no longs)

### 2. Asian Session Range
- Asian session: **00:00 – 08:00 UTC**
- Record the **low** of this session (previous day’s range)

### 3. London Sweep
- London liquidity window: **08:00 – 12:00 UTC**
- Price must **sweep below** the Asian low (make a lower low)
- Then show reversal (close back above the low or form a higher low)

### 4. 15m FVG Confirmation
- Switch to **15-minute** timeframe
- A **bullish Fair Value Gap** must form **after** the sweep
- Definition: `low[current] > high[2]` (classic 3-candle imbalance)
- Recommended filter: FVG size > 0.3 × ATR(14)

### 5. Risk Management (Strict)
- **Entry**: Current close (or midpoint of FVG)
- **Stop Loss**: Below Asian low or most recent swing low
- **Take Profit**: Exactly **3× risk** (fixed 3RR – never move TP)

---

## Cronjob Requirements

- **Frequency**: Every **15 minutes** during 07:00–18:00 UTC
- **Output**: Only send alert when **full setup** is valid
- **Alert Content** (example):

```
🟢 GOLD LONG SETUP DETECTED
Time: 2026-05-02 10:45 UTC
DXY Bias: Bearish ✓
Asian Low Swept: YES ✓
FVG Confirmed: YES ✓
Current Price: 2345.60
Entry: 2345.60
SL: 2338.40 (Risk: 7.20)
TP: 2367.20 (3RR)
```

---

## Technical Notes for Implementation

- Use `yfinance`, `pandas`, `pandas_ta`
- Handle sessions with UTC datetime
- Persist previous Asian low between runs (simple JSON or variable)
- Prevent duplicate alerts for the same setup
- Silent when no setup (as per original strategy)

---

**Philosophy** (from original post)  
> “Nothing fancy — just structure, patience, and execution.  
> Most days I do nothing. Some days this prints Asian clean.”

---

**Ready for Hermes Agent**  
Pass this file directly. The logic is complete and unambiguous.