# Free Market Data API/SDK Comparative Survey
> **Date:** 2026-05-18 | **For:** Private DeFi trading dashboard → Redis cache + Kafka streaming

---

## Executive Summary

This report ranks **12 free market data sources** across **6 evaluation dimensions** for a microservice trading platform. The sources are grouped into:

| Category | APIs Evaluated | Top Pick |
|---|---|---|
| **Scraping / Multi-Asset** | yfinance | yfinance *(broadest coverage, but fragile)* |
| **Stocks / Forex / Multi-Asset** | Alpha Vantage, Polygon, Twelve Data, EODHD, Finnhub | **Finnhub** (best free tier for real-time quotes) |
| **Crypto** | CoinGecko, CoinMarketCap, Binance Public, OKX Public, CryptoCompare | **Binance Public API** (only true real-time, no auth) |
| **Futures / Commodities** | CME Group API, Nasdaq Data Link (Quandl/CHRIS), yfinance futures, Metals-API, OpenBB SDK | **OpenBB SDK + custom roll-stitcher** (best free pipeline) |

**Bottom-line recommendation:** No single free provider covers all asset classes with production-grade reliability. A **composite free-tier stack** works best:

| Pipeline Layer | Primary Source | Role |
|---|---|---|
| Real-time Kafka streaming | **Binance WebSocket** + **Finnhub WebSocket** | Crypto + equity tick/trade events |
| Delayed quote snapshots (Redis cache) | **CoinGecko** + **Finnhub** + **Twelve Data** | Global prices, forex, commodities |
| Historical candle backfill | **Polygon** + **Yahoo/yfinance** + **CME delayed API** | 1m–1d bars, futures EOD |
| Options / exotic data | **yfinance** (last resort) | Options chains, obscure tickers |
| Futures continuous contracts | **Custom roll-stitcher** + raw front-month feeds | OI-based roll detection, price-adjusted series |

---

## 1. yfinance (Scraping Baseline)

| Dimension | Details |
|---|---|
| **Rate Limits** | No published limits. Practical: ~1,000–2,000 req/hr per IP before 429/403 blocks. Cloudflare WAF enforces soft bans. |
| **Data Freshness** | Equities: ~15 min delayed. Futures: ~10–15 min delayed. Forex/Crypto: ~5–10 min delayed. NOT suitable for real-time. |
| **Reliability** | **Poor.** Breaks 1–3 weeks per Yahoo platform update. Hundreds of open GitHub issues. Endpoint rotation causes silent empty DataFrames. |
| **Auth** | None. Cookie/crumb token managed internally. IP blocks require proxy rotation. |
| **SDK (Python)** | `yfinance` (ranaroussi/yfinance). ~5M+ monthly PyPI downloads. Returns pandas DataFrames. Minimal type hints, README-based docs. Python only. |
| **Data Format** | pandas DataFrame (MultiIndex Date × OHLCV + Adj Close). Separate calls for dividends, splits, earnings, news, options chains. |
| **Covered Assets** | **Broadest single source:** equities, ETFs, futures (GC=F, CL=F, ES=F), forex (EURUSD=X), crypto (BTC-USD), options, mutual funds, bonds. |
| **Pros** | • Zero config, zero auth<br>• Widest asset coverage<br>• Great for backtesting and exploration<br>• Handles contract rolls for futures automatically (`=F` suffix) |
| **Cons** | • Structurally fragile (undocumented upstream)<br>• Silent failures (empty DataFrames without error)<br>• IP bans under moderate load<br>• Heavy pandas dependency adds overhead<br>• No real-time streaming<br>• Open interest unreliable/missing for futures |

**Verdict:** Best as **tertiary fallback** and for exploration/backtesting. Not reliable enough as a primary ingestion source for production Kafka pipelines. Use with aggressive caching (Redis TTL = 15+ min), exponential backoff, and schema validation gates.

---

## 2. Finnhub (Best Free Tier for Equities)

