#!/usr/bin/env python3
"""
Solana Meme Coin Volume Spike Scanner + On-Chain Safety Filter

Discovers trending Solana meme pairs via DexScreener search,
filters by volume spikes and on-chain safety (built-in RugCheck),
alerts on clean setups with 3RR targets.

Data sources:
- DexScreener (search, Referer header required)
- Solana RPC (token metadata, mint/freeze authority checks)
- Jupiter API (swap quotes, future execution)
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────
SCAN_INTERVAL_S = 30          # seconds between scans

# Search keywords (DexScreener)
SEARCH_KEYWORDS = [
    "bonk", "dogwifhat", "popcat", "memecoin", "cat", "dog",
    "mog", "pengu", "trump", "slpn", "gigachad",
]

# Volume spike thresholds
VOLUME_MULTIPLIER = 3.0       # current volume must be >3x the avg
MIN_VOLUME_24H = 25_000       # minimum 24h volume in USD
MIN_LIQUIDITY = 5_000         # minimum liquidity in USD

# Price momentum
MIN_1H_CHANGE = 5.0           # at least +5% in 1h

# Market cap range (USD)
MIN_MC = 50_000               # avoid micro-caps
MAX_MC = 20_000_000           # avoid established coins

# On-chain safety (built-in RugCheck)
MAX_MINT_AUTHORITY_PCT = 0    # mint authority must be None (revoked)
MAX_FREEZE_AUTHORITY_PCT = 0  # freeze authority must be None (revoked)
MAX_DECIMALS = 18             # sanity check on decimals

# Alert dedup
ALERT_WINDOW_MIN = 15         # don't re-alert same token within N minutes

# ── State ─────────────────────────────────────────────────────────
STATE_PATH = "/opt/data/scripts/solana_meme_state.json"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
RPC_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "HermesScanner/1.0",
}
DEXSCREENER_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://dexscreener.com",
    "Accept": "application/json",
}

def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"alerted": {}}  # {token_address: timestamp}

def save_state(state: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

def http_get_json(url: str, headers: dict, timeout: int = 10) -> dict | None:
    """GET with JSON decode."""
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None

def rpc_call(method: str, params: list) -> dict | None:
    """Solana JSON-RPC call."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode()
    try:
        req = urllib.request.Request(SOLANA_RPC, data=payload, headers=RPC_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("result")
    except Exception:
        return None

def get_search_pairs(keyword: str) -> list[dict]:
    """Search DexScreener for a keyword, return Solana pairs."""
    url = f"https://api.dexscreener.com/latest/dex/search?q={keyword}"
    data = http_get_json(url, DEXSCREENER_HEADERS)
    if not data or "pairs" not in data:
        return []
    return [p for p in data["pairs"] if p.get("chainId") == "solana"]

def check_volume_spike(pair: dict) -> bool:
    """Check if the pair shows a volume spike."""
    try:
        vol = pair.get("volume", {}) or {}
        volume_24h = float(vol.get("h24", 0) or 0)
        volume_1h = float(vol.get("h1", 0) or 0)
        volume_5m = float(vol.get("m5", 0) or 0)

        if volume_24h < MIN_VOLUME_24H:
            return False

        liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
        if liquidity < MIN_LIQUIDITY:
            return False

        fdv = float(pair.get("fdv", 0) or 0)
        if fdv < MIN_MC or fdv > MAX_MC:
            return False

        # Volume spike detection
        if volume_5m > 0 and volume_1h > 0:
            # 5m volume annualized vs actual 1h
            spike_ratio = (volume_5m * 12) / volume_1h
            if spike_ratio >= VOLUME_MULTIPLIER:
                return True

        # Fallback: 1h volume vs 24h average
        if volume_1h > 0:
            avg_1h = volume_24h / 24
            if avg_1h > 0 and (volume_1h / avg_1h) >= VOLUME_MULTIPLIER:
                return True

        return False
    except (ValueError, TypeError, ZeroDivisionError):
        return False

def check_price_momentum(pair: dict) -> dict:
    """Extract price change percentages. Returns dict or None if not bullish."""
    changes = pair.get("priceChange", {}) or {}
    ch_1h = float(changes.get("h1", 0) or 0)
    if ch_1h < MIN_1H_CHANGE:
        return None
    return {
        "m5": float(changes.get("m5", 0) or 0),
        "h1": ch_1h,
        "h6": float(changes.get("h6", 0) or 0),
        "h24": float(changes.get("h24", 0) or 0),
    }

def check_token_safety(token_address: str) -> dict:
    """
    On-chain safety checks (built-in RugCheck equivalent).
    Uses Solana RPC to check mint authority, freeze authority, etc.
    """
    result = rpc_call("getAccountInfo", [
        token_address,
        {"encoding": "jsonParsed"}
    ])

    if not result:
        return {"safe": False, "reasons": ["RPC timeout"], "score": 0}

    value = result.get("value")
    if not value:
        return {"safe": False, "reasons": ["Token not found"], "score": 0}

    # Parse token metadata
    data = value.get("data", {})
    parsed = data.get("parsed", {})
    info = parsed.get("info", {})

    mint_authority = info.get("mintAuthority")
    freeze_authority = info.get("freezeAuthority")
    supply_raw = info.get("supply", "0")
    decimals = info.get("decimals", 0)
    is_initialized = info.get("isInitialized", False)

    reasons = []
    score = 100

    # Check mint authority (must be None = revoked)
    if mint_authority is not None:
        reasons.append("Mint authority NOT revoked (can print more tokens)")
        score -= 50

    # Check freeze authority (must be None = revoked)
    if freeze_authority is not None:
        reasons.append("Freeze authority NOT revoked (can freeze your tokens)")
        score -= 30

    # Decimals sanity check
    if decimals > MAX_DECIMALS:
        reasons.append(f"Unusual decimals: {decimals}")
        score -= 10

    # Supply sanity check (> 1 quintillion is suspicious)
    try:
        supply_int = int(supply_raw)
        if supply_int > 10**18:
            reasons.append(f"Extremely high supply: {supply_int}")
            score -= 10
    except (ValueError, TypeError):
        pass

    safe = len(reasons) == 0
    return {
        "safe": safe,
        "score": max(score, 0),
        "reasons": reasons,
        "mint_revoked": mint_authority is None,
        "freeze_revoked": freeze_authority is None,
        "decimals": decimals,
        "supply": supply_raw,
    }

def format_alert(pair: dict, safety: dict, changes: dict) -> str:
    """Format the alert message."""
    token = pair.get("baseToken", {})
    quote = pair.get("quoteToken", {})
    dex = pair.get("dexId", "Unknown")
    url = pair.get("url", "")
    token_address = token.get("address", "")

    price = float(pair.get("priceUsd", 0) or 0)
    volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
    volume_5m = float(pair.get("volume", {}).get("m5", 0) or 0)
    liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
    fdv = float(pair.get("fdv", 0) or 0)

    # Risk management (wider stops for meme coins)
    risk_pct = 0.10  # 10% stop
    sl = price * (1 - risk_pct)
    tp = price * (1 + (3 * risk_pct))  # 3RR = 30% target

    alert = (
        f"🔥 SOL MEME VOLUME SPIKE\n\n"
        f"**{token.get('symbol', '?')}** "
        f"({token_address[:8]}...{token_address[-4:]})\n"
        f"Dex: {dex} | "
        f"Quote: {quote.get('symbol', '?')} | "
        f"[Chart]({url})\n\n"
        f"Price: ${price:,.6f}\n"
        f"MCap: ${fdv:,.0f}\n"
        f"Liquidity: ${liquidity:,.0f}\n"
        f"Vol 5m: ${volume_5m:,.0f} | 24h: ${volume_24h:,.0f}\n\n"
        f"Changes: "
        f"5m {changes['m5']:+.1f}% | "
        f"1h {changes['h1']:+.1f}% | "
        f"6h {changes['h6']:+.1f}%\n\n"
        f"🛡️ Safety: {safety['score']}/100\n"
        f"  Mint revoked: {'✅' if safety['mint_revoked'] else '❌'}\n"
        f"  Freeze revoked: {'✅' if safety['freeze_revoked'] else '❌'}\n"
        f"  Decimals: {safety['decimals']}\n"
    )

    if safety.get("reasons"):
        alert += f"  Risks: {'; '.join(safety['reasons'])}\n"

    alert += (
        f"\n💰 Setup:\n"
        f"Entry: ${price:,.6f}\n"
        f"SL: ${sl:,.6f} (-{risk_pct*100:.0f}%)\n"
        f"TP: ${tp:,.6f} (+{3*risk_pct*100:.0f}% / 3RR)\n"
    )

    return alert

def main():
    state = load_state()
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()

    # Clean old alerts
    old_ts = now_ts - (ALERT_WINDOW_MIN * 60)
    state["alerted"] = {
        addr: ts for addr, ts in state.get("alerted", {}).items()
        if ts > old_ts
    }

    # Search for trending meme pairs
    all_pairs = {}  # keyed by token address to dedup
    for keyword in SEARCH_KEYWORDS:
        pairs = get_search_pairs(keyword)
        for p in pairs:
            token_addr = p.get("baseToken", {}).get("address", "")
            if token_addr and token_addr not in all_pairs:
                all_pairs[token_addr] = p

    if not all_pairs:
        print("SLEEP")
        return

    alerts_sent = []
    rpc_calls = 0
    max_rpc = 10  # rate limit protection

    for token_addr, pair in all_pairs.items():
        # Volume spike filter
        if not check_volume_spike(pair):
            continue

        # Price momentum filter
        changes = check_price_momentum(pair)
        if changes is None:
            continue

        # Dedup: skip if already alerted recently
        if token_addr in state.get("alerted", {}):
            continue

        # On-chain safety check (rate limited)
        if rpc_calls >= max_rpc:
            break

        safety = check_token_safety(token_addr)
        rpc_calls += 1

        if not safety["safe"]:
            continue

        # Format and queue alert
        alert = format_alert(pair, safety, changes)
        alerts_sent.append(alert)

        # Mark as alerted
        state.setdefault("alerted", {})[token_addr] = now_ts

    save_state(state)

    if not alerts_sent:
        print("SLEEP")
        return

    # Output all alerts
    for i, alert in enumerate(alerts_sent):
        if i > 0:
            print("\n" + "=" * 50 + "\n")
        print(alert)

    if len(alerts_sent) > 1:
        print(f"\n📊 {len(alerts_sent)} setups found")

if __name__ == "__main__":
    main()
