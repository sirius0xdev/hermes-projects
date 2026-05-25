# Trading Execution SDKs Research Report

*Generated: 2026-05-17*
*Purpose: Evaluation for private DeFi trading dashboard — execution focus*

---

## 1. CCXT — Universal Crypto Exchange Library

### Overview
CCXT (CryptoCurrency eXchange Trading Library) is the most widely adopted cross-exchange library in the industry. It provides a **unified API** across 100+ centralized exchanges (CEXs) with identical method signatures regardless of the underlying exchange.

**Verified NPM metadata:** `ccxt@4.5.54` | MIT License | `https://ccxt.com` | Last published: 2026-05-15

### 1.1 Supported Chains / Markets
- **Not chain-specific** — CCXT connects to **centralized exchange APIs** (REST + WebSocket), not blockchains
- **100+ CEXs supported** including: Binance, Coinbase Pro, OKX, Kraken, Bybit, KuCoin, Bitfinex, Huobi/HTX, Gate.io, Bitget, MEXC, and many more
- Supports **spot, margin, futures, swap** markets where available per exchange
- Each exchange declares its own `has` capability matrix (e.g., `has.createOrder`, `has.createStopLimitOrder`)

### 1.2 Auth Flow
- **API Key + Secret** (REST): Standard HMAC-SHA256 signing per exchange
- **API Key + Secret + Passphrase:** For exchanges requiring it (e.g., Coinbase, OKX, Gate.io)
- **WebSocket auth:** Separate authentication via exchange-specific WS login messages
- **No wallet required** — CEX-native authentication
- All auth handled internally; you simply pass `{ apiKey, secret, password? }` to the exchange constructor

```python
exchange = ccxt.binance({
    'apiKey': '...',
    'secret': '...',
})
```

### 1.3 Order Types
Extensive support per exchange's unified interface:
- **Market** — market buy/sell
- **Limit** — limit buy/sell
- **Stop-loss** — trigger-on-price
- **Stop-limit** — stop-triggered limit
- **Take-profit** — target-exit orders
- **Trailing stop** — dynamic stop loss
- **Reduce-only** — position reduction mode
- **IOC/FOK/GTC** — time-in-force params where supported
- **Post-only** — maker-only orders

*Note: Available order types vary by exchange — check `exchange.has` flags at runtime.*

### 1.4 Latency Characteristics
- **REST:** 50ms–500ms round-trip depending on exchange API region and rate limits
- **WebSocket (watchTickers/watchOrderBook):** ~10–50ms for real-time streams
- **Rate limiting:** Built-in rate-limiting per exchange; configurable via `rateLimit` parameter and `enableRateLimit` flag
- **Co-location benefit:** Running in AWS Tokyo/Singapore/Virginia near exchange servers significantly reduces latency
- **Not HFT-grade** — CCXT prioritizes compatibility over microsecond latency

### 1.5 Mainnet vs Testnet Support
- **Most exchanges** offer testnet / sandbox modes
- **Binance:** Testnet available (`exchange.setSandboxMode(true)`)
- **OKX, Bybit, Bitfinex:** Full sandbox environments
- **~30+ exchanges** have documented testnet support
- CCXT provides `setSandboxMode(true)` to automatically switch to testnet URLs per exchange

### 1.6 Documentation Quality
- **Official docs:** https://docs.ccxt.com/ — **excellent**, comprehensive
- **Examples directory:** `ccxt/examples/` with working scripts in Python/JS/PHP
- **CCXT Pro manual:** WebSocket documentation in detail
- **Exchange capability matrix:** Every exchange documents its unified method support
- **GitHub wiki:** Extensive troubleshooting and FAQ coverage
- **Community:** Very active GitHub issues, Discord community

**Links:**
- Docs: https://docs.ccxt.com/
- GitHub: https://github.com/ccxt/ccxt (100K+ stars)
- Pro (WebSocket): https://github.com/ccxt/ccxt/wiki/ccxt.pro

### 1.7 SDK Maturity
| Metric | Value |
|--------|-------|
| NPM Package | `ccxt@4.5.54` (1988+ versions published) |
| NPM Weekly Downloads | ~500K+ |
| PyPI Downloads | ~2M+ monthly |
| GitHub Stars | ~100K+ |
| Last Update | **2026-05-15** (actively maintained) |
| License | MIT |
| Languages | JavaScript/TypeScript, Python, PHP, C#, Go |
| Age | Since 2017 |

