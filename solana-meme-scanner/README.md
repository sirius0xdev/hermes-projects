# Solana Meme Coin Volume Spike Scanner

Scans for trending Solana meme coins with volume spikes and on-chain safety filters. Alerts only on clean setups.

## How It Works
1. **Discovery**: Searches DexScreener for trending meme pairs (10 keywords)
2. **Volume Spike**: Filters pairs with volume >3× average
3. **Price Momentum**: Requires +5% minimum in 1h
4. **On-Chain Safety**: Solana RPC checks mint/freeze authority (built-in RugCheck)
5. **Alert**: Only fires when all conditions pass

## Filters
| Check | Threshold |
|---|---|
| 24h Volume | > $25,000 |
| Liquidity | > $5,000 |
| Market Cap | $50k – $20M |
| 1h Change | > +5% |
| Mint Authority | Must be revoked |
| Freeze Authority | Must be revoked |

## Setup (Risk Management)
- **Entry**: Current market price
- **SL**: -10% (standard meme coin stop)
- **TP**: +30% (3RR fixed)

## Data Sources
- **DexScreener**: Pair discovery (free, search API)
- **Solana RPC**: On-chain safety checks (free, mainnet)
- **Jupiter API**: Swap execution (future)

## State
Runtime state in `solana_meme_state.json` (gitignored).

## Cron
Runs every 15m via Hermes Agent cronjob, alerts on Telegram.
