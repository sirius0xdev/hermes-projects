# Execution SDK Comparison — DeFi Trading Dashboard

**Research Date:** May 17, 2026  
**Purpose:** Evaluate SDKs for trade execution on a private DeFi trading dashboard  
**Categories Covered:** Hyperliquid, Solana Ecosystem, EVM DEXs, CEX Aggregation, Perpetuals

---

## Executive Summary

| SDK/Category | Language | Best For | Verdict |
|--------------|----------|----------|---------|
| **Hyperliquid Python SDK** | Python 3.9+ | Hyperliquid perp/spot trading | ⭐⭐⭐⭐⭐ Official, production-ready |
| **Hyperliquid Node.js SDK** | TypeScript | Hyperliquid perp/spot trading | ⭐⭐⭐⭐ Community, well-maintained |
| **Solana web3.js** | TypeScript | Solana chain-level ops | ⭐⭐⭐⭐⭐ Foundational, essential |
| **solana-py** | Python | Solana from Python | ⭐⭐⭐⭐ Community, no DEX abstractions |
| **Jupiter SDK (@jup-ag/api)** | TypeScript | Solana multi-DEX swaps | ⭐⭐⭐⭐ Best aggregator on Solana |
| **Raydium SDK V2** | TypeScript | Raydium pool execution | ⭐⭐⭐ Alpha, GPL-3.0 warning |
| **Orca Whirlpools SDK** | TypeScript | Orca pool execution | ⭐⭐⭐⭐ Production-ready, AMM-only |
| **CCXT** | JS/TS/Py/PHP/Go/C# | 100+ CEX execution | ⭐⭐⭐⭐⭐ Universal, unmatched coverage |
| **Uniswap SDKs (v3/v4)** | TypeScript | EVM DEX swaps | ⭐⭐⭐⭐⭐ Essential for EVM chains |
| **dYdX v4 SDK** | TypeScript | Perpetual futures orderbook | ⭐⭐⭐⭐ Best DeFi perp orderbook, AGPL-3.0 |
| **Injective SDK** | TypeScript | Cross-chain spot+derivs | ⭐⭐⭐⭐ Permissive license (Apache-2.0) |
| **Trader Joe SDK** | TypeScript | Avalanche DEX | ⭐⭐⭐ Niche (Avalanche-specific) |

**Recommended Core Stack:**
1. **CCXT** — CEX execution layer (Binance, Bybit, OKX, Kraken)
2. **Hyperliquid Python SDK** — Hyperliquid perp/spot (own L1, 400ms blocks)
3. **Uniswap SDKs** — EVM chain DEX execution (Arbitrum, Base, Polygon, etc.)
4. **Solana web3.js + Jupiter** — Solana DEX swaps
5. **dYdX v4** — Perpetual futures (if derivatives needed)
6. **Injective** — Cross-chain spot+derivatives alternative to dYdX

---

## 1. Hyperliquid SDK

### 1.1 Hyperliquid Python SDK (Official)

| Field | Value |
|-------|-------|
| **Package** | `hyperliquid-python-sdk` |
| **Version** | 0.23.0 |
| **License** | MIT |
| **Repository** | https://github.com/hyperliquid-dex/hyperliquid-python-sdk |
| **Docs** | https://hyperliquid.gitbook.io/hyperliquid |
| **Python Support** | 3.9–3.13 |
| **GitHub Stars** | ~1,600 |
| **Monthly PyPI Downloads** | ~34,000 |
| **Last Active** | April 2026 (3+ years development) |

**Supported Chains/Markets:**
- **Hyperliquid L1** — Tendermint-based chain, not an L2 (~400ms block time)
- **Perpetual futures** — 50+ pairs (BTC, ETH, SOL, DOGE, AVAX, etc.)
- **Spot trading** — Growing spot market
- **Vaults** — Automated strategies

**Auth Flow:**
- **Private key signing** — Direct Ethereum keypair for signature
- **API wallet/agent keys** — Sub-wallets with isolated permissions
- **No exchange API keys** — All transactions are signed and submitted directly

**Order Types:**
- Market, Limit (GTC/IOC), Trigger/Stop
- Reduce-only orders
- Bulk order submission (up to 20 orders per tx)
- Vault management (deposit/withdraw)

**Latency:**
- Expected round-trip: ~50-150ms
- HTTP REST for trading, WebSocket for market data
- Optimized for programmatic trading

**Mainnet vs Testnet:**
- Full mainnet + testnet support
- Testnet available for development

