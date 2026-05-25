# Solana SDKs for DEX Trade Execution — Comprehensive Research

**Research Date:** May 17, 2026  
**Purpose:** Evaluate SDKs and libraries for programmable trade execution on Solana DEXs, scoped to a DeFi trading dashboard.  
**Scope:** Trade execution primitives only (swaps, limit orders, AMM interactions) — not RPC-only data retrieval or token metadata lookup.

**Solana Network Context**
- **Block time:** ~400ms (500ms target, often 400–500ms in practice)
- **Finality:** ~12 seconds (13–14 slots for confirmed finality)
- **TPS capacity:** 65k theoretical, ~3–5k sustained mainnet
- **Transaction size limit:** 1,232 bytes (MTU — constrains complex multi-hop swap instructions)
- **CU limit per transaction:** 1.4M compute units (as of recent policy)

---

## 1. @solana/web3.js — Official Solana JavaScript SDK

### Overview
The foundational JavaScript/TypeScript SDK for interacting with Solana nodes. It provides the RPC client, keypair management, transaction construction/signing, and program interaction primitives that all other SDKs build on top of.

### Key Details
| Field | Value |
|-------|-------|
| **Current Version** | 1.98.4 |
| **Language** | TypeScript |
| **License** | MIT |
| **Package Registry** | npm (`@solana/web3.js`) |
| **Versions Published** | 1,967 (extremely active release cadence) |
| **Installed Size** | 11.2 MB (unpacked) |
| **Dependencies** | 15 |
| **Repo** | https://github.com/solana-foundation/solana-web3.js |
| **Docs** | https://solana.com/docs/developers/guides/javascript |
| **API Reference** | https://solana-labs.github.io/solana-web3.js/ |

### GitHub Maturity (as of May 17, 2026)
| Metric | Value |
|--------|-------|
| ⭐ Stars | 2,722 |
| 🔀 Forks | 1,057 |
| ⚠️ Open Issues | 18 |
| 🟢 Last Push | May 8, 2026 |
| 📅 Created | Aug 22, 2018 |
| 👀 Watchers | N/A (org repo) |

### Supported Chains / Markets
- **Solana Mainnet** (`https://api.mainnet-beta.solana.com`)
- **Solana Devnet** (`https://api.devnet.solana.com`)
- **Solana Testnet** (`https://api.testnet.solana.com`)
- **Custom RPC** endpoints (any Solana-compatible node)

**Note:** This is the chain-level SDK, not a DEX-specific library. It enables interaction with any Solana program, including DEX programs (Raydium, Orca, OpenBook, Jupiter), but doesn't provide DEX-specific abstractions like swap routing or AMM math.

### Auth Flow
- **Keypair (Ed25519):** Native `Keypair.generate()` / `Keypair.fromSecretKey()` for programmatic signers
- **Phantom / Wallet Adapter:** Via `@solana/wallet-adapter-*` packages for browser-based signing
- **Multisig:** Via `@solana/spl-memo` and multi-signature transaction construction
- **Message signing:** `Connection.signTransaction()`, `Transaction.sign()`, `VersionedTransaction` support
- **Ledger/Hardware:** Via wallet-adapter-ledger

### Order Types Supported (via web3.js directly)
web3.js itself does not implement order types — it provides the transaction primitives to:
- Submit raw **instructions** to any on-chain program
- Construct **VersionedTransactions** with Address Lookup Tables (ALTs) for larger instruction sets
- Supports any order type that the target program accepts, passed as raw instruction data

For DEX order types, web3.js is the transport layer; the DEX SDKs (Jupiter, Raydium, Orca) define the order semantics.

### Latency Characteristics
- **RPC call latency:** 50–200ms to Solana RPC nodes (varies by region and node quality)
- **Transaction submission:** Near-instant HTTP POST to RPC
- **Block confirmation:** ~400ms first-confirmation, ~12s for full finality
- **No built-in retry logic:** The SDK provides raw transaction submission; callers must implement their own retry/confirmation polling with strategies like `Connection.confirmTransaction()`
- **Prioritization fees:** Supported via `ComputeBudgetProgram` instructions (added to transaction to improve landing probability during congestion)