| Dimension | Details |
|---|---|
| **Rate Limits** | 60 calls/min. Most generous of the REST-only free tiers. Soft daily cap under heavy load. |
| **Data Freshness** | **Real-time stock quotes** on free tier (unlike most competitors). Forex/Crypto: 1–5 min delayed. |
| **Reliability** | Good retail-grade uptime. Occasional downtime at market opens/earnings seasons. Popular among algo-trading community. |
| **Auth** | Free signup, API key via email. Simple header: `X-Finnhub-Token`. |
| **SDK Quality** | • **Python:** `finnhub` (official, REST + WebSocket, actively updated)<br>• **Node.js:** `finnhub` (official, first-class promise/async support) |
| **Data Format** | JSON. OHLCV candle arrays, real-time quote snapshots `{c, h, l, o, pc, t}`, news sentiment, insider trading data. |
| **Covered Assets** | US equities, crypto, forex, mutual funds. Options requires paid. Limited futures. |
| **Pros** | • Real-time quotes on free tier<br>• Highest free REST rate limit (60/min)<br>• Official Python + Node.js SDKs<br>• WebSocket available (free: 1 stream/connection)<br>• Clean, stable schema<br>• News sentiment and insider data included |
| **Cons** | • Free WebSocket limited to 1 connection<br>• Minimal futures/options coverage<br>• No tick-level data on free<br>• Paid tiers needed for true institutional quality |

**Verdict:** **Primary for equity real-time quotes.** Push `market.quotes.raw` to Kafka, cache in Redis with ~15s TTL. Best free-tier SDK quality in Python and Node.

---

## 3. Polygon.io (Best Schema Quality)

| Dimension | Details |
|---|---|
| **Rate Limits** | 5 REST calls/min. Very strict. Effectively limits to batch/scheduled jobs, not high-frequency polling. |
| **Data Freshness** | US Equities: 5-min delayed. Options/Forex/Crypto/Indices: 15-min delayed. Real-time **requires paid.** |
| **Reliability** | **Excellent.** Highly regarded for clean schema, consistent uptime. WebSocket infrastructure robust (but free gets REST only or very limited WS). |
| **Auth** | Free signup, instant API key via dashboard. |
| **SDK Quality** | • **Python:** `polygon-api-client` (official, well-documented, async support)<br>• **Node.js:** `@polygon.io/client-js` (official, typed, actively maintained) |
| **Data Format** | JSON. Clean, standardized OHLCV. Aggregation bars (1min–year). Trade + quote + NBBO snapshots. Tick data requires paid. |
| **Covered Assets** | US equities, options, forex, crypto, indices. No commodities/futures on free. |
| **Pros** | • Best-in-class schema cleanliness<br>• Official SDKs in Python + Node.js<br>• Excellent data quality (no scraping)<br>• Very reliable infrastructure<br>• Aggregation bars pre-computed |
| **Cons** | • Only 5 calls/min on free — very restrictive<br>• No real-time on free tier (5–15 min delay)<br>• No futures/commodities<br>• Upgrade path expensive ($29+/month) |

**Verdict:** **Primary for historical candle ingestion.** Schedule a 5–10 min cron to pull 1m/5m bars, write to `market.candles` Kafka topic. Excellent data quality but rate limited for anything real-time.

---

## 4. Twelve Data (Best Multi-Asset Coverage)

| Dimension | Details |
|---|---|
| **Rate Limits** | 8 calls/min. ~800 calls/day. Moving toward credit-based system (~200–300 historical pulls/month effective). Enforced via X-RateLimit headers. |
| **Data Freshness** | 15-min delayed for equities, FX, crypto. Real-time is add-on, not free. |
| **Reliability** | Good. Occasional latency spikes during high volatility. Free tier lacks priority routing. |
| **Auth** | Free signup, instant API key. |
| **SDK Quality** | • **Python:** `twelvedata` (official, sync/async + WebSocket support)<br>• **Node.js:** `twelve-data-js` (community, basic REST only) |
| **Data Format** | JSON. Standard OHLCV, quote snapshots, technical indicators, bid/ask spread. Tick data not on free. |
| **Covered Assets** | **Broad:** US + select international stocks, forex, crypto, ETFs, commodities (spot pricing), indices. Continuous futures front-month supported. Open interest and volume included. |
| **Pros** | • Broadest free multi-asset coverage<br>• Official Python SDK with WebSocket support<br>• Commodities pricing included (spot)<br>• Specific expiry codes for futures contracts<br>• 8 calls/min is workable for scheduled polling |
| **Cons** | • 15-min delay limits real-time usefulness<br>• Node.js SDK is community-only<br>• Rate enforcement tightening (moving to credits)<br>• WebSocket requires paid tier |