**Python SDK Maturity:** ⭐⭐⭐⭐⭐ Production-ready, officially maintained

### 1.2 Hyperliquid Node.js SDK (Community)

| Field | Value |
|-------|-------|
| **Package** | `hyperliquid` (npm) |
| **Version** | 1.7.7 |
| **License** | MIT |
| **Repository** | https://github.com/nomeida/hyperliquid-api |
| **GitHub Stars** | 283 |
| **Weekly NPM Downloads** | ~6,300 |
| **Last Active** | March 2026 |

**Key Features:**
- TypeScript-native with full type coverage
- WebSocket streaming for real-time data
- REST API + WebSocket support
- Covers most official SDK features (vault, cancel-schedule may be limited)

**Node.js SDK Maturity:** ⭐⭐⭐⭐ Community-maintained, actively used

### Hyperliquid Architecture Notes
- **Self-hosted L1** with Tendermint consensus (~400ms block time)
- Separate chain, not built on Ethereum/Solana
- Fast finality, low latency
- HTTP REST for trading operations
- WebSocket for order book, trades, user fills

---

## 2. Solana SDKs

### 2.1 @solana/web3.js (Official JS)

| Field | Value |
|-------|-------|
| Version | 1.98.4 |
| Stars | 2,722 |
| Forks | 1,057 |
| License | MIT |
| Last Push | May 8, 2026 |
| Created | Aug 22, 2018 |

**Role:** Chain-level SDK — foundational for all JS-based Solana operations. Enables interaction with any Solana program (DEXs, lending, NFTs). Provides transaction primitives, keypair management, and RPC client.

**Auth:** Keypair (Ed25519), Wallet Adapter (Phantom/Solflare), hardware wallets via ledger adapter.

**Order Types:** None directly — provides instruction submission primitives. DEX SDKs define order semantics.

**Latency:** RPC calls 50-200ms. Transaction confirmation ~400ms (12s for finality). Solana block time: ~400ms.

**Networks:** Mainnet, Devnet, Testnet with full parity.

### 2.2 solana-py (Python)

| Field | Value |
|-------|-------|
| Version | 0.37.x |
| Stars | 1,429 |
| License | Apache 2.0 |
| Last Push | May 14, 2026 |

**Role:** Python client for Solana. Chain-level only, no DEX abstractions. Requires companion packages (anchorpy for Anchor programs, pyserum for OpenBook).

**Python DEX gap:** No dedicated Python DEX SDKs exist — must construct instructions manually or use wrapper libraries.

### 2.3 Jupiter SDK (@jup-ag/api)

| Field | Value |
|-------|-------|
| Version | 6.0.48 |
| Stars | 243 |
| License | MIT |
| Last Push | Apr 2, 2026 |

**Role:** Dominant Solana DEX aggregator. Routes across 20+ DEXs. Primary for multi-DEX swaps.

**Auth:** No API key required for quotes. Swap API returns serialized transaction, sign with keypair.

**Order Types:** Market swaps (primary), Limit orders (separate API), DCA.

**Latency:** 500ms-2s total round-trip (server-side routing). Not HFT-grade but optimal price execution.

### 2.4 Raydium SDK V2

| Field | Value |
|-------|-------|
| Version | 0.2.45-alpha |
| Stars | 346 |
| License | GPL-3.0 ⚠️ |
| Last Push | May 15, 2026 |

**Role:** Direct Raydium AMM interaction (CLMM, CPMM, AMM pools). Still alpha.

**⚠️ License caution:** GPL-3.0 — if distributing dashboard, must release under GPL.

### 2.5 Orca Whirlpools SDK

| Field | Value |
|-------|-------|
| Version | 0.20.0 |
| Stars | 529 |
| License | Custom (BSD-style) |
| Last Push | May 16, 2026 |

**Role:** Direct Orca Whirlpool (CLMM) interaction. Clean design (3 dependencies), well-documented.

**Limitation:** AMM-only, no native limit orders in SDK.

---

## 3. EVM DEX SDKs

### 3.1 Uniswap SDKs

| SDK | Version | Weekly Downloads | License |
|-----|---------|-----------------|---------|
| @uniswap/sdk-core | 7.14.0 | ~500K+ | MIT |
| @uniswap/v3-sdk | 3.30.0 | ~250K+ | MIT |
| @uniswap/v4-sdk | 2.1.0 | ~50K+ | MIT |