### 1.8 Free Tier / API Limits
- **CCXT itself is free** (MIT license) — no licensing fees
- **Exchange rate limits apply:** Each exchange has its own limits (typically 1–10 requests/second for free tier)
- **CCXT Pro (WebSocket):** Commercial license required for production use at scale (free for personal use)
- **Open-source REST methods:** Fully free, no restrictions

### 1.9 Execution Capability Assessment for DeFi Dashboard
| Strength | Weakness |
|----------|----------|
| Unified API across 100+ exchanges | Not DeFi/Dex — CEX only |
| Battle-tested, 100K+ stars | REST latency ~50-500ms |
| Excellent documentation | WebSocket features require Pro license |
| Active daily development | Order types vary by exchange |
| Multi-language support | Rate limits per exchange still apply |

**Verdict:** Excellent CEX execution layer. **Not suitable as sole execution tool for DeFi** — pair with DEX SDKs for on-chain trades. Ideal for fiat on/off-ramp and CEX arbitrage.

---

## 2. Uniswap SDKs (@uniswap/sdk-core, v3-sdk, v4-sdk)

### Overview
The Uniswap SDK suite is the official TypeScript library for interacting with Uniswap V2, V3, and V4 protocols. It focuses on route computation, swap quotation, and transaction construction — **not order books** (Uniswap uses AMM model).

**Verified NPM metadata:**
- `@uniswap/sdk-core@7.14.0` | MIT
- `@uniswap/v3-sdk@3.30.0` | MIT
- `@uniswap/v4-sdk@2.1.0` | MIT
- GitHub: https://github.com/Uniswap/sdks

### 2.1 Supported Chains / Markets
**All Ethereum-compatible (EVM) chains running Uniswap contracts:**
- **Ethereum Mainnet** (L1)
- **Arbitrum One & Nova**
- **Optimism** (OP Mainnet)
- **Polygon PoS**
- **Base** (Coinbase L2)
- **BNB Chain** (formerly BSC)
- **Celo**
- **Avalanche (C-Chain)**
- **Other EVM chains** with deployed Uniswap V3/V4 pool addresses

**V3 pools:** Concentrated liquidity — any ERC-20 token pair can have a pool at multiple fee tiers (0.01%, 0.05%, 0.3%, 1%)
**V4:** Hooks architecture, custom pool types (deployed May 2025 on Ethereum mainnet)

### 2.2 Auth Flow
- **Wallet signatures required** (no API keys)
- **MetaMask/WalletConnect/Coinbase Wallet** or embedded wallet via `ethers.js`/`viem`
- **Transaction signing:** Standard EIP-1559 transactions via `provider.getSigner()` or `viem` wallet client
- **Multicall:** Swap routing often batches through Multicall contract (no extra auth)
- **Permit (EIP-2612):** Optional gasless approval for token allowances
- **No exchange account** — purely wallet-to-contract interaction

### 2.3 Order Types
**Uniswap does NOT have traditional order types** — it's an Automated Market Maker:

| Feature | Description |
|---------|-------------|
| **Swap** | Direct token exchange at current pool price |
| **Quoting** | Get price impact and expected output before swap |
| **Multi-hop routing** | SDK computes optimal path across pools |
| **Range orders (V3)** | LP positions within specific price ranges |
| **V4 Hooks** | Custom limit-order-like behavior via pool hooks |
| **Limit orders (third-party)** | Built by other protocols (UniswapX, CowSwap, 1inch) |

**Important:** For limit-order-like functionality on Uniswap, you'd use:
- **UniswapX** (off-chain order matching, on-chain settlement)
- **CowSwap Protocol** (batch auctions)
- **Limit order protocols built on top of V3/V4 hooks**

### 2.4 Latency Characteristics
- **Quote computation:** <10ms (local SDK calculation)
- **Transaction broadcast:** ~2–12 seconds to confirmation (Ethereum L1) or ~1–3 seconds on L2s
- **Block time dependent:** Ethereum ~12s, Arbitrum ~2s, Base ~2s, Polygon ~2s
- **No WebSocket stream** for order status — must poll `eth_getTransactionReceipt` or use The Graph/subgraph
- **Slippage protection** is built into transaction parameters (slippage tolerance)

