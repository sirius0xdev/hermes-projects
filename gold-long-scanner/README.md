# Gold Long Setup Scanner

Automated scanner for the r/Forexstrategy gold long trading setup.
Monitors DXY bias, Asian session range, London sweep, and 15m FVG confirmation.

## Files
- `gold_long_scanner.py` — Main scanner script (runs via Hermes cron every 15m)
- `BRIEF.md` — Original strategy specification

## Setup Conditions (ALL required)
1. DXY daily close < 50 EMA (bearish bias)
2. Asian session low (00:00–08:00 UTC) established
3. London sweep below Asian low (08:00–12:00 UTC) + reversal
4. Bullish 15m FVG after sweep (size > 0.3×ATR)

## Risk Management
- **Entry**: Current market price
- **SL**: Asian low - 0.1% buffer
- **TP**: Fixed 3× risk (3RR)

## State
Runtime state persisted to `gold_scanner_state.json` (gitignored).

## Cron
Scheduled via Hermes Agent cronjob — runs every 15m, alerts only on full setup.