**Supported Chains:** Ethereum L1, Arbitrum, Optimism, Polygon, Base, BNB Chain, Celo, Avalanche — anywhere Uniswap is deployed.

**Auth:** Wallet signatures (MetaMask, WalletConnect). No API keys.

**Order Types:** Swaps (primary). Multi-hop routing computed locally. No traditional order types — use UniswapX/CowSwap for limit-order-like functionality.

**Latency:** Quote <10ms (local calculation). Transaction confirmation 2-12s (chain-dependent). L2s much faster (~2s) than Ethereum L1 (~12s).

**Maturity:** ⭐⭐⭐⭐⭐ Essential for any EVM dashboard.

---

## 4. CEX Execution

### 4.1 CCXT (Universal Exchange Library)

| Field | Value |
|-------|-------|
| Version | 4.5.54 |
| Weekly Downloads | ~500K+ (npm), ~2M+ (PyPI) |
| Stars | 100,000+ |
| License | MIT |
| Last Updated | May 15, 2026 |
| Languages | JS/TS, Python, PHP, C#, Go |

**Exchanges:** 100+ CEXs — Binance, Coinbase Pro, OKX, Kraken, Bybit, KuCoin, etc.

**Auth:** API Key + Secret per exchange. Standard HMAC-SHA256 signing.

**Order Types:** Market, Limit, Stop-loss, Stop-limit, Take-profit, Trailing stop, Reduce-only, IOC/FOK/GTC, Post-only. Per-exchange availability varies.

**Latency:** REST 50-500ms. WebSocket 10-50ms (CCXT Pro, commercial license required for production).

**Testnet:** Most exchanges support sandbox mode via `setSandboxMode(true)`.

**Maturity:** ⭐⭐⭐⭐⭐ Unmatched CEX coverage. Not DeFi/Dex — pair with DEX SDKs.

---

## 5. Perpetuals & Derivatives

### 5.1 dYdX v4 SDK

| Field | Value |
|-------|-------|
| Package | `dydx` (npm) |
| Version | 1.0.13 |
| License | AGPL-3.0 ⚠️ |
| Stars | ~500+ (v4-chain), ~200+ (v4-clients) |
| Last Updated | May 2026 |

**Architecture:** Cosmos-based standalone chain (~0.6s blocks). Order book model for perpetuals.

**Markets:** 30+ perpetual pairs (BTC, ETH, SOL, DOGE, etc.). No spot trading.

**Auth:** Dual layer — API keys + ECDSA signatures + Cosmos wallet signing.

**Order Types:** Full suite — Market, Limit, Stop-Market, Stop-Limit, TP-Market, TP-Limit, Trailing Stop, IOC, FOK, GTT, GTB, Post-Only, Reduce-Only.

**Testnet:** Full testnet with faucet support.

**⚠️ License caution:** AGPL-3.0 — copyleft. If distributing, must release source.

### 5.2 Injective SDK

| Field | Value |
|-------|-------|
| Package | @injectivelabs/sdk-ts |
| Version | 1.19.12 |
| License | Apache-2.0 |
| Stars | ~200+ (sdk-ts), ~1K+ (monorepo) |
| Weekly Downloads | ~10K+ |
| Last Updated | May 15, 2026 |

**Architecture:** Cosmos-based L1 optimized for DeFi. Order book model.

**Markets:** 100+ spot + derivatives pairs. Cross-chain via IBC (Ethereum, Solana, BNB assets).

**Auth:** Cosmos wallet, EVM wallet (EIP-712), Ledger. No separate API keys.

**Order Types:** Market, Limit, Stop-Market, Stop-Limit, Take-Profit, Conditional, Reduce-Only.

**Benefits:** Apache-2.0 license (permissive). Lower gas fees. Cross-chain IBC support.

---

## 6. Latency Comparison

| SDK/Method | Quote/Calc | Trade Submit | Finality | Total Round-Trip |
|------------|------------|-------------|----------|-----------------|
| **CCXT (REST)** | N/A | 50-500ms | N/A | 50-500ms |
| **CCXT (WS)** | N/A | 10-50ms | N/A | 10-50ms |
| **Hyperliquid** | N/A | 50-150ms | 400ms (L1) | 50-150ms |
| **dYdX v4 (REST)** | N/A | 30-100ms | 0.6s block | 30-100ms |
| **Injective** | N/A | 50-200ms | 1-2s block | 50-200ms |
| **Uniswap (L2)** | <10ms | 2-3s | 2s block | 2-5s |
| **Uniswap (L1)** | <10ms | 12s | 12s block | 12-15s |
| **Jupiter (Solana)** | 100-300ms | 200-500ms | 400ms block | 500ms-2s |
| **Raydium Direct** | <10ms | 150-300ms | 400ms block | 150-800ms |
| **Orca Direct** | <10ms | 150-300ms | 400ms block | 150-800ms |