### 2.5 Mainnet vs Testnet Support
| Environment | Status |
|------------|--------|
| **Ethereum Mainnet** | Full support |
| **L2 Mainnets** (Arbitrum, Optimism, Base, Polygon) | Full support |
| **Ethereum Sepolia** | V3 pools deployed, SDK supports |
| **Arbitrum Sepolia** | Partial support |
| **Optimism Sepolia** | Partial support | |
| **Base Sepolia** | V3 deployed, SDK supports |
| **Mumbai/Polygon Amoy** | Limited/Deprecated |

Testnet support requires manually configuring chain IDs and pool addresses in the SDK.

### 2.6 Documentation Quality
- **Official docs:** https://docs.uniswap.org/ — **good but scattered**
- **SDK reference:** Inline JSDoc in source code, no dedicated API reference
- **GitHub README:** Covers basic setup
- **Community docs:** Strong — Uniswap has excellent blog posts, tutorials, and YouTube content
- **TypeScript:** Fully typed, IntelliSense friendly

**Links:**
- Docs: https://docs.uniswap.org/
- GitHub: https://github.com/Uniswap/sdks
- V3 Subgraph: https://thegraph.com/explorer/subgraphs/3h7Vk2q3k...
- Interface: https://app.uniswap.org/ (reference implementation)

### 2.7 SDK Maturity
| Package | Version | Weekly Downloads | GitHub Stars (mono-repo) | Last Update |
|---------|---------|-----------------|-------------------------|------------|
| @uniswap/sdk-core | 7.14.0 | ~500K+ | ~20K+ (Uniswap/interface) | 2026-05 |
| @uniswap/v3-sdk | 3.30.0 | ~250K+ | | 2026-05 |
| @uniswap/v4-sdk | 2.1.0 | ~50K+ | | 2026-05 |

| Metric | Value |
|--------|-------|
| License | MIT |
| Language | TypeScript (Node.js + browser) |
| Age | V2 SDK since 2019, V3 SDK since 2021, V4 SDK since 2024 |

### 2.8 Free Tier / API Limits
- **Entirely free** — on-chain protocol, no API keys needed
- **Gas fees apply** for all transactions (swap, approve, liquidity management)
- **Quoting is free** — SDK calculates routes locally, no API calls needed
- **RPC rate limits** depend on your Ethereum node provider (Infura/Alchemy/QuickNode)
- **No commercial restrictions** — MIT license

### 2.9 Execution Capability Assessment for DeFi Dashboard
| Strength | Weakness |
|----------|----------|
| Free, no API limits | No traditional order types (AMM only) |
| TypeScript ecosystem | High gas on Ethereum L1 |
| Multi-chain EVM support | Transaction confirmation latency (2-12s) |
| Fully typed, excellent DX | No WebSocket for trade status |
| V4 hooks enable custom logic | V4 still early adoption |

**Verdict:** **Essential for any DeFi trading dashboard on EVM chains.** Excellent for swap execution, route optimization, and price computation. Pair with a limit-order protocol (CowSwap, UniswapX) for advanced order types.

---

## 3. dYdX SDK (v4/Chain)

### Overview
dYdX v4 is a **dedicated Cosmos-based perpetual futures exchange** running its own blockchain (dYdX Chain). It operates an order book model for perpetual contracts with deep liquidity and fast execution.

**Verified NPM metadata:** `dydx@1.0.13` | AGPL-3.0 License | `https://github.com/dydxprotocol/v4-clients`

*Note: dYdX v3 is deprecated and sunset. Only v4/Chain is actively maintained.*

### 3.1 Supported Chains / Markets
- **dYdX Chain** — a standalone Cosmos appchain (NOT Ethereum L2)
- **Perpetual futures** on: BTC, ETH, SOL, DOGE, AVAX, LINK, UNI, SUI, APE, TIA, SEI, NEAR, INJ, and 30+ more perpetual pairs
- **Cross perpetuals, isolated perpetuals** — single collateral pool or per-position margin
- **No spot trading** — perpetuals only
- **No cross-chain support** — all trading happens on dYdX Chain

### 3.2 Auth Flow
Dual authentication layers:

**1. dYdX API Authentication (REST/WS):**
- **Private API key** generated in dYdX account settings
- **ECDSA signatures** — requests signed with Ethereum wallet private key
- **API key + secret + passphrase** pattern for REST endpoints
- **JWT tokens** for session management

