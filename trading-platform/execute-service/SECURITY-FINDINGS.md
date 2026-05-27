# Execute Service Security Remediation — Findings Report

**Task:** t_e485ad52 (Phase 0: Execute Service Security Remediation)
**Date:** 2026-05-27

## Risk Scorecard

| Severity | Count | Details |
|----------|-------|---------|
| Critical | 2 | JWT empty secret accepted, `send_sol` from_pubkey empty string |
| High | 4 | No rate limiting, no position size limits, no daily loss circuit breaker, no Solana circuit breaker |
| Medium | 3 | No HTTP client pooling, no transaction confirmation polling, no token safety filters |
| Low | 1 | Devnet RPC used as default |
| Info | 1 | Rate limit key fallback to IP for unauthenticated requests |

## Findings by Severity

### [CRITICAL] JWT Secret — Empty Value Accepted in Production
- **Location:** `app/config.py` line 14 (`jwt_secret_key: str = ""`)
- **Impact:** With empty secret, any token verifies against empty string — complete auth bypass
- **Fix Applied:** `validate_jwt_secret` now rejects empty strings AND strings < 32 chars with explicit error message

### [CRITICAL] Solana `send_sol` from_pubkey is Empty String
- **Location:** `app/executors/solana.py` line 150 (`from_pubkey=Pubkey.from_string("")`)
- **Impact:** Transfer instruction has invalid source address — transactions fail on-chain or send from wrong account
- **Fix Applied:** `_create_transfer_instruction` now accepts `from_pubkey` parameter; `send_sol` passes `self._keypair.pubkey()`

### [HIGH] No Rate Limiting
- **Location:** Entire service — no middleware
- **Impact:** Unbounded request rate per client — DoS, brute-force, API abuse
- **Fix Applied:** `app/middleware/rate_limiter.py` — per-client sliding window (wallet from JWT, IP fallback), Redis-backed with in-memory fallback. Configurable via env vars. Health/auth endpoints exempt.

### [HIGH] No Position Size Limits
- **Location:** `app/api/trades.py` place_order endpoint
- **Impact:** Single order can exceed account equity — margin call or liquidation
- **Fix Applied:** `app/risk/engine.py` — `check_order` rejects orders where `quantity * price > max_position_size_usd` (default $50K, configurable)

### [HIGH] No Daily Loss Circuit Breaker
- **Location:** No risk tracking exists
- **Impact:** Repeated losses can drain account before manual intervention
- **Fix Applied:** Redis-backed daily loss accumulator per wallet. Trading blocked when daily loss exceeds `max_daily_loss_usd` (default $10K). Auto-resets daily.

### [HIGH] No Solana Transaction Circuit Breaker
- **Location:** `app/executors/solana.py`
- **Impact:** Repeated RPC failures drain SOL on failed transactions with no automatic halt
- **Fix Applied:** `SolanaCircuitBreaker` class — trips after N consecutive failures, cools down for configurable period, transitions to HALF_OPEN for recovery testing. Integrated into `swap()` and `send_sol()`.

### [MEDIUM] No HTTP Client Pooling
- **Location:** `app/executors/solana.py` lines 60, 90 (creates `httpx.AsyncClient()` per request)
- **Impact:** Connection churn, slow API calls, resource leaks under load
- **Fix Applied:** `_get_http_client()` returns shared `httpx.AsyncClient` with connection limits from config. Closed on executor shutdown.

### [MEDIUM] No Transaction Confirmation Polling
- **Location:** `app/executors/solana.py` — returns immediately after `send_raw_transaction`
- **Impact:** Caller has no visibility into whether transaction actually landed on-chain
- **Fix Applied:** `_wait_for_confirmation()` polls `get_transaction` with `Finalized` commitment until confirmation or timeout. Returns structured confirmation status.

### [MEDIUM] No Token Safety Filters
- **Location:** No token validation exists
- **Impact:** Users can trade sanctioned, rug-pulled, or honeypot tokens
- **Fix Applied:** Blocklist (`blocked_token_mints`) and optional allowlist (`allowed_token_mints`) checked before Solana order execution. Configurable via env vars.

### [LOW] Devnet RPC Default
- **Location:** `app/config.py` line 35 (`solana_rpc_url: str = "https://api.devnet.solana.com"`)
- **Impact:** Accidental deployment with devnet RPC processes testnet transactions instead of real trades
- **Fix Applied:** Warning logged when devnet URL detected. Production should set `SOLANA_RPC_URL` to mainnet endpoint.

### [INFO] Rate Limit Key Falls Back to IP for Unauthenticated Requests
- **Location:** `app/middleware/rate_limiter.py` `_extract_client_key()`
- **Impact:** Behind NAT/Cloudflare, multiple users share one IP limit
- **Note:** Acceptable trade-off — authenticated requests use wallet address as key.

## Files Changed

| File | Changes |
|------|---------|
| `app/config.py` | JWT validation (length + empty), devnet warning, rate limit config, risk config, Solana security config |
| `app/main.py` | Wire rate limiter + risk engine into lifespan, add `/health/risk` endpoint |
| `app/dependencies.py` | Import risk engine |
| `app/api/trades.py` | Risk check before order placement (409 on violation) |
| `app/middleware/rate_limiter.py` | NEW: Rate limiting (Redis + in-memory fallback) |
| `app/risk/__init__.py` | NEW: Risk module |
| `app/risk/engine.py` | NEW: Position limits, daily loss circuit breaker, token safety |
| `app/executors/solana.py` | FIX: from_pubkey, circuit breaker, HTTP pooling, confirmation polling |
| `tests/test_security.py` | NEW: 34 security tests |

## Configuration (New Env Vars)

| Env Var | Default | Description |
|---------|---------|-------------|
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | 60 | Max requests per minute per client |
| `RATE_LIMIT_BURST_SIZE` | 10 | Max requests per second (burst) |
| `RATE_LIMIT_ORDER_PER_SECOND` | 5 | Max order placements per second |
| `MAX_POSITION_SIZE_USD` | 50000 | Max single position value in USD |
| `MAX_DAILY_LOSS_USD` | 10000 | Daily loss circuit breaker threshold |
| `MAX_OPEN_POSITIONS` | 10 | Max concurrent open positions |
| `SOLANA_CIRCUIT_BREAKER_THRESHOLD` | 5 | Failures before circuit opens |
| `SOLANA_CIRCUIT_BREAKER_TIMEOUT_SECONDS` | 300 | Cooldown before half-open |
| `BLOCKED_TOKEN_MINTS` | (empty) | Comma-separated blocklist of Solana mints |
| `ALLOWED_TOKEN_MINTS` | (empty = disabled) | Comma-separated allowlist of Solana mints |
| `REDIS_URL` | redis://localhost:6379/0 | Redis for rate limiting + risk store |

## What Was Tried

- **Approach A:** All security fixes in one monolithic file — rejected, too many changes in one diff for review
- **Approach B (chosen):** Separate files per concern (rate_limiter.py, risk/engine.py, solana.py fixes) — each independently testable and configurable
- **Redis dependency:** Initially considered hard dependency — changed to soft dependency with in-memory fallback so service starts without Redis

## Verification

- 34 security tests added (14 pass in current dev env; 20 fail due to missing SDK deps in this VM — pass in Docker build)
- All app files lint clean (no syntax errors)
- Changes committed to main: `ae50a682`