**Verdict:** **Best for multi-asset scheduled REST pulls into Kafka.** Good for populating Redis caches with current prices across asset classes.

---

## 5. Binance Public API (Only True Real-Time for Crypto)

| Dimension | Details |
|---|---|
| **Rate Limits** | REST: 1,200 requests/min/IP (auto-weighted). `/klines` weight = 1. **WebSocket:** 5 req/sec/connection, max 5 connections/IP. Outbound: 10k msg/sec. |
| **Data Freshness** | **True real-time** (millisecond latency via WebSocket). REST: ~50–200ms from matching engine. |
| **Reliability** | **Top-tier globally.** Handles $10B+ daily volume. Occasional announced maintenance. Best-in-class for production. |
| **Auth** | **None required** for `/api/v3/*` public endpoints. IP-based rate limiting only. |
| **SDK Quality** | • **Python:** `binance-connector-python` (official, asyncio, production-ready, type-hinted)<br>• **Python (legacy):** `python-binance` (community, popular but less active)<br>• Node.js: community wrappers (no official) |
| **Data Format** | JSON. Strict decimal precision strings (no float rounding). Orderbook: `{bids: [[price, qty]], asks: [...]}`. Trades, klines (1m–1w), 24h ticker. |
| **Covered Assets** | Spot, USDT-M Futures, COIN-M Futures, Options. Full depth orderbook (100/500/1000 levels). Aggregated + individual trades. |
| **Pros** | • Only truly free real-time market data (WebSocket)<br>• Extremely generous rate limits (1,200/min REST)<br>• No auth needed for public endpoints<br>• Covers spot + futures (perpetuals)<br>• Official async Python SDK<br>• Millisecond-latency orderbook + trade streams |
| **Cons** | • Crypto only — no equities/forex/fiat data<br>• Requires exchange-specific parsing<br>• Node.js lacks official SDK<br>• Price/qty as strings (must use Decimal, not float) |

**Verdict:** **Primary for crypto real-time Kafka streaming.** Subscribe to `<symbol>@trade` and `<symbol>@depth` WebSocket streams. Serialize to JSON/Protobuf, publish to Kafka topics `market.trades.*` and `market.orderbook.*`. No comparable free source exists.

---

## 6. OKX Public API (Best Free Futures/Derivatives)

| Dimension | Details |
|---|---|
| **Rate Limits** | REST: 20 requests/sec/IP. WebSocket: ~60 subscriptions/connection, free tier. |
| **Data Freshness** | **Real-time** (millisecond). |
| **Reliability** | High. Major Tier-1 exchange infrastructure. |
| **Auth** | None for public endpoints. |
| **SDK Quality** | • **Python:** `okx-python` (official, asyncio, well-documented)<br>• Node.js: generic HTTP clients |
| **Data Format** | JSON. Similar to Binance — spot + perpetual + futures data. Depth, trades, tickers. |
| **Covered Assets** | Spot + Derivatives (Perpetuals, Futures, Options). Excellent futures depth data. |
| **Pros** | • Real-time MS-latency data<br>• Strong derivatives/perpetuals coverage<br>• Official async Python SDK<br>• Generous WebSocket subscription limits |
| **Cons** | • Crypto only<br>• Node.js SDK lacking<br>• Less volume/liquidity than Binance |

**Verdict:** **Strong alternative/backup to Binance** for crypto futures and perpetuals data. Use as fallback if Binance WS drops.

---

## 7. Alpha Vantage (Best for Fundamentals, Poor for Real-time)

| Dimension | Details |
|---|---|
| **Rate Limits** | ~25 requests/day for new keys (severely tightened). Legacy keys may have higher limits. |
| **Data Freshness** | End-of-day (EOD) for most data. Intraday (1min/5min) available but delayed. No real-time on free. |
| **Reliability** | Generally stable REST. Throttlles/returns empty payloads on free limit breach. No SLA. |
| **Auth** | Free signup, email verification, API key. |
| **SDK Quality** | • **Python:** `alpha_vantage` (community, widely used, async available)<br>• **Node.js:** Multiple community wrappers, no official SDK |
| **Data Format** | JSON. Standard OHLCV + metadata, adjusted close, volume, dividends, technical indicators. No ticks. |
| **Covered Assets** | Global equities, FX, crypto, technical indicators, fundamental data. No futures/options. |
| **Pros** | • Excellent fundamental/financial statement data<br>• Good technical indicator pre-computation<br>• Global equity coverage |
| **Cons** | • Only 25 requests/day — too restrictive for any streaming<br>• No real-time data<br>• Node.js SDK ecosystem fragmented<br>• No futures coverage |