**2. On-Chain Authentication (Cosmos):**
- **Cosmos wallet** (dYdX-specific wallet derived from Ethereum key)
- **CometBFT/Cosmjs signing** for on-chain transactions (place/cancel orders)
- **Message signing** via `@cosmjs/proto-signing`

```typescript
import { LocalWallet } from '@dydxprotocol/v4-local-wallet';
const wallet = LocalWallet.fromMnemonic(MNEMONIC, BECH32_PREFIX);
```

### 3.3 Order Types
dYdX v4 is a full **order book exchange** with advanced order types:

| Order Type | Supported | Notes |
|------------|-----------|-------|
| **Market** | Yes | Immediate execution |
| **Limit** | Yes | Maker/taker pricing |
| **Stop-Market** | Yes | Trigger at stop price, fill at market |
| **Stop-Limit** | Yes | Trigger at stop price, limit order fills |
| **Take-Profit Market** | Yes | Auto-close at target |
| **Take-Profit Limit** | Yes | Limit order triggered by profit target |
| **Trailing Stop** | Via conditional orders | |
| **IOC** | Yes | Immediate-or-cancel |
| **FOK** | Yes | Fill-or-kill |
| **Good Til Time (GTT)** | Yes | Expiry time in ms |
| **Good Til Block (GTB)** | Yes | Expiry block height |
| **Post-Only** | Yes | Maker-only enforcement |
| **Reduce-Only** | Yes | Position reduction only |
| **Short-Term Orders** | Yes | On-chain, block-confirmed |
| **Stateful Orders** | Yes | Longer-lived, off-chain book |

### 3.4 Latency Characteristics
- **API (REST):** ~30–100ms round-trip
- **WebSocket (real-time):** ~10–30ms for order book updates
- **On-chain execution (Short-Term orders):** ~0.6s block time (dYdX Chain has 0.5–1s blocks)
- **Order matching:** Off-chain matching engine → on-chain settlement
- **Order placement latency:** ~50–200ms end-to-end for API orders
- **Not HFT-grade** but faster than typical L2 DEX due to dedicated chain

### 3.5 Mainnet vs Testnet Support
| Environment | Status |
|------------|--------|
| **dYdX Mainnet** | Full production support |
| **dYdX Testnet** | Full testnet available, faucet for test tokens |
| **Local devnet** | Available via Docker compose |
| **Noble testnet** | For USDC transfers testing |

**Testnet configuration:**
```typescript
client = new IndexerClient('https://indexer.v4testnet.dydx.exchange');
composer = new Composer(); // transaction composer
```

### 3.6 Documentation Quality
- **Official docs:** https://docs.dydx.exchange/ — **good, comprehensive**
- **API reference:** OpenAPI spec available for REST endpoints
- **SDK README:** Covers basic setup and examples
- **Developer portal:** https://dydx.exchange/developers
- **GitHub wiki:** Limited — most docs on the main site
- **Community:** Active Discord, Telegram, community forums
- **v3 docs are deprecated** — ensure you're reading v4 docs

**Links:**
- Docs: https://docs.dydx.exchange/
- API Reference: https://docs.dydx.exchange/api
- GitHub v4 Clients: https://github.com/dydxprotocol/v4-clients
- GitHub: https://github.com/dydxprotocol/v4-chain

### 3.7 SDK Maturity
| Metric | Value |
|--------|-------|
| NPM Package | `dydx@1.0.13` |
| License | AGPL-3.0 |
| Language | TypeScript |
| GitHub Stars (v4-clients) | ~200+ |
| GitHub Stars (v4-chain) | ~500+ |
| NPM Weekly Downloads | ~5K+ |
| Last Update | 2026-05 (active development) |
| Age | v4 launched 2023 |

**Note:** Smaller community than CCXT/Uniswap but dedicated to perpetual trading.

### 3.8 Free Tier / API Limits
- **Trading is free** — no SDK license fees
- **No API key cost** — generate free API keys from dYdX account
- **Maker/taker fees apply:**
  - Maker: ~0.00%–0.02%
  - Taker: ~0.03%–0.05%
- **Rate limits:**
  - Public endpoints: ~10–30 requests/second
  - Private endpoints: ~5–10 requests/second
  - WebSocket: Unlimited streams, but connection limits apply
- **Staking required** for some governance features, not for trading
- **No KYC** — non-custodial, self-custody wallet