### Mainnet vs Devnet/Testnet Support
- **Full parity** across all three clusters — same API, different endpoint
- Devnet/Testnet use identical code paths and abstractions
- Devnet has faucet for SOL airdrop; testnet has its own faucet
- **Caution:** Devnet/Testnet may have different program versions deployed by DEXes

### Documentation Quality
- **Quality:** Excellent — maintained by the Solana Foundation with comprehensive docs
- **Guides:** Step-by-step tutorials for transfers, airdrop, account creation, program interaction
- **API Reference:** Auto-generated JSDoc, thorough parameter documentation
- **Examples:** Extensive code samples in official docs
- **TypeScript-first:** Full type definitions for all methods and accounts

### SDK Maturity Assessment
**★★★★★ Production-ready, foundational.** This is the bedrock library. Extremely mature (2018 origin), massive community, excellent npm/npm adoption. It is used as a peer dependency by virtually every other Solana JS SDK. The 1.x release line is stable but undergoing active evolution. The newer `@solana/kit` (v2 API) is the next-generation modular SDK but 1.98.4 remains the production standard.

---

## 2. solana-py — Unofficial Python SDK for Solana

### Overview
A community-maintained Python client for Solana RPC and transaction handling. Provides Python developers access to Solana without needing to bridge through JavaScript. The most widely-used Python library for Solana.

### Key Details
| Field | Value |
|-------|-------|
| **Current Version** | 0.37.x (PyPI) |
| **Language** | Python |
| **License** | Apache 2.0 |
| **Package Registry** | PyPI (`solana`) |
| **Repo** | https://github.com/michaelhly/solana-py |
| **Docs** | https://michaelhly.github.io/solana-py/ |
| **PyPI page** | https://pypi.org/project/solana/ |

### GitHub Maturity (as of May 17, 2026)
| Metric | Value |
|--------|-------|
| ⭐ Stars | 1,429 |
| 🔀 Forks | 340 |
| ⚠️ Open Issues | 52 |
| 🟢 Last Push | May 14, 2026 |
| 📅 Created | Aug 20, 2020 |
| 👀 Subscribers | 14 |

### Supported Chains / Markets
- **Solana Mainnet**
- **Solana Devnet**
- **Solana Testnet**
- **Custom RPC** via `Cluster` enum or custom endpoint string

Like web3.js, this is a chain-level SDK — not DEX-specific. It provides the transport layer for interacting with any Solana program from Python.

### Auth Flow
- **Keypair (Ed25519):** `Keypair()` class, supports loading from raw bytes, JSON keypair files (Solana CLI format), and seed phrases via `from_mnemonic()`
- **Transaction signing:** `Transaction.sign(keypair)` and `Transaction.sign_partial()`
- **Message signing:** Low-level message construction with signing
- **No wallet adapter:** Python SDK has no equivalent to Phantom wallet adapter — it's designed for backend/service-based signing with loaded keypairs

### Order Types Supported (via solana-py directly)
Same as web3.js — solana-py provides transaction/instruction primitives, not DEX order semantics. For DEX trades from Python:
- Construct instructions manually using known program IDs and instruction format
- Use **Pyserum** (unofficial) for OpenBook/Serum DEX interactions
- Use **anchorpy** (separate package) for Anchor program IDL-based interactions

### Latency Characteristics
- **RPC call latency:** Same network constraints as web3.js (50–200ms to RPC nodes)
- **Serialization overhead:** Python may have slightly higher serialization overhead vs native JS for large instruction payloads, but negligible for typical swap transactions
- **No async-first guarantee:** The SDK supports async via `asyncio` but some methods are sync — important for high-frequency trading loops
- **No built-in retry:** Callers implement their own confirmation polling
- **Prioritization fees:** Supported via the same `ComputeBudgetProgram` approach

### Mainnet vs Devnet/Testnet Support
- **Full parity** across all clusters
- `cluster_api_url()` helper supports all standard environments

### Documentation Quality
- **Quality:** Moderate — decent auto-generated API docs via Sphinx
- **Guides:** Limited tutorial content compared to web3.js; community-created examples fill gaps
- **API Reference:** Function-level documentation present but less comprehensive than web3.js
- **Python type hints:** Full type annotations for IDE support
- **Community:** Smaller ecosystem; fewer StackOverflow answers and blog posts