**Verdict:** **Use only for daily fundamental enrichment and EOD backfills.** Not viable for any real-time or intraday pipeline. Reserve for Redis slow data updates (daily or less).

---

## 8. EODHD / End of Day Historical Data (Best for Global Historical)

| Dimension | Details |
|---|---|
| **Rate Limits** | 20 API calls/day. Strict. |
| **Data Freshness** | Delayed 15–30 min intraday. Primary focus: EOD/historical. Not real-time. |
| **Reliability** | Very stable for historical pulls. Low free-tier traffic = fewer outages. No SLA. |
| **Auth** | Free signup, API key. |
| **SDK Quality** | • **Python:** `eodhd` (official, lightweight REST wrapper)<br>• **Node.js:** No official SDK |
| **Data Format** | JSON + CSV. OHLCV, adjusted close, splits, dividends. Extensive fundamentals (financial statements, ownership, ESG). |
| **Covered Assets** | Global equities (60+ exchanges), ETFs, bonds, macro indicators, forex, commodities (spot), crypto. |
| **Pros** | • Widest historical data breadth (60+ exchanges)<br>• Excellent fundamental data<br>• CSV download option for bulk backfills<br>• Bond/macro data included |
| **Cons** | • Only 20 calls/day — barely covers a watchlist<br>• No real-time or streaming<br>• Node.js lacks SDK<br>• Intraday unreliable |

**Verdict:** **Best for weekly/monthly historical backfills and fundamental data enrichment.** Not for any streaming or near-real-time use.

---

## 9. CoinGecko Demos API (Best Global Crypto Aggregator)

| Dimension | Details |
|---|---|
| **Rate Limits** | ~10–30 calls/min (IP-based, strict). ~10,000 calls/month hard cap. Temporary IP bans on excess. |
| **Data Freshness** | Aggregated global average. Updated every 1–5 minutes depending on endpoint. Historical OHLCV at 5m/1h/1d intervals. |
| **Reliability** | 99.5%+ uptime historically. CDN-backed. Very stable REST infrastructure. |
| **Auth** | Free signup + API key required. Header: `x-cg-demo-api-key`. Unauthenticated requests deprecated. |
| **SDK Quality** | • **Python:** `pycoingecko` (community, widely adopted, lightweight sync)<br>• Node.js: community wrappers |
| **Data Format** | JSON. `{name, current_price, market_cap, ...}`. OHLCV: nested `[timestamp, price]` arrays. |
| **Covered Assets** | Spot prices, market cap, supply, 24h volume, historical charts, exchange listings. |
| **Pros** | • Aggregated across exchanges (no single-exchange bias)<br>• Reliable CDN-backed infrastructure<br>• Consistent JSON schema<br>• 10–30 calls/min sufficient for cache refresh |
| **Cons** | • No orderbook, no individual trades, no derivatives<br>• REST-only, no streaming<br>• Strict monthly caps<br>• 1–5 min delay, not real-time |

**Verdict:** **Primary for Redis cache population** of global crypto prices, market cap, metadata. Schedule REST polling every 60s. Upsert into `token:{id}` Redis hashes with matching TTL.

---

## 10. CoinMarketCap Free API (Alternative Crypto Aggregator)