### 3.9 Execution Capability Assessment for DeFi Dashboard
| Strength | Weakness |
|----------|----------|
| Full order book with 30+ perpetual pairs | Perpetuals only, no spot trading |
| Advanced order types (Stop, TP, trailing) | Cosmos-based — different ecosystem |
| Fast block time (~0.6s) | AGPL-3.0 license (copyleft) |
| Non-custodial, on-chain settlement | Smaller dev community |
| Sub-account support for risk management | No cross-chain trading |

**Verdict:** **Excellent for perpetual futures execution** on a dedicated chain. Best-in-class DeFi derivatives orderbook. Add to dashboard for leveraged trading. Note the AGPL-3.0 license if distributing derivatives of the SDK.

---

## 4. Injective SDK (@injectivelabs/sdk-ts)

### Overview
Injective is a Cosmos-based blockchain optimized for DeFi and derivatives. The official TypeScript SDK provides access to **spot trading, derivatives, and cross-chain functionality**.

**Verified NPM metadata:** `@injectivelabs/sdk-ts@1.19.12` | Apache-2.0 License | `https://github.com/InjectiveLabs/injective-ts` | Last updated: 2026-05-15

### 4.1 Supported Chains / Markets
- **Injective Chain** — Cosmos-based L1 optimized for DeFi
- **Spot markets:** 100+ trading pairs (INJ, ETH, BTC, SOL, etc.)
- **Derivatives markets:** Perpetual contracts on major assets
- **Cross-chain markets** via IBC:
  - Ethereum assets (via Peggy bridge)
  - Solana assets
  - Cosmos ecosystem tokens
  - BNB Chain assets
- **Exchange markets** managed by the Injective exchange module
- **Order book model** — not AMM

### 4.2 Auth Flow
Multi-layered authentication:

**1. Wallet Signing:**
- **CosmJS wallet** for Cosmos-native transactions
- **Ethereum wallet (MetaMask)** via Ethereum-compatible injection
- **Ledger hardware wallet** support
- **Private key** or mnemonic-based signing

```typescript
import { PrivateKey } from '@injectivelabs/sdk-ts';
const privateKey = PrivateKey.fromMnemonic(MNEMONIC);
const address = privateKey.toBech32();
```

**2. EIP-712 Signing (for Ethereum-originated messages):**
- Messages signed in EIP-712 format for Ethereum wallet compatibility
- Converts to Cosmos tx for broadcast

**3. Exchange Auth (for trading):**
- No separate exchange API keys needed
- All orders are on-chain transactions signed by the wallet
- **Batch signing** for multiple operations

### 4.3 Order Types
Full order book functionality:

| Order Type | Supported | Notes |
|------------|-----------|-------|
| **Market** | Yes | Immediate best-price fill |
| **Limit** | Yes | Maker/taker pricing |
| **Stop-Market** | Yes | Trigger → market fill |
| **Stop-Limit** | Yes | Trigger → limit order |
| **Take-Profit** | Via conditional | Close at target price |
| **Conditional Orders** | Yes | Trigger-based execution |
| **Reduce-Only** | Yes | Close positions only |

**Note:** Fewer exotic order types than dYdX but covers all essential types.

### 4.4 Latency Characteristics
- **Block time:** ~1–2 seconds (Cosmos Tendermint consensus)
- **API response:** ~50–200ms for REST endpoints
- **Transaction confirmation:** 1–2 blocks (~1–4 seconds)
- **Indexer (query):** Separate indexer node for historical data — faster reads
- **WebSocket:** Real-time order book and trade updates available
- **Optimized for DeFi speed** — faster than Ethereum L1

### 4.5 Mainnet vs Testnet Support
| Environment | Status |
|------------|--------|
| **Injective Mainnet** | Full production support |
| **Injective Testnet** | Full testnet, faucet available |
| **Local node** | Available via Docker |

**Testnet configuration:**
```typescript
import { TESTNET_CHAIN_ID, getNetworkEndpoints } from '@injectivelabs/networks';
const endpoints = getNetworkEndpoints(TESTNET_CHAIN_ID);
```

### 4.6 Documentation Quality
- **Official docs:** https://docs.injective.network/ — **comprehensive but complex**
- **SDK docs:** API reference via GitHub README and inline JSDoc
- **API documentation:** gRPC + REST endpoints documented
- **Developer tutorials:** Extensive examples for common operations
- **Community:** Active Telegram, Discord, forum

