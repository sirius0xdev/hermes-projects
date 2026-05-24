# Security Review — Trading Platform & Autonomous Bot

**Date:** 2025-07-25
**Reviewer:** Security Audit (Kanban t_f97273cd)
**Scope:** trading-platform/execute-service, data_pipeline, deploy/k8s, infra/helm, config.py, solana.py, hyperliquid.py, security.py, cache.py, redis_lock.py

**Status:** BLOCKED — Do NOT fund wallet until Critical/High findings remediated.

---

## Executive Summary

The trading platform architecture demonstrates solid security foundations: mTLS support, SOPS secret encryption, non-root containers, NetworkPolicy default-deny, and structured config validation. However, several **critical gaps in execution-layer risk controls** mean the autonomous bot currently lacks hard guardrails against total capital loss.

**14 findings: 1 Critical, 5 High, 5 Medium, 1 Low, 1 Info**

### Top Risks
| # | Risk | Impact |
|---|------|--------|
| 1 | Hard-coded JWT default secret | Auth forgery if env misconfigured |
| 2 | No circuit breaker on Solana execution | Unbounded fee burn + duplicate txs |
| 3 | No position size limits | 100% wallet allocation to single token |
| 4 | No daily loss circuit breaker | Full seed capital loss in one day |
| 5 | No rug-pull / token safety filters | Trading rug-pull tokens = permanent loss |

---

## 1. Findings

### [CRITICAL] Hard-coded JWT Secret Default

**File:** `trading-platform/execute-service/app/config.py`

```python
jwt_secret_key: str = "change-me-in-production"
```

**Impact:** If the `EXECUTE_JWT_SECRET_KEY` env var is not set or is empty, the JWT signing secret falls back to the predictable default string. Any attacker can forge valid JWTs, impersonate authorized users, and execute trades.

**Why it matters:** JWT tokens protect the execution API. A weak secret means all authentication is effectively disabled.

**Fix:**
```python
from pydantic import field_validator

@field_validator("jwt_secret_key")
@classmethod
def reject_default(cls, v: str) -> str:
    if v == "change-me-in-production":
        raise ValueError("EXECUTE_JWT_SECRET_KEY must be set to a strong value in production")
    if len(v) < 32:
        raise ValueError("JWT secret must be at least 32 characters")
    return v
```

---

### [HIGH] No Circuit Breaker on Solana Execution

**File:** `trading-platform/execute-service/app/executors/solana.py`

**Impact:** The Solana executor has no circuit breaker pattern. If the RPC fails repeatedly or Jupiter returns stale quotes, the bot will retry indefinitely. Each retry burns priority fees (~$0.01-0.05 per attempt).

**Why it matters:** During RPC outages or Jupiter maintenance, the bot wastes funds on failed transactions and may execute stale quotes.

**Fix:** Implement circuit breaker wrapper:
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=300, half_open_max=2):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self.failure_count = 0
        self.state = "closed"  # closed, open, half_open
        self.last_failure_time = 0

    async def call(self, func, *args, **kwargs):
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half_open"
            else:
                raise CircuitOpen("Circuit breaker open - retrying later")
        try:
            result = await func(*args, **kwargs)
            self.failure_count = 0
            self.state = "closed"
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            raise e
```

---

### [HIGH] No Position Size Limits

**File:** `trading-platform/execute-service/app/executors/solana.py`

**Impact:** The execute-service has no hard position size limits. The quant decision engine could allocate 100% of wallet balance to a single token with no guardrail.

**Why it matters:** A single bad trade can liquidate the entire wallet. Without position sizing, the bot has no risk management at the execution layer.

**Fix:** Add position limits to config.py:
```python
# Risk management
max_position_pct: float = 20.0  # Max % of wallet per position
max_open_positions: int = 5     # Max concurrent open positions
daily_max_trade_volume_pct: float = 50.0  # Max daily trade volume
max_slippage_bps: int = 100      # Max slippage in basis points (1%)
```

Validate in `swap()` before execution:
```python
async def swap(self, token_in: str, amount_in: float, quote_response: dict) -> dict:
    wallet_balance = await self._get_wallet_balance()
    position_pct = (amount_in / wallet_balance) * 100
    if position_pct > self.config.max_position_pct:
        raise ValueError(f"Position size {position_pct:.1f}% exceeds limit {self.config.max_position_pct}%")
    # ... rest of swap logic