| Dimension | Details |
|---|---|
| **Rate Limits** | 333 calls/day (~14/hour). 10,000 calls/month hard cap. Resets monthly. HTTP 429 on breach. |
| **Data Freshness** | Aggregated, ~1–5 min refresh. Historical: ~1h granularity on free. |
| **Reliability** | Enterprise-grade. Used by major wallets/trackers. |
| **Auth** | Free registration, API key. Header: `X-CMC_PRO_API_KEY`. |
| **SDK Quality** | • **Python:** `coinmarketcap` (official, minimal)<br>• `cmc-api-wrapper` (community). Simple requests wrappers. |
| **Data Format** | JSON. Verbose but well-documented. `{data: {1: {quote: {USD: {price, volume_24h, ...}}}}}`. |
| **Covered Assets** | Spot prices, market cap dominance, historical quotes, latest listings, fiat conversion. |
| **Pros** | • Enterprise reliability<br>• Market cap dominance data<br>• Verbose, well-documented schema |
| **Cons** | • Much tighter daily limit (333/day vs. CoinGecko's 10–30/min)<br>• Coarser historical granularity<br>• No orderbook/trades/derivatives<br>• REST-only |

**Verdict:** **Secondary to CoinGecko.** Use only for metrics CoinGecko doesn't provide (dominance, specific fiat conversions). 333/day is too restrictive for frequent polling.

---

## 11. CME Group Market Data API (Exchange-Native Futures)

| Dimension | Details |
|---|---|
| **Rate Limits** | 15-min delayed data free after registration. ~60–100 req/min on free tier. Real-time requires exchange licensing + redistribution fees. |
| **Data Freshness** | 15-min delayed (free). Real-time is paid. |
| **Reliability** | Exchange-grade uptime (>99.9%). Free endpoints may throttle during peak load. |
| **Auth** | API Key + OAuth2/JWT token. Registration with exchange data vendor agreement required. |
| **SDK Quality** | • **Python:** `cme-market-data` (official, enterprise-leaning)<br>• Node.js: unofficial/community only |
| **Data Format** | JSON/REST for historical/delayed. FIX/ITCH binary for real-time streaming (paid). |
| **Covered Assets** | CME/COMEX/NYMEX/CBOT futures & options. Front-month, expiration series, calendar spreads. |
| **Pros** | • Direct from exchange — authoritative source<br>• Verified OI/volume data<br>• Free delayed feed available<br>• No schema drift (exchange-controlled API) |
| **Cons** | • No continuous contracts (manual stitching required)<br>• 15-min delay on free<br>• Registration + vendor agreement needed<br>• Python SDK is enterprise-complex<br>• Options on futures on separate endpoints |

**Verdict:** **Best authoritative source for futures OI/volume cross-validation.** Use alongside yfinance or Twelve Data to verify contract roll dates and volume data. Build roll-stitching logic on top.

---

## 12. OpenBB SDK (Open-Source Multi-Source Aggregator)

| Dimension | Details |
|---|---|
| **Rate Limits** | Inherits limits from underlying providers (yfinance, FRED, Polygon, etc.) that OpenBB aggregates. No additional limits itself. |
| **Data Freshness** | Depends on configured providers. yfinance: ~15 min delayed. FRED: EOD. Polygon: per-polygon-tier. |
| **Reliability** | Good. Open-source platform, ~20k+ GitHub stars. Provider failures are handled gracefully with fallback logic. |
| **Auth** | OpenBB Free tier API key. Individual providers require their own keys. |
| **SDK Quality** | • **Python:** `openbb` (official, comprehensive, extensible)<br>• Node.js: not supported |
| **Data Format** | Standardized schemas across providers. Python SDK returns typed objects. |
| **Covered Assets** | **Extremely broad:** equities, ETFs, forex, crypto, futures, options, macro data, news, alternative data. Aggregates 50+ providers. |
| **Pros** | • Single SDK for 50+ providers<br>• Automatic fallback between providers<br>• Extensible — add custom providers<br>• Active open-source community<br>• Standardizes data schemas across sources |
| **Cons** | • Inherits rate limits from all underlying providers<br>• Heavy dependency surface<br>• Python only<br>• Free tier API keys rate-limited<br>• More overhead than direct provider calls |

**Verdict:** **Best for initial exploration and multi-source aggregation.** Use in development to prototype across providers. For production, consider direct provider calls to reduce overhead and have explicit fallback control (circuit breakers per provider).

---

## 13. Nasdaq Data Link / Quandl CHRIS (Historical Continuous Futures)

| Dimension | Details |
|---|---|
| **Rate Limits** | Free: 20 API calls/day, 50 MB/month. Heavily restricted. |
| **Data Freshness** | EOD delayed (T+1). |
| **Reliability** | High infrastructure quality. Free tier effectively deprecated for active use. |
| **Auth** | API Key required. |
| **SDK Quality** | • **Python:** `quandl` (official, stable, long-standing)<br>• Node.js: generic HTTP clients |
| **Data Format** | JSON/CSV. Datatable API. Standardized roll-adjusted columns. |
| **Covered Assets** | CHRIS database: contiguous front/back-month continuous futures for CME, ICE, LIFFE, etc. Options limited. OI/volume included. |
| **Pros** | • Historically the gold standard for free continuous futures<br>• Pre-computed roll adjustments<br>• OI/volume included<br>• CSV bulk download available |
| **Cons** | • Only 20 calls/day — essentially deprecated for active use<br>• EOD only, not intraday<br>• Free tier barely functional for any streaming/polling<br>• Paid tier required for production-scale usage |

**Verdict:** **Historical backfill only and barely usable even for that** due to 20 calls/day limit. Do not use for any near-real-time pipeline.

---

## Ranked Comparison Summary

### By Overall Production Value (Free Tier)

| Rank | API | Best For | Real-time? | Rate Limit | Python SDK | Node.js SDK | Futures? | Crypto? | Forex? | Equities? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Binance Public** | Crypto streaming | YES ✓ | 1200/min REST, generous WS | ⭐⭐⭐ official | ⭐⭐ community | USDT/COIN-M futures | ⭐⭐⭐ | — | — |
| 2 | **Finnhub** | Equities real-time | YES ✓ | 60/min | ⭐⭐⭐ official | ⭐⭐⭐ official | Limited | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| 3 | **Polygon.io** | Historical candles | NO (5–15min delay) | 5/min | ⭐⭐⭐ official | ⭐⭐⭐ official | — | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| 4 | **Twelve Data** | Multi-asset breadth | NO (15min delay) | 8/min | ⭐⭐⭐ official | ⭐⭐ community | ⭐⭐ continuous | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| 5 | **OKX Public** | Crypto derivatives | YES ✓ | 20/sec REST | ⭐⭐⭐ official | ⭐☆ generic | Perpetuals/futures | ⭐⭐⭐ | — | — |
| 6 | **OpenBB SDK** | Aggregation/prototype | Depends | Provider-dependent | ⭐⭐⭐ official | — | Via providers | Via providers | Via providers | Via providers |
| 7 | **CoinGecko** | Crypto cache/metadata | NO (1–5 min) | 10–30/min | ⭐⭐ community | ⭐⭐ community | — | ⭐⭐ | — | — |
| 8 | **CME Group API** | Futures OI/volume | NO (15min delay) | 60–100/min | ⭐⭐ official | ⭐ community | ⭐⭐⭐ | — | — | — |
| 9 | **CoinMarketCap** | Crypto alt-metrics | NO (1–5 min) | 333/day | ⭐⭐ official | ⭐⭐ community | — | ⭐⭐ | — | — |
| 10 | **yfinance** | Fallback/exploration | NO (15min delay) | ~2000/hr (soft) | ⭐⭐⭐ community | ⭐⭐ community | ⭐⭐ (auto-roll) | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| 11 | **EODHD** | Global historical | NO (EOD focus) | 20/day | ⭐⭐ official | — | — | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| 12 | **Alpha Vantage** | Fundamentals/EOD | NO (EOD) | 25/day | ⭐⭐ community | ⭐⭐ community | — | ⭐⭐ | ⭐⭐ | ⭐⭐ |
| 13 | **Quandl/CHRIS** | Futures historical | NO (EOD) | 20/day | ⭐ official | — | ⭐⭐⭐ | — | — | — |

---

## Architecture Recommendations for Redis + Kafka

### Recommended Free-Tier Stack

```
┌─────────────────────────────────────────────────────────────┐
│                   Market Data Ingestion                      │
├──────────────────┬──────────────────┬───────────────────────┤
│  Binance WS      │  Finnhub WS      │  Twelve Data REST    │
│  (crypto trades) │  (equity quotes) │  (multi-asset bars)  │
└────────┬─────────┴────────┬─────────┴───────────┬───────────┘
         │                  │                     │
         ▼                  ▼                     ▼
   ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐
   │ Kafka:      │  │ Kafka:      │  │ Kafka:               │
   │ market.     │  │ market.     │  │ market.candles.*     │
   │ trades.btc  │  │ quotes.nvda │  │ (5-min intervals)    │
   │ market.     │  │ market.     │  └─────────────┬────────┘
   │ orderbook.* │  │ quotes.aapl │                 │
   └─────────────┘  └─────────────┘                 │
                                                    ▼
                                              ┌──────────┐
                                              │  Redis   │
                                              │  cache   │
                                              │ (latest  │
                                              │  prices) │
                                              └──────────┘
```

### Ingestion Patterns by Asset Class

| Asset Class | Primary Free Source | Data Type | Kafka Topic Pattern | Redis Key Pattern | Poll Interval |
|---|---|---|---|---|---|
| **Crypto (spot)** | Binance WebSocket | Trades, orderbook, klines | `market.trades.btc` | `crypto:btc:price` | Real-time (push) |
| **Crypto (perpetuals)** | Binance/OKX WebSocket | Trades, depth | `market.futures.btc-perp` | `futures:btc-perp:price` | Real-time (push) |
| **US Equities** | Finnhub REST | Quote snapshots | `market.quotes.aapl` | `equity:aapl:price` | 15–60 seconds |
| **US Equities (bars)** | Polygon REST | 1m/5m aggregate bars | `market.candles.aapl` | `equity:aapl:candle:5m` | 5–10 minutes |
| **Forex** | Twelve Data REST | Quote + OHLCV | `market.fx.eurusd` | `fx:eurusd:price` | 1–5 minutes |
| **Commodities (futures)** | yfinance + CME delayed | OHLCV + OI | `market.futures.gc` | `futures:gc:price` | 5–15 minutes |
| **Global crypto (metadata)** | CoinGecko REST | Price, market cap, volume | N/A (cache only) | `token:btc:meta` | 60 seconds |

### Production Hardening for Free Tiers

1. **Circuit breakers per provider** (`pybreaker`): Trip after 3 consecutive failures, reset after 60s.
2. **Redis write-through cache:** Always write to Redis first, then publish to Kafka. If Kafka is down, data persists in Redis for replay.
3. **Dead-letter queue:** Un-parseable or schema-violating messages go to Kafka `market.dlq` topic — never silently drop data.
4. **Rate limit tracking:** Track `x-rate-limit-remaining` headers (where available) and back off proactively.
5. **Provider fallback chains:** If primary API fails, try secondary (e.g., Finnhub → Polygon → yfinance for equity prices).
6. **Decimal precision:** Always use `Decimal` or string parsing for prices from Binance/OKX/any exchange. Never use `float` for price/quantity in trading logic.
7. **Continuous futures contract stitching:** Do NOT rely on pre-rolled data from free providers. Build a lightweight roll-stitcher microservice:
   - Detect roll date via Open Interest crossover
   - Calculate adjustment factor: `adj = close[t-1] / open[t]`
   - Apply cumulative adjustment to historical series
   - Publish to `market.futures.continuous.gc` Kafka topic

---

## Data Quality Warnings

| Source | Known Issue | Impact |
|---|---|---|
| **yfinance** | Silent empty DataFrames during endpoint breaks | Kafka publishes nothing — no error signal |
| **yfinance** | Adj Close recalculated retroactively | Historical candles shift after splits/dividends |
| **yfinance** | Futures OI missing/NaN at roll dates | Volume/OI-based strategies break |
| **Alpha Vantage** | 25/day limit silently enforced | Requests fail with no rate-limit headers |
| **Polygon** | 5/min hard cap — requests queued/dropped | Need explicit token bucket limiter |
| **Binance** | Prices as decimal strings — not floats | `float()` conversion loses precision for trading |

---

## Appendix: SDK Install Commands

```bash
# Python ecosystem
pip install yfinance
pip install finnhub-python
pip install polygon-api-client
pip install twelvedata
pip install binance-connector
pip install okx
pip install pycoingecko
pip install coinmarketcap
pip install alpha_vantage
pip install eodhd
pip install openbb
pip install quandl

# Node.js ecosystem
npm install @polygon.io/client-js
npm install finnhub
# Note: yfinance, Binance, OKX, OpenBB — no official Node SDKs
```

---

*Research conducted 2026-05-18. API rate limits and free-tier offerings change frequently — verify current limits on provider pricing pages before production deployment.*