---

## 7. Architecture Recommendations

### Tier 1 — Core Execution

| SDK | Use Case | Why |
|-----|----------|-----|
| **CCXT** | All CEX execution | Unified API, 100+ exchanges |
| **Hyperliquid Python SDK** | Hyperliquid perp/spot | Official SDK, own fast L1 |
| **Uniswap SDKs (v3)** | EVM DEX swaps | Multi-chain, free, no KYC |
| **Solana web3.js + Jupiter** | Solana execution | Best price routing, 20+ DEXs |

### Tier 2 — Extended Coverage

| SDK | Use Case | Why |
|-----|----------|-----|
| **dYdX v4** | Perpetual futures | Full orderbook, 30+ pairs |
| **Injective** | Cross-chain spot+derivs | Apache-2.0, 100+ markets |
| **Orca SDK** | Orca pool access | Solana CLMM specialist |

### Tier 3 — Niche/Skip

| SDK | Status | Notes |
|-----|--------|-------|
| **Raydium V2** | Alpha | GPL-3.0 license warning |
| **Trader Joe** | Avalanche-specific | Only if AVAX exposure needed |
| **Pangolin** | Stale (2022) | Skip |

---

## 8. License Summary

| SDK | License | Commercial Use | Distribution Notes |
|-----|---------|---------------|-------------------|
| Hyperliquid | MIT | ✅ | Free, no restrictions |
| CCXT | MIT | ✅ | Free, no restrictions |
| Uniswap | MIT | ✅ | Free, no restrictions |
| web3.js | MIT | ✅ | Free, no restrictions |
| solana-py | Apache 2.0 | ✅ | Free, permissive |
| Jupiter | MIT | ✅ | Free, no restrictions |
| Orca | Custom (BSD-style) | ✅ | Review custom terms |
| Injective | Apache 2.0 | ✅ | Free, permissive |
| Trader Joe | MIT | ✅ | Free, no restrictions |
| **dYdX v4** | **AGPL-3.0** | ⚠️ | Must release source if distributed |
| **Raydium V2** | **GPL-3.0** | ⚠️ | Must release source if distributed |

---

## 9. Implementation Priority Order

1. **CCXT** — Quickest value (unified CEX API, 5-min setup)
2. **Hyperliquid Python SDK** — Official SDK, well-documented, fast execution
3. **Uniswap v3 SDK** — EVM coverage on L2s (Arbitrum/Base), fast transactions
4. **Solana web3.js + Jupiter** — Solana coverage via aggregator
5. **dYdX v4 or Injective** — Perpetuals (pick based on license preference)
6. **Orca SDK** — Solana CLMM specialist (if needed)

---

## 10. Research Sources

| SDK | Primary Source | Secondary |
|-----|---------------|-----------|
| Hyperliquid | https://github.com/hyperliquid-dex/hyperliquid-python-sdk | https://hyperliquid.gitbook.io/hyperliquid |
| Solana web3.js | https://github.com/solana-foundation/solana-web3.js | https://solana.com/docs |
| solana-py | https://github.com/michaelhly/solana-py | https://pypi.org/project/solana |
| Jupiter | https://github.com/jup-ag/jupiter-quote-api-node | https://station.jup.ag/docs |
| Raydium | https://github.com/raydium-io/raydium-sdk-V2 | https://docs.raydium.io |
| Orca | https://github.com/orca-so/whirlpools | https://orca-so.gitbook.io |
| CCXT | https://github.com/ccxt/ccxt | https://docs.ccxt.com |
| Uniswap | https://github.com/Uniswap/sdks | https://docs.uniswap.org |
| dYdX v4 | https://github.com/dydxprotocol/v4-clients | https://docs.dydx.exchange |
| Injective | https://github.com/InjectiveLabs/injective-ts | https://docs.injective.network |
| Trader Joe | https://github.com/traderjoe-xyz/joe-sdks | https://docs.traderjoexyz.com |

---

*Research compiled May 17, 2026. Package versions and GitHub stats are current as of this date.*
*All SDKs have free tier access — no upfront costs.*
