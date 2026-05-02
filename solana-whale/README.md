# 🐋 Solana Whale Tracker

Monitors large on-chain fund movements on the Solana mainnet in real-time via WebSocket streaming, or replays recent blocks in scan mode.

## Features

- **Real-time WebSocket streaming** — subscribes to Solana logs for token and SOL transfers
- **Historical scanning** — replays recent transactions to find whale movements
- **Multi-token support** — monitors 8 major SPL tokens (USDC, USDT, PYTH, Bonk, JUP, mSOL, ETH, WIF) + native SOL
- **USD valuation** — fetches live prices from CoinGecko, uses peg for stablecoins
- **Watchlist** — alerts for any movement involving tracked wallets
- **Deduplication** — avoids duplicate alerts from multi-instruction transactions
- **SOL transfer pairing** — matches senders with receivers (no spurious "network" labels)
- **Rate-limit resilient** — exponential backoff for 429s on public RPC
- **JSONL logging + CSV export**

## Setup

```bash
# Dependencies
pip3 install --break-system-packages solana solders websockets httpx rich click pyyaml

# Configure
cp config.yaml config.local.yaml   # edit RPC endpoint, thresholds, tokens, wallets
```

## Usage

### Scan recent transactions

```bash
# Scan last 500 transactions
python3 tracker.py scan --txs 500

# Scan last 1000 from custom config
python3 tracker.py scan --txs 1000 --config config.local.yaml
```

### Stream real-time alerts

```bash
# Start real-time monitoring
python3 tracker.py stream

# With custom config
python3 tracker.py stream --config config.local.yaml
```

Press `Ctrl+C` to stop.

### Export logged alerts to CSV

```bash
python3 tracker.py export --output whale_alerts.csv
```

## Configuration (`config.yaml`)

### RPC Endpoints

```yaml
rpc:
  https: "https://api.mainnet-beta.solana.com"     # Public (rate-limited)
  wss: "wss://api.mainnet-beta.solana.com"
```

**For production use**, replace with a paid RPC for higher rate limits:

| Provider | Free Tier | Paid |
|----------|-----------|------|
| Helius | 3M CU/day | https://mainnet.helius-rpc.com/?api-key=KEY |
| QuickNode | 60 req/s | https://solana-mainnet.quiknode.pro/YOUR_KEY/ |
| Triton | 100 CU/s | Custom endpoints |
| Alchemy | 250 req/s | https://solana-mainnet.g.alchemy.com/v2/YOUR_KEY |

### Thresholds

```yaml
thresholds:
  sol_usd: 50000        # Alert for SOL transfers >= $50,000
  spl_usd: 100000       # Alert for SPL token transfers >= $100,000
  top_n: 20             # Max transfers shown in summary table
```

### Monitored Tokens

Add any SPL token by its mint address, symbol, and decimals:

```yaml
monitored_tokens:
  - mint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    symbol: "USDC"
    decimals: 6
    price_usd: 1.0          # Optional: hardcoded peg (for stablecoins)
  - mint: "YourTokenMintAddressHere"
    symbol: "MYTOKEN"
    decimals: 6
```

### Watched Wallets

Get alerts for any movement from/to these addresses, regardless of value:

```yaml
watched_wallets:
  - address: "YourAddressHere"
    label: "My Wallet"
```

### Behavior

```yaml
behavior:
  log_file: "/opt/data/solana-whale/log.jsonl"
  max_history: 5000           # Max alerts kept in memory
  rpc_delay_seconds: 3.0      # Seconds between RPC calls
  max_retries: 5              # Retry attempts on failure
  backoff_base: 5             # Base seconds for exponential backoff on 429
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  WebSocket   │────▶│  Signature   │────▶│  Transaction│
│  Subscribe   │     │  Queue       │     │  Fetch (RPC)│
└─────────────┘     └──────────────┘     └──────┬──────┘
    │                                            │
    │       ┌────────────────────────────────────┘
    │       ▼
    │  ┌─────────────────┐     ┌────────────┐
    │  │  Tx Parser      │────▶│  Whale     │
    │  │  • SPL transfers│     │  Alerts    │
    │  │  • SOL pairs    │     └──────┬─────┘
    │  └─────────────────┘            │
    │                                  ▼
    │                          ┌───────────────┐
    │                          │  Formatter    │
    │                          │  • Console    │
    │                          │  • JSONL log  │
    │                          │  • CSV export │
    │                          └──────────────┘
```

## Whale Alert Levels

- 🐋🐋🐋 $10M+ — Mega whale
- 🐋 $1M+ — Large whale
- 🐳 $500K+ — Medium whale
- 🐬 $100K+ — Small whale
- 🐟 Below threshold — Tracked via watchlist

## Output

### Real-time alerts (stream mode)

```
🐋 $1,250,000
   15,000.00 SOL
   5Tzk…Lcxz → CF6t…sy6
   [sol_transfer] 3xKp…mNqV
   2026-05-02 15:42:18 UTC
```

### Summary table

Shows the top N whale movements with token, amount, USD value, from/to addresses.

### Log file (`log.jsonl`)

Each line is a JSON object:

```json
{"timestamp":"2026-05-02 15:42:18 UTC","signature":"...","amount":15000,"token_symbol":"SOL","usd_value":1250000,"from_address":"...","to_address":"...","tx_type":"sol_transfer"}
```

## Notes

- **Public RPC limitations**: The default `api.mainnet-beta.solana.com` is heavily rate-limited (429s). For production, use a paid RPC endpoint.
- **Price data**: SOL from CoinGecko, stablecoins have hardcoded pegs, other tokens fetched from CoinGecko by token ID mapping.
- **Token 2022**: The parser supports both SPL Token (`Tokenkeg…`) and Token-2022 (`TokenzQd…`) programs.