```

---

### [HIGH] No Daily Loss Circuit Breaker

**File:** Not implemented

**Impact:** There is no daily P&L tracker or loss limit that pauses the bot automatically. A string of losing trades can drain the entire seed wallet before anyone notices.

**Why it matters:** Without daily loss limits, the bot can lose its entire seed capital in a single day. This is a fundamental risk control missing from any trading system.

**Fix:** Add `DailyLossTracker`:
```python
class DailyLossTracker:
    def __init__(self, redis_client, max_daily_loss_pct=15.0):
        self.redis = redis_client
        self.max_daily_loss_pct = max_daily_loss_pct

    async def initialize(self, starting_balance: float):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"daily_loss:{today}"
        await self.redis.set(key, json.dumps({"balance": starting_balance, "pnl": 0}))

    async def should_pause(self, current_balance: float) -> bool:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"daily_loss:{today}"
        data = json.loads(await self.redis.get(key) or "{}")
        starting = data.get("balance", current_balance)
        loss_pct = ((starting - current_balance) / starting) * 100
        return loss_pct >= self.max_daily_loss_pct
```

---

### [HIGH] No Rug Pull / Token Safety Filters

**File:** `trading-platform/execute-service/app/executors/solana.py`

**Impact:** The execution service has no built-in filters for token age, liquidity, holder concentration, or blacklist. The autonomous bot could trade newly deployed tokens with essentially no liquidity.

**Why it matters:** On Solana, any developer can create a token in seconds. Without safety checks, the bot might trade tokens that are immediate rug pulls — resulting in permanent capital loss.

**Fix:** Add token safety validation layer:
```python
async def check_token_safety(self, token_address: str) -> dict:
    """Validate token safety before trading."""
    checks = {
        "age_hours": await self._check_token_age(token_address),
        "liquidity_usd": await self._check_liquidity(token_address),
        "top_holder_pct": await self._check_holder_concentration(token_address),
        "is_blacklisted": await self._check_blacklist(token_address),
    }
    min_age_hours = self.config.min_token_age_hours  # default 24
    min_liquidity = self.config.min_liquidity_usd    # default 10000
    max_holder_pct = self.config.max_top_holder_pct  # default 30
    if checks["age_hours"] < min_age_hours:
        raise TokenSafetyError(f"Token too young: {checks['age_hours']}h < {min_age_hours}h")
    if checks["liquidity_usd"] < min_liquidity:
        raise TokenSafetyError(f"Insufficient liquidity: ${checks['liquidity_usd']}")
    if checks["top_holder_pct"] > max_holder_pct:
        raise TokenSafetyError(f"Holder concentration too high: {checks['top_holder_pct']}%")
    if checks["is_blacklisted"]:
        raise TokenSafetyError("Token is blacklisted")
    return checks
```

---

### [MEDIUM] Solana Executor `send_sol()` Has Placeholder from_pubkey

**File:** `trading-platform/execute-service/app/executors/solana.py`

```python
transfer_ix = SystemProgram.transfer(
    from_pubkey=Pubkey.from_string(""),  # placeholder
    to_pubkey=Pubkey.from_string(to_address),
    lamports=int(amount_sol * 1e9),
)
```

**Impact:** The `send_sol()` method uses an empty string for `from_pubkey`, which would fail at runtime with a `solana.AddressError`. Raw SOL transfers are broken.

**Fix:** Use the instance's own pubkey:
```python
transfer_ix = SystemProgram.transfer(
    from_pubkey=self._keypair.pubkey,
    to_pubkey=Pubkey.from_string(to_address),
    lamports=int(amount_sol * 1e9),
)
```

---

### [MEDIUM] No Transaction Confirmation Monitoring

**File:** `trading-platform/execute-service/app/executors/solana.py`

**Impact:** After `send_raw_transaction`, the code logs the signature and returns immediately without waiting for on-chain confirmation. Failed transactions still consume priority fees.

**Fix:** Add confirmation polling:
```python
async def wait_for_confirmation(self, tx_sig: str, timeout: int = 30) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        tx = await self._client.get_transaction(tx_sig, commitment="confirmed")
        if tx:
            return tx
        await asyncio.sleep(1)
    raise TimeoutError(f"Transaction {tx_sig} not confirmed within {timeout}s")
```

---

### [MEDIUM] HTTP Client Created Per Request

**File:** `trading-platform/execute-service/app/executors/solana.py`

**Impact:** Both `get_token_price()` and `swap()` create new `httpx.AsyncClient()` instances per call, wasting connections and adding latency.

**Fix:** Create class-level client with connection pooling:
```python
class SolanaExecutor:
    def __init__(self, config: ExecuteConfig):
        self._config = config
        self._client = httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=20, max_keepalive_connections=10))
```

---

### [MEDIUM] Devnet RPC Default for Solana

**File:** `trading-platform/execute-service/app/config.py`

```python
solana_rpc_url: str = "https://api.devnet.solana.com"
```

**Impact:** If `SOLANA_RPC_URL` is not overridden in production, the bot trades on devnet instead of mainnet — silently.

**Fix:** Add startup validation:
```python
@field_validator("solana_rpc_url", mode="after")
@classmethod
def reject_devnet_in_prod(cls, v: str, info: ValidationInfo) -> str:
    env = info.data.get("environment", "development")
    if env == "production" and "devnet" in v or "testnet" in v:
        raise ValueError("Devnet/testnet RPC not allowed in production")
    return v