**Links:**
- Docs: https://docs.injective.network/
- GitHub: https://github.com/InjectiveLabs/injective-ts
- API Reference: https://docs.injective.network/#injective-api
- SDK Examples: https://github.com/InjectiveLabs/injective-ts/tree/master/examples

### 4.7 SDK Maturity
| Metric | Value |
|--------|-------|
| NPM Package | `@injectivelabs/sdk-ts@1.19.12` |
| License | Apache-2.0 |
| Language | TypeScript |
| NPM Weekly Downloads | ~10K+ |
| GitHub Stars (injective-ts) | ~200+ |
| GitHub Stars (monorepo) | ~1K+ |
| Last Update | 2026-05-15 (very active) |
| Age | Since 2020 |
| Ecosystem Packages | sdk-ts, utils, networks, wallet-ts, exceptions, ts-types |

### 4.8 Free Tier / API Limits
- **SDK is free** — Apache-2.0 license, permissive
- **No API key costs** — wallet-based auth
- **Trading fees:**
  - Maker: ~0.00% (often zero for makers)
  - Taker: ~0.05%–0.10%
- **Gas fees:** Very low (~$0.01–$0.10 per transaction)
- **RPC/Indexer rate limits:**
  - Public endpoints: generous but may throttle at very high volumes
  - Private indexer: available for paid plans
- **No KYC** for on-chain trading

### 4.9 Execution Capability Assessment for DeFi Dashboard
| Strength | Weakness |
|----------|----------|
| Apache-2.0 license (permissive) | Order types less comprehensive than dYdX |
| 100+ spot + derivatives pairs | Cosmos ecosystem — smaller than EVM |
| Cross-chain via IBC | Smaller dev community |
| Low gas fees | Complex auth flow (multiple patterns) |
| Active development (v1.19.x) | Documentation can be overwhelming |

**Verdict:** **Strong contender for spot + derivatives trading** with excellent fee structure. Permissive Apache-2.0 license is ideal for commercial projects. Cross-chain IBC support is a unique advantage.

---

## 5. Avalanche DEX SDKs — Trader Joe & Pangolin

### Overview
Two primary Decentralized Exchanges on Avalanche:

**Trader Joe:** The dominant DEX on Avalanche with a V2-style AMM, LB (Liquidity Book) V2.1 architecture, and multi-chain deployment.

**Pangolin:** Community-driven DEX forked from Uniswap V2, smaller volume but still active on Avalanche.

### 5.1 Trader Joe

#### Supported Chains / Markets
- **Avalanche C-Chain** (primary)
- **Arbitrum**
- **BNB Chain**
- **Ethereum**
- **Base**
- **Other EVM chains** via deployment
- **Liquidity Book V2.1:** Bin-based AMM with discrete price steps
- **V2 AMM:** Traditional Uniswap V2-style pools
- Supports **ERC-20 token pairs**

**Verified NPM metadata:**
- `@traderjoe-xyz/sdk@5.0.16` | MIT
- `@traderjoe-xyz/sdk-core@2.0.13` | MIT
- `@traderjoe-xyz/sdk-v2@3.0.30` | MIT
- GitHub: https://github.com/traderjoe-xyz/joe-sdks

#### Auth Flow
- **Wallet signatures** only (EVM-compatible wallets)
- **MetaMask/WalletConnect/Injected wallet** for browser
- **ethers.js or viem** for transaction signing
- **Router contracts:** Interact via Trader Joe Router (not direct pool)
- **No API keys** — purely on-chain

#### Order Types
**AMM-based (no order book):**
- **Swap** — direct token exchange
- **Route computation** — multi-hop via SDK
- **LP management** — add/remove liquidity
- **Liquidity Book** — bin-based LP positions (unique to Trader Joe)
- **No limit orders natively** — requires aggregators for that

#### Latency Characteristics
- **Quote computation:** <5ms (local SDK)
- **Transaction confirmation:** ~2 seconds (Avalanche block time)
- **AVAX subnets:** ~1-2 second finality
- **Slippage tolerance** configured in SDK before tx submission

#### Mainnet vs Testnet Support
| Environment | Status |
|------------|--------|
| **Avalanche Mainnet (C-Chain)** | Full support |
| **Avalanche Fuji Testnet** | Full support, faucet available |
| **Arbitrum, BNB Mainnets** | Supported via SDK |