### SDK Maturity Assessment
**★★★★☆ Well-established but community-maintained.** 1,429 stars and 5+ years of development indicate a stable, tested library. The 52 open issues suggest active maintenance but some backlog. It is the de facto Python SDK for Solana but lacks the institutional backing of web3.js. For a Python-based trading dashboard, this is the primary choice. Consider **anchorpy** as a companion for Anchor-based DEX programs.

**Important Note for Python users:** You will likely need multiple packages:
- `solana` (core SDK) — chain-level operations
- `anchorpy` — Anchor program IDL interactions (many DEXs use Anchor)
- `solders` — Rust-backed Solana primitives (fast serialization, used by newer SDKs)
- `pyserum` — for OpenBook/Serum limit order interactions (if needed)

---

## 3. Jupiter SDK (@jup-ag/api) — DEX Aggregator

### Overview
Jupiter is the dominant DEX aggregator on Solana, routing swaps across 20+ DEXs (Raydium, Orca, Meteora, Phoenix, OpenBook, Marinade, etc.) to find the best execution price. The SDK provides TypeScript types and client code for the Jupiter Quote and Swap APIs.

### Key Details
| Field | Value |
|-------|-------|
| **Current Version** | 6.0.48 (`@jup-ag/api`) |
| **SDK (core)** | 4.0.0-beta.21 (`@jup-ag/core` — experimental) |
| **Language** | TypeScript |
| **License** | MIT |
| **Package Registry** | npm (`@jup-ag/api`) |
| **Versions Published** | 65 |
| **Installed Size** | 246 KB (lightweight — mostly types) |
| **Dependencies** | 0 (it's a types wrapper around REST API) |
| **Repo** | https://github.com/jup-ag/jupiter-quote-api-node |
| **API Docs** | https://station.jup.ag/docs/apis/swap-api |
| **Quote API** | https://quote-api.jup.ag/v6/quote |
| **Swap API** | https://quote-api.jup.ag/v6/swap |

### GitHub Maturity (as of May 17, 2026)
| Metric | Value |
|--------|-------|
| ⭐ Stars | 243 |
| 🔀 Forks | 85 |
| ⚠️ Open Issues | 35 |
| 🟢 Last Push | Apr 2, 2026 |
| 📅 Created | Feb 8, 2022 |

### Supported Chains / Markets
- **Solana Mainnet only** for production trading
- **Limited devnet support** — the API primarily serves mainnet; devnet tokens may not have routing data
- **Aggregated DEXs (20+):** Raydium (all pools), Orca Whirlpools, Meteora DLMM, Phoenix, OpenBook, Marinade, Drift, FluxBeam, Lifinity, Aldrin, Crema, Oasis, Sanctum, and more
- **Token pairs:** Any spl-token pair with liquidity across the aggregated DEXs

### Auth Flow
- **No SDK-level auth:** The Quote API is public (no auth required for price quotes)
- **Swap API requires a signed transaction:**
  1. Call `/quote` endpoint for best route (no auth)
  2. Call `/swap` endpoint with your wallet public key — returns a serialized transaction
  3. Sign the transaction with your keypair (using web3.js or wallet-adapter)
  4. Submit to Solana network (you control submission, not Jupiter)
- **Keypair signing:** Standard Ed25519 via `Keypair.fromSecretKey()`
- **Wallet adapter:** Browser-based signing via Phantom/other wallets supported
- **No API keys required:** The public Jupiter APIs are free to use

### Order Types Supported
- **Market swaps:** Primary order type. Jupiter automatically routes across multiple DEXs and splits orders for optimal price execution
- **Limit orders:** Via Jupiter's separate **Limit Order API** (`https://limit-order.jup.ag/`) — creates OpenBook/Phoenix limit orders under the hood
- **DCA orders:** Dollar-cost-averaging via Jupiter's DCA program
- **Advanced features:** Price impact protection, slippage tolerance, fee tokens

### Latency Characteristics
- **API call latency:** 100–300ms for quote computation (Jupiter computes routes server-side)
- **Swap transaction retrieval:** 200–500ms for the API to assemble a swap transaction (includes on-chain account lookups)
- **Total round-trip (quote → swap tx → sign → submit):** 500ms–2s depending on network
- **Not suitable for HFT:** Jupiter is an API-based aggregator with server-side routing; it's optimized for execution quality, not raw speed
- **Prioritization fees:** Jupiter includes compute budget instructions in swap transactions
- **Rate limits:** Public API has rate limits; high-frequency traders may need a commercial arrangement or self-hosted routing

### Mainnet vs Devnet/Testnet Support
- **Mainnet-only focus.** Quote and Swap APIs are mainnet-focused
- **Devnet:** Limited devnet support — most token pairs won't have routing data on devnet
- **Testnet:** Not supported
- **For testing:** Use Jupiter's documented devnet examples with known devnet token pairs

### Documentation Quality
- **Quality:** Good — Jupiter Station documentation is well-organized
- **Guides:** Step-by-step integration tutorials, Postman collections for API testing
- **API Reference:** Swagger/OpenAPI-spec for Quote API (the @jup-ag/api package is auto-generated from this spec)
- **Examples:** TypeScript examples in repo; community has many integration tutorials
- **Limitations:** Some advanced features (DCA, limit orders) have less documented SDK integration

### SDK Maturity Assessment
**★★★★☆ Production-ready for swaps, beta for advanced features.** Jupiter is the dominant DEX aggregator on Solana handling billions in volume. The `@jup-ag/api` package (v6) is stable and actively used. The `@jup-ag/core` (v4 beta) was an earlier attempt at a more complete SDK but has been superseded by the API-driven approach. For a trading dashboard, Jupiter is the go-to for multi-DEX swaps. The 243 GitHub stars are lower than chain-level SDKs because it's an API wrapper, not the main Jupiter codebase.

**Architecture note:** `@jup-ag/api` is essentially a generated TypeScript client around REST APIs. All routing computation happens on Jupiter servers. This means you are dependent on Jupiter's infrastructure availability and rate limits. For a production dashboard with high trade frequency, consider:
1. Adding local caching for quote data
2. Implementing retry logic for API failures
3. Having a fallback direct-DEX execution path (e.g., Raydium SDK) if Jupiter is unreachable

---

## 4. Raydium SDK (V1 and V2)

### Overview
Raydium is one of the largest Solana DEXs, offering both automated market maker (AMM) pools and concentrated liquidity (CLMM) pools. The SDK provides direct interaction with Raydium on-chain programs for swaps, liquidity provision, and order management.

### Key Details

#### Raydium SDK V1
| Field | Value |
|-------|-------|
| **Package** | `@raydium-io/raydium-sdk` |
| **Version** | 1.3.1-beta.58 |
| **License** | GPL-3.0 |
| **Installed Size** | 1.7 MB |

#### Raydium SDK V2
| Field | Value |
|-------|-------|
| **Package** | `@raydium-io/raydium-sdk-v2` |
| **Version** | 0.2.45-alpha |
| **License** | GPL-3.0 |
| **Installed Size** | 90.9 MB (very large — includes static data) |
| **Versions** | 239 published |

#### GitHub Maturity (as of May 17, 2026)
| Metric | V1 (raydium-sdk-v1) | V2 (raydium-sdk-V2) |
|--------|------|------|
| ⭐ Stars | 409 | 346 |
| 🔀 Forks | 152 | 203 |
| ⚠️ Open Issues | 64 | 1 |
| 🟢 Last Push | Jul 12, 2024 | May 15, 2026 |
| 📅 Created | Nov 9, 2021 | Nov 21, 2022 |
| Language | TypeScript | TypeScript |

### Supported Chains / Markets
- **Solana Mainnet only** — SDK interacts with deployed Raydium programs
- **Pool types:**
  - **AMM v4** (legacy AMM pools — V1 focus)
  - **CLMM** (Concentrated Liquidity Market Maker — V2 focus)
  - **OpenBook market integration** — Raydium pools use OpenBook order books for price discovery
  - **CPMM** (Constant Product Market Maker)
- **Token pairs:** All spl-token pairs with deployed Raydium pools

### Auth Flow
- **Keypair signing:** Standard Ed25519 via `@solana/web3.js` `Keypair`
- **Connection:** `Connection` object from web3.js (required peer dependency)
- **Token accounts:** SDK handles associated token account (ATA) lookups and creation
- **No API keys needed:** Direct on-chain program interaction
- **Wallet adapter:** Works with any web3.js-compatible wallet

### Order Types Supported
- **Market swaps:** Direct AMM swaps against Raydium pools (both v4 AMM and CLMM)
- **Limit orders:** Via Raydium's **OpenBook integration** — Raydium uses OpenBook (formerly Serum) as its order book. The SDK can create limit order instructions on OpenBook markets
- **Liquidity provision:** Add/remove liquidity for AMM v4, CLMM, and CPMM pools
- **Route swaps:** Multi-hop swaps across Raydium pools (V2 has improved routing)

### Latency Characteristics
- **Direct on-chain interaction:** No intermediary API — all pool data and swap instructions are constructed from on-chain account data
- **Account data fetching:** Must fetch pool state accounts before swap construction (~100-300ms per RPC batch)
- **Local computation:** Swap amount calculations happen client-side (AMM math is deterministic)
- **Faster than Jupiter for single-DEX trades:** No server-side routing overhead
- **Slower than Jupiter for multi-DEX price discovery:** You must manually compare prices across DEXs
- **Prioritization fees:** Caller must add compute budget instructions manually
- **V2 improvement:** V2 SDK has better caching and bulk account fetching for reduced latency

### Mainnet vs Devnet/Testnet Support
- **Mainnet-focused** — SDK is designed for mainnet program IDs
- **Devnet:** Limited support — would require deploying Raydium programs on devnet and adjusting program IDs
- **Program IDs are hardcoded** in the SDK for mainnet; devnet usage requires overrides

### Documentation Quality
- **Quality:** Moderate — functional but not comprehensive
- **Guides:** SDK documentation covers basic swap and liquidity operations
- **Examples:** `@raydium-io/raydium-sdk-V2-demo` repo (264 stars) provides working examples
- **API Reference:** Source code serves as primary reference — JSDoc coverage is incomplete
- **Limitations:** Some advanced features (CLMM range orders, complex routing) are poorly documented
- **Language:** Primarily Chinese community + English; some docs may require translation

### SDK Maturity Assessment
**★★★☆☆ Production for swaps, evolving for advanced features.** V1 (409 stars) has 64 open issues and hasn't been pushed to since July 2024 — it's effectively deprecated. V2 (346 stars, last push May 15 2026) is the actively maintained version with only 1 open issue but is still in alpha (0.2.45-alpha). The GPL-3.0 license is notable for commercial dashboards — ensure compliance.

**V1 vs V2:**
- V1: Covers AMM v4 pools, stable but no longer maintained
- V2: Covers CLMM + CPMM + improved AMM, actively developed, still alpha
- **Recommendation:** Use V2 for new development; fall back to V1 if you need features not yet ported

**License caution:** GPL-3.0 means if you distribute your dashboard software, you must also release it under GPL. For a closed-source private dashboard, usage is permitted but consult legal guidance.

---

## 5. Orca SDK (@orca-so/whirlpools-sdk)

### Overview
Orca is a leading Solana DEX specializing in concentrated liquidity pools via its "Whirlpools" architecture. The SDK provides TypeScript tooling for interacting with Orca's Whirlpool program, including swaps, liquidity management, and position tracking.

### Key Details
| Field | Value |
|-------|-------|
| **Package** | `@orca-so/whirlpools-sdk` |
| **Version** | 0.20.0 |
| **License** | Custom (see `LICENSE` in repo — typically BSD-style) |
| **Installed Size** | 1.3 MB (lean) |
| **Dependencies** | 3 (`@orca-so/common-sdk`, `decimal.js`, `tiny-invariant`) |
| **Repo** | https://github.com/orca-so/whirlpools |
| **Homepage** | https://orca.so |
| **Docs** | https://orca-so.gitbook.io/orca-developer-ecosystem/ |

### GitHub Maturity (as of May 17, 2026)
| Metric | Value |
|--------|-------|
| ⭐ Stars | 529 |
| 🔀 Forks | 327 |
| ⚠️ Open Issues | 60 |
| 🟢 Last Push | May 16, 2026 |
| 📅 Created | Apr 22, 2022 |
| Language | TypeScript |

### Supported Chains / Markets
- **Solana Mainnet only**
- **Whirlpools program:** Orca's concentrated liquidity AMM (similar to Uniswap v3)
- **Token pairs:** All spl-token pairs with Whirlpools pools
- **Tick spacing:** Configurable tick spacings (1, 2, 4, 8, 16, 64, 128, 256) for different volatility profiles
- **Fee tiers:** Multiple fee tiers per pool (0.01% to ~1%)

### Auth Flow
- **Keypair signing:** Standard via web3.js `Keypair`
- **Whirlpool Context:** SDK uses `WhirlpoolContext` which wraps the web3.js `Connection` and `wallet` provider
  ```typescript
  const ctx = WhirlpoolContext.from(connection, wallet, programId);
  ```
- **Wallet provider:** Supports any web3.js-compatible wallet (Phantom, Solflare, etc.)
- **No API keys:** Direct on-chain interaction
- **Prioritization fees:** Supported via context configuration

### Order Types Supported
- **Market swaps:** Primary order type — swap against any Whirlpool at current market price
- **Quote computation:** SDK provides on-chain quote calculations (exact-in, exact-out)
- **Liquidity provision:** Open/close liquidity positions with specific price ranges (concentrated liquidity)
- **No native limit orders:** Orca Whirlpools is an AMM, not an order book. Limit order functionality is not part of the core SDK
  - For limit orders on Orca, you would need to use **Orca's Whirlpool program** in combination with a limit order abstraction (community-built or custom)
  - Orca has experimented with limit order features via their UI but these are not fully exposed in the SDK

### Latency Characteristics
- **Direct on-chain:** All pool data fetched from on-chain accounts via RPC
- **Quote calculation:** Client-side computation using pool state — very fast once account data is fetched
- **Account fetching:** Single pool requires fetching whirlpool account + tick array accounts; multi-hop may require multiple batches (~100-400ms)
- **Efficient SDK design:** Only 3 dependencies means minimal overhead
- **Concentrated liquidity complexity:** CLMM math is more computationally intensive than simple AMM, but still runs in milliseconds client-side
- **Prioritization fees:** Must be added by the caller

### Mainnet vs Devnet/Testnet Support
- **Mainnet-focused** — SDK targets Whirlpools program on mainnet
- **Devnet:** Orca has a devnet deployment; program ID must be overridden in context
- **Testnet:** Not officially supported
- **Context override:** WhirlpoolContext accepts custom program ID, enabling devnet testing

### Documentation Quality
- **Quality:** Good — Orca Developer docs are well-structured
- **GitBook docs:** Comprehensive documentation site with guides, API reference, and architecture overview
- **Tutorial repos:** `orca-so/whirlpools-sdk-tutorial-kit` provides hands-on examples
- **TypeScript-first:** Full type definitions, IDE-friendly
- **Community:** Active Discord and Telegram for developer support
- **Gaps:** Advanced CLMM concepts (tick math, fee growth, position management) require understanding of Uniswap v3-like architecture

### SDK Maturity Assessment
**★★★★☆ Production-ready for Whirlpools operations.** 529 stars, active development (last push May 16, 2026), and 327 forks indicate strong community interest and production usage. The SDK is mature and well-designed but focused exclusively on Orca's Whirlpools — it does not support other DEXs. For a trading dashboard, Orca's SDK is essential if you want to trade against Orca pools (which have significant liquidity on Solana).

---

## Comparative Summary

### Quick Comparison Matrix

| Feature | web3.js | solana-py | Jupiter SDK | Raydium SDK | Orca SDK |
|---------|---------|-----------|-------------|-------------|----------|
| **Primary Role** | Chain-level SDK | Chain-level SDK | DEX Aggregator | Single DEX (Raydium) | Single DEX (Orca) |
| **Language** | TypeScript | Python | TypeScript | TypeScript | TypeScript |
| **Version** | 1.98.4 | 0.37.x | 6.0.48 | V2: 0.2.45-alpha | 0.20.0 |
| **Stars** | 2,722 | 1,429 | 243 | V2: 346 | 529 |
| **Last Active** | May 8, 2026 | May 14, 2026 | Apr 2, 2026 | May 15, 2026 | May 16, 2026 |
| **License** | MIT | Apache 2.0 | MIT | GPL-3.0 | Custom |
| **Swaps** | ✅ (via programs) | ✅ (via programs) | ✅ (multi-DEX) | ✅ (Raydium pools) | ✅ (Orca pools) |
| **Limit Orders** | ✅ (via OpenBook) | ✅ (via pyserum) | ✅ (via API) | ✅ (via OpenBook) | ❌ (AMM only) |
| **Multi-DEX Routing** | ❌ | ❌ | ✅ | ❌ | ❌ |
| **API Dependency** | None (RPC only) | None (RPC only) | ✅ (Jupiter API) | None (on-chain) | None (on-chain) |
| **Mainnet** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Devnet** | ✅ | ✅ | ⚠️ Limited | ⚠️ Manual | ⚠️ Manual |
| **Prioritization Fees** | ✅ | ✅ | ✅ | Manual | Manual |

### Latency Comparison (Estimated Trade Round-Trip)

For a typical token swap trade (quote → construction → signing → submission):

| Path | Estimated Latency | Notes |
|------|-------------------|-------|
| **Jupiter (API)** | 500ms – 2s | Server-side routing adds latency but optimizes price |
| **Raydium V2 (direct)** | 150ms – 800ms | Depends on pool state fetch time |
| **Orca (direct)** | 150ms – 800ms | Similar to Raydium; CLMM math adds minimal compute |
| **Custom multi-DEX** | 200ms – 1.5s | Query multiple SDKs, compare prices, execute best |

All paths share Solana's ~400ms block time for transaction confirmation.

### Recommended Architecture for Trading Dashboard

For a private DeFi trading dashboard needing execution across Solana DEXs:

1. **Core transport:** `@solana/web3.js` (v1.98.4) — required for all JS-based operations
2. **Price discovery & execution:** `@jup-ag/api` (v6) — primary route for multi-DEX swaps
3. **Raydium access:** `@raydium-io/raydium-sdk-v2` (alpha) — for direct Raydium pool access, fallback routing
4. **Orca access:** `@orca-so/whirlpools-sdk` (v0.20.0) — for direct Orca Whirlpool access
5. **Python backend (if applicable):** `solana-py` + `anchorpy` — for any Python-based services
6. **OpenBook for limit orders:** Use `openbook-twap` program or raw OpenBook instructions via web3.js — no dedicated SDK exists in the same form

### Key Risks & Considerations

1. **Jupiter dependency:** Using Jupiter means trusting their routing API availability and rate limits. Implement fallbacks.
2. **GPL-3.0 license (Raydium):** Review compliance requirements for your dashboard.
3. **Raydium V2 is alpha:** Breaking changes possible; pin versions.
4. **No Python DEX SDKs:** solana-py is chain-level only; DEX interactions from Python require manual instruction construction or wrapping JS SDKs.
5. **Prioritization fees:** Essential for reliable trade execution during network congestion; manually add compute budget instructions.
6. **Solana congestion:** During high demand, confirmations can take 30+ seconds regardless of SDK choice.
7. **Slippage protection:** Always implement slippage tolerance; all SDKs support it but you must configure it.

### Useful Links

| Resource | URL |
|----------|-----|
| Solana Docs | https://solana.com/docs |
| Solana Explorer | https://explorer.solana.com |
| Jupiter Station Docs | https://station.jup.ag/docs |
| Jupiter Quote API | https://station.jup.ag/docs/apis/swap-api |
| Raydium Docs | https://docs.raydium.io/ |
| Orca Dev Docs | https://orca-so.gitbook.io/orca-developer-ecosystem/ |
| Solana Cookbook | https://solanacookbook.com/ |
| Anchor Framework | https://www.anchor-lang.com/ |

---

*Research compiled May 17, 2026. Package versions and GitHub stats are current as of this date.*