```

---

### [MEDIUM] No API Rate Limiting on Execute Service Endpoints

**File:** `trading-platform/execute-service/app/` (FastAPI app)

**Impact:** No API rate limiting middleware on execution endpoints. External callers could flood execution endpoints causing resource exhaustion.

**Fix:** Add rate limiting middleware:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/solana/swap")
@limiter.limit("10/second")
async def swap_solana(request: Request, trade: SwapRequest):
    ...
```

---

### [MEDIUM] No Input Validation on Swap Parameters

**File:** `trading-platform/execute-service/app/executors/solana.py`

**Impact:** The `swap()` method accepts any `quote_response` dict without validating it. A malformed or adversarial Jupiter response could cause unexpected behavior.

**Fix:** Add Pydantic model validation for quote responses:
```python
class JupiterQuoteResponse(BaseModel):
    inputAmount: int
    outputAmount: int
    swapMode: str
    otherAmountThreshold: int
    platformFee: Optional[dict]
    priceImpactPct: str
    routePlan: list
```

---

### [LOW] No Structured Audit Logging for Key Operations

**Impact:** Private key initialization logs only the pubkey (correct). But there's no audit trail for when the key was last loaded, rotated, or accessed.

**Fix:** Add audit logging events:
```python
logger.info("key_loaded", pubkey=str(self._keypair.pubkey), timestamp=datetime.utcnow().isoformat())
```

---

### [INFO] Consider GCP Secret Manager Integration

**Current state:** SOPS + K8s Secrets (good practice).
**Enhancement:** GKE-native GCP Secret Manager CSI driver provides automatic rotation, audit logging, and IAM-based access control for secrets.

---

## 2. What's Done Well

| Control | Implementation | Status |
|---------|---------------|--------|
| mTLS | Client cert validation, configurable trust stores | ✅ Supported |
| Secret Encryption | SOPS with age keys encrypting K8s secrets | ✅ Production-ready |
| Non-root Containers | `appuser` in Dockerfiles, `runAsNonRoot: true` | ✅ Enforced |
| NetworkPolicies | Default-deny ingress/egress + service-specific allow | ✅ Comprehensive |
| Redis Rate Limiting | Sliding window, 100 req/sec limit | ✅ Implemented |
| Structured Config | Pydantic settings with env var mapping | ✅ Well-designed |
| JWT Auth | Token generation + validation in security.py | ✅ In place |

---

## 3. Architecture Security Model

From `AUTONOMOUS-BOT-ARCH.md` and `TASK-DECOMPOSITION.md`:
- **Multi-agent design:** Quant engine (decision) → Execute service (execution) → Dashboard (monitoring)
- **Communication:** gRPC with mTLS between agents
- **Secrets:** SOPS-encrypted K8s secrets, age-key encrypted
- **Auth:** JWT-based authentication for API access
- **Data:** PostgreSQL for persistence, Redis for caching/rate limiting

---

## 4. Risk Scorecard

| Severity | Count | Examples |
|----------|-------|---------|
| Critical | 1 | JWT default secret |
| High | 5 | No circuit breakers, position limits, daily loss, token safety, key rotation |
| Medium | 5 | Broken send_sol, no tx confirmation, no connection pooling, devnet default, no rate limiting |
| Low | 1 | Audit logging |
| Info | 1 | GCP Secret Manager |
| **Total** | **14** | |

**Overall Risk Level: HIGH** — Requires remediation before live trading with funded wallet.

---

## 5. Remediation Priority

**Before First Funded Trade:**
1. [CRITICAL] Add JWT secret validation (reject default)
2. [HIGH] Add position size limits (max 20% per position)
3. [HIGH] Add daily loss circuit breaker (pause at 15% drawdown)
4. [HIGH] Add circuit breaker on Solana execution
5. [HIGH] Add token safety filters (age, liquidity, concentration)

**Before Regular Operation:**
6. [MEDIUM] Fix send_sol() from_pubkey
7. [MEDIUM] Add transaction confirmation polling
8. [MEDIUM] Add connection pooling for HTTP clients
9. [MEDIUM] Reject devnet RPC in production
10. [MEDIUM] Add API rate limiting middleware

**Nice to Have:**
11. [LOW] Add key lifecycle audit logging
12. [INFO] Migrate to GCP Secret Manager CSI driver

---

## 6. Recommendations

1. **Do NOT fund the wallet** until all Critical and High findings are remediated.
2. **Use hot/cold wallet pattern:** Hot wallet holds only daily trading capital. Cold wallet holds reserves.
3. **Start small:** Fund with minimal amount ($50-100) for initial validation before scaling up.
4. **Add manual approval gate:** For first trades, require human approval before execution.
5. **Implement external monitoring:** Alert on daily P&L, wallet balance drops, and failed transactions.