#### Documentation Quality
- **GitHub README:** Moderate quality
- **Docs:** https://docs.traderjoexyz.com/ — decent but not comprehensive
- **TypeScript:** Good type definitions
- **Community:** Solid on Avalanche ecosystem forums
- **API reference:** Limited — primarily code-driven

**Links:**
- Docs: https://docs.traderjoexyz.com/
- GitHub: https://github.com/traderjoe-xyz/joe-sdks
- Interface: https://traderjoexyz.com/

#### SDK Maturity
| Metric | Value |
|--------|-------|
| Packages | @traderjoe-xyz/sdk@5.0.16, sdk-core@2.0.13, sdk-v2@3.0.30 |
| License | MIT |
| Language | TypeScript |
| NPM Weekly Downloads | ~10K+ (combined) |
| GitHub Stars | ~300+ (joe-sdks repo) |
| Last Update | 2025-10 to 2025-11 |
| Age | Since 2021 |

#### Free Tier / API Limits
- **Fully free** — MIT license, no API keys
- **Gas fees** for transactions (AVAX chain, very low fees ~$0.01)
- **Trading fees:** 0.3% for V2 pools, variable for LB pools
- **RPC limits** depend on node provider (public Avalanche RPC has rate limits)

### 5.2 Pangolin

#### Supported Chains / Markets
- **Avalanche C-Chain** (primary)
- **Other EVM chains** where Pangolin has deployed
- **Uniswap V2 fork** — standard pair model
- **ERC-20 token pairs**

**Verified NPM metadata:**
- `pangolin-sdk@1.0.0` | MIT
- GitHub: https://github.com/thanhnguyennguyen/pangolin-sdk
- Based on `@uniswap/v2-core` architecture

#### Auth Flow
- **Wallet signatures** (MetaMask/injected wallet)
- **ethers.js** for signing
- **Router contract** interaction
- **No API keys** — purely on-chain

#### Order Types
**Standard AMM (Uniswap V2 fork):**
- **Swap** — token exchange via Router
- **LP management** — add/remove liquidity
- **Route computation** — multi-hop swaps
- **No advanced order types**

#### Latency Characteristics
- **Quote computation:** <5ms
- **Transaction confirmation:** ~2 seconds (Avalanche)
- **Standard Uniswap V2 path** — well-understood performance profile

#### Mainnet vs Testnet Support
| Environment | Status |
|------------|--------|
| **Avalanche Mainnet** | Supported |
| **Fuji Testnet** | Partial (limited liquidity) |

#### Documentation Quality
- **GitHub README:** Minimal
- **Docs:** Limited official documentation
- **Uniswap V2 docs** serve as reference (fork architecture)
- **Community:** Very small compared to Trader Joe

**Links:**
- GitHub: https://github.com/thanhnguyennguyen/pangolin-sdk
- Interface: https://app.pangolin.exchange/

#### SDK Maturity
| Metric | Value |
|--------|-------|
| Package | `pangolin-sdk@1.0.0` |
| License | MIT |
| Language | TypeScript/JavaScript |
| NPM Weekly Downloads | ~100 or less |
| GitHub Stars | ~10 or less |
| Last Update | 2022-03 (stale) |
| Age | Since 2021 |

#### Free Tier / API Limits
- **Fully free** — MIT license
- **Gas fees** for transactions
- **Trading fees:** 0.3% + 0.05% protocol fee

---

## Consolidated Comparison Matrix

### Execution Capability Summary

| Feature | CCXT | Uniswap | dYdX v4 | Injective | Trader Joe | Pangolin |
|---------|------|---------|---------|-----------|------------|----------|
| **Model** | Orderbook (CEX) | AMM | Orderbook | Orderbook | AMM | AMM |
| **Market Types** | Spot/Futures/Swap | Spot (swap) | Perpetuals | Spot+Derivs | Spot | Spot |
| **Limit Orders** | ✓ | ✗ (via 3rd party) | ✓ | ✓ | ✗ | ✗ |
| **Stop Orders** | ✓ (varies) | ✗ | ✓ | ✓ | ✗ | ✗ |
| **Take-Profit** | ✓ (varies) | ✗ | ✓ | ✓ | ✗ | ✗ |
| **Market Orders** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Post-Only** | ✓ | N/A | ✓ | ✓ | N/A | N/A |
| **Reduce-Only** | ✓ | N/A | ✓ | ✓ | N/A | N/A |
| **Free to Use** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **KYC Required** | Per exchange | No | No | No | No | No |
| **Languages** | JS/TS/Py/PHP/Go/C# | TypeScript | TypeScript | TypeScript | TypeScript | TS/JS |

### Maturity & Activity Comparison

| SDK | Weekly Downloads | GH Stars | Last Updated | License | Verdict |
|-----|-----------------|----------|-------------|---------|---------|
| **CCXT** | 500K+ | 100K+ | 2026-05-15 | MIT | ⭐⭐⭐⭐⭐ |
| **Uniswap SDKs** | 500K+/250K+ | 20K+ | 2026-05 | MIT | ⭐⭐⭐⭐⭐ |
| **dYdX v4** | 5K+ | 500+/200+ | 2026-05 | AGPL-3.0 | ⭐⭐⭐⭐ |
| **Injective** | 10K+ | 200+/1K+ | 2026-05-15 | Apache-2.0 | ⭐⭐⭐⭐ |
| **Trader Joe** | 10K+ | 300+ | 2025-11 | MIT | ⭐⭐⭐ |
| **Pangolin** | ~100 | ~10 | 2022-03 | MIT | ⭐ (stale) |

### Latency Comparison

| SDK | Quote/Calc | Execution | Settlement | Notes |
|-----|------------|-----------|------------|-------|
| **CCXT (WS)** | 10-50ms | 50-200ms | N/A (CEX) | Best for speed |
| **CCXT (REST)** | N/A | 50-500ms | N/A | Per-exchange variance |
| **Uniswap** | <10ms | 2-12s | Block time | EVM chain dependent |
| **dYdX v4** | 10-30ms | 30-100ms | 0.6s block | Dedicated chain |
| **Injective** | <10ms | 50-200ms | 1-2s block | Cosmos chain |
| **Trader Joe** | <5ms | ~2s | ~2s block | Avalanche fast |
| **Pangolin** | <5ms | ~2s | ~2s block | Avalanche fast |

---

## Recommendations for Private DeFi Trading Dashboard

### Tier 1 — Core Execution Layer (Implement These)

1. **CCXT** — For all CEX execution (Binance, Bybit, OKX, Kraken, etc.)
   - Unified API across 100+ exchanges
   - Best-in-class documentation and community
   - MIT license, free REST methods
   - **Use for:** fiat on/off-ramp, CEX spot, CEX futures

2. **Uniswap SDKs (v3 + v4)** — For EVM DEX execution
   - Essential for any EVM-based DeFi trading
   - Free, no restrictions
   - **Use for:** token swaps, LP management, price computation on Arbitrum, Base, Polygon, Avalanche

3. **dYdX SDK (v4)** — For perpetual futures
   - Best DeFi orderbook for derivatives
   - 30+ perp pairs, advanced order types
   - **Use for:** leveraged perpetual trading

### Tier 2 — Extended Coverage (Consider Adding)

4. **Injective SDK** — For cross-chain spot + derivatives
   - Apache-2.0 license (more permissive than dYdX)
   - 100+ markets, cross-chain IBC
   - **Use for:** markets not available on dYdX, spot trading on Injective

5. **Trader Joe SDK** — For Avalanche-native DeFi
   - Liquidity Book V2.1 unique to Avalanche
   - Only if you specifically need Avalanche DEX exposure

### Tier 3 — Skip

6. **Pangolin SDK** — Stale since 2022, low volume, superseded by Trader Joe

---

## Appendix: Quick Reference Links

| SDK | Docs | GitHub | NPM/PyPI |
|-----|------|--------|----------|
| CCXT | https://docs.ccxt.com/ | github.com/ccxt/ccxt | `ccxt` (npm/pip) |
| Uniswap SDKs | https://docs.uniswap.org/ | github.com/Uniswap/sdks | `@uniswap/sdk-core`, `@uniswap/v3-sdk`, `@uniswap/v4-sdk` |
| dYdX v4 | https://docs.dydx.exchange/ | github.com/dydxprotocol/v4-clients | `dydx` (npm) |
| Injective | https://docs.injective.network/ | github.com/InjectiveLabs/injective-ts | `@injectivelabs/sdk-ts` |
| Trader Joe | https://docs.traderjoexyz.com/ | github.com/traderjoe-xyz/joe-sdks | `@traderjoe-xyz/sdk` |
| Pangolin | github.com/thanhnguyennguyen/pangolin-sdk | (no official org) | `pangolin-sdk` |
