"""
Solana Whale Tracker — monitors large on-chain fund movements in real-time.

Architecture:
  • Rate-limited RPC client with exponential backoff for 429s
  • jsonParsed encoding to get structured token transfer instructions
  • Transfer detection: transferChecked, transfer, mintTo, burn (SPL Token)
  • Price: CoinGecko (SOL), hardcoded peg (stablecoins), on-chain for rest
  • Two modes: --scan (historical replay) and --stream (real-time WebSocket)
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# ─── Paths & logging ────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
LOG_PATH = BASE_DIR / "log.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("whale")

# ─── Config ─────────────────────────────────────────────────────────────────

def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

# ─── Data models ────────────────────────────────────────────────────────────

@dataclass
class WhaleAlert:
    timestamp: str
    signature: str
    slot: int
    amount: float
    token_symbol: str
    token_decimals: int
    usd_value: float
    from_address: str
    to_address: str
    from_label: str = ""
    to_label: str = ""
    tx_type: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

# ─── Rate-limited RPC client ────────────────────────────────────────────────

class SolanaRPC:
    """RPC client with per-second rate limiting and 429 backoff."""

    def __init__(self, config: dict):
        self.url = config["rpc"]["https"]
        self.wss = config["rpc"]["wss"]
        self.delay = config["behavior"]["rpc_delay_seconds"]
        self.max_retries = config["behavior"]["max_retries"]
        self.backoff_base = config["behavior"].get("backoff_base", 5)
        self._semaphore = asyncio.Semaphore(1)
        self._last_call = 0.0
        self._client = httpx.AsyncClient(
            base_url=self.url,
            timeout=httpx.Timeout(20),
            limits=httpx.Limits(max_connections=10),
        )

    async def _wait_rate_limit(self):
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self._last_call = time.monotonic()

    async def _request_with_backoff(self, method: str, params: Any) -> Any:
        async with self._semaphore:
            for attempt in range(self.max_retries):
                await self._wait_rate_limit()
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or [],
                }
                try:
                    resp = await self._client.post("/", json=payload)
                    if resp.status_code == 429:
                        wait = self.backoff_base * (attempt + 1)
                        logger.warning(f"429 rate limited, waiting {wait}s (attempt {attempt+1})")
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    if "error" in data:
                        raise RuntimeError(f"RPC error: {data['error']}")
                    return data.get("result")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        wait = self.backoff_base * (attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    raise
                except Exception:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1)
                    raise

    async def rpc(self, method: str, params: Any = None) -> Any:
        return await self._request_with_backoff(method, params)

    async def get_transaction(self, signature: str) -> dict | None:
        try:
            result = await self.rpc("getTransaction", [
                signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "transaction_details": "full"},
            ])
            return result
        except Exception as e:
            logger.debug(f"Failed to fetch TX {signature}: {e}")
            return None

    async def get_signatures(self, address: str, limit: int = 1000) -> list[dict]:
        return await self.rpc("getSignaturesForAddress", [
            address, {"limit": limit},
        ]) or []

    async def get_slot(self) -> int:
        return await self.rpc("getSlot") or 0

    async def close(self):
        await self._client.aclose()

# ─── Price fetcher ──────────────────────────────────────────────────────────

class PriceFetcher:
    def __init__(self, config: dict):
        self.tokens = {t["mint"]: t for t in config.get("monitored_tokens", [])}
        self._sol_price = 0.0
        self._sol_time = 0.0
        self._token_prices: dict[str, float] = {}
        self._token_times: dict[str, float] = {}
        self._client = httpx.AsyncClient(timeout=10)

    async def get_sol_price(self) -> float:
        if time.time() - self._sol_time < 120 and self._sol_price > 0:
            return self._sol_price

        try:
            resp = await self._client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "solana", "vs_currencies": "usd"},
            )
            resp.raise_for_status()
            self._sol_price = resp.json()["solana"]["usd"]
            self._sol_time = time.time()
            logger.info(f"SOL price: ${self._sol_price:,.2f}")
        except Exception as e:
            logger.warning(f"CoinGecko SOL price failed: {e}")

        return self._sol_price

    async def get_token_price(self, mint: str) -> float:
        # Check config for hardcoded price (stablecoins)
        token_cfg = self.tokens.get(mint, {})
        if "price_usd" in token_cfg:
            return float(token_cfg["price_usd"])

        # Check cache
        if mint in self._token_prices and time.time() - self._token_times.get(mint, 0) < 120:
            return self._token_prices[mint]

        # Fetch from CoinGecko (need coin ID mapping)
        price = await self._fetch_token_price(mint)
        return price

    async def _fetch_token_price(self, mint: str) -> float:
        # Mint -> CoinGecko ID mapping
        cg_map = {
            "7dHbWXmci3dT4UF99gs68iPjkOfUCzg5V2TLBoQD9vtn": "pyth-network",
            "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "bonk",
            "JUPyiwrYJFskUPiHa7hkeR8VUtk6BWo3eB6L9wqbF2j": "jupiter-exchange-solana",
            "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "msol",
            "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "ethereum",
            "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "dogwifcoin",
        }

        coin_id = cg_map.get(mint)
        if not coin_id:
            return 0.0

        try:
            resp = await self._client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
            )
            resp.raise_for_status()
            price = resp.json()[coin_id]["usd"]
            self._token_prices[mint] = price
            self._token_times[mint] = time.time()
            symbol = self.tokens.get(mint, {}).get("symbol", mint[:6])
            logger.info(f"{symbol} price: ${price:,.6f}")
            return price
        except Exception as e:
            logger.warning(f"Price fetch failed for {mint}: {e}")
            return self._token_prices.get(mint, 0.0)

    async def refresh_all(self):
        await self.get_sol_price()
        for mint in self._token_prices:
            await self._fetch_token_price(mint)

    async def close(self):
        await self._client.aclose()

# ─── Transaction parser ────────────────────────────────────────────────────

class TxParser:
    SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    SPL_TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
    SYSTEM_PROGRAM = "11111111111111111111111111111111"

    def __init__(self, config: dict, price: PriceFetcher):
        self.config = config
        self.price = price
        self.tokens = {t["mint"]: t for t in config.get("monitored_tokens", [])}
        self.watched = {w["address"]: w["label"] for w in config.get("watched_wallets", [])}
        self.sol_threshold = config["thresholds"]["sol_usd"]
        self.spl_threshold = config["thresholds"]["spl_usd"]

    def _label(self, addr: str) -> str:
        if addr in self.watched:
            return self.watched[addr]
        return addr[:4] + "…" + addr[-4:]

    def _find_associated_address(
        self, account_keys: list, loaded_keys_writable: list, loaded_keys_readonly: list, pubkey: str
    ) -> int | None:
        all_keys = account_keys + loaded_keys_writable + loaded_keys_readonly
        for i, ak in enumerate(all_keys):
            pk = ak if isinstance(ak, str) else ak.get("pubkey", "")
            if pk == pubkey:
                return i
        return None

    async def parse_transaction(self, tx: dict) -> list[WhaleAlert]:
        if not tx:
            return []

        meta = tx.get("meta", {})
        if meta.get("err") is not None:
            return []

        block_time = tx.get("blockTime", 0)
        slot = tx.get("slot", 0)
        signature = tx.get("signature", "")
        ts = datetime.fromtimestamp(block_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if block_time else ""

        account_keys = tx["transaction"]["message"].get("accountKeys", [])
        loaded_writable = meta.get("loadedAddresses", {}).get("writable", [])
        loaded_readonly = meta.get("loadedAddresses", {}).get("readonly", [])
        pre_balances = meta.get("preBalances", [])
        post_balances = meta.get("postBalances", [])

        sol_price = await self.price.get_sol_price()
        alerts: list[WhaleAlert] = []
        seen = set()  # dedup key: (from, to, mint, amount)

        # ── Parse SPL token transfers from innerInstructions ─────────────────
        for block in meta.get("innerInstructions", []):
            for instr in block.get("instructions", []):
                parsed = instr.get("parsed", {})
                if not parsed:
                    continue

                itype = parsed.get("type", "")
                info = parsed.get("info", {})

                if itype not in ("transfer", "transferChecked", "mintTo", "burn"):
                    continue

                mint = info.get("mint", "")

                # Determine source and destination
                if itype == "burn":
                    source = info.get("authority", info.get("owner", ""))
                    dest = "burn"
                else:
                    source = info.get("source", "")
                    dest = info.get("destination", "")

                # Get amount — transferChecked uses tokenAmount dict
                token_amount = info.get("tokenAmount", {})
                if token_amount:
                    raw_amount = token_amount.get("amount", "0")
                    decimals = token_amount.get("decimals", 6)
                    ui_amount = token_amount.get("uiAmount")
                else:
                    raw_amount = info.get("amount", "0")
                    decimals = self.tokens.get(mint, {}).get("decimals", 6)
                    ui_amount = None

                try:
                    amount = int(raw_amount)
                except (ValueError, TypeError):
                    try:
                        amount = int(float(raw_amount))
                    except (ValueError, TypeError):
                        continue

                if amount <= 0:
                    continue

                readable = amount / (10 ** decimals)
                symbol = self.tokens.get(mint, {}).get("symbol", mint[:8])

                token_price = await self.price.get_token_price(mint)
                usd = readable * token_price

                # Dedup
                dedup = (source, dest, mint, amount)
                if dedup in seen:
                    continue
                seen.add(dedup)

                # Check threshold or watched wallet
                if usd >= self.spl_threshold or source in self.watched or dest in self.watched:
                    alerts.append(WhaleAlert(
                        timestamp=ts,
                        signature=signature,
                        slot=slot,
                        amount=readable,
                        token_symbol=symbol,
                        token_decimals=decimals,
                        usd_value=usd,
                        from_address=source,
                        to_address=dest,
                        from_label=self._label(source),
                        to_label=self._label(dest) if dest != "burn" else "🔥 Burn",
                        tx_type=itype,
                    ))

        # ── SOL transfers from balance changes ──────────────────────────────
        # Collect all account SOL balance changes, then pair senders with receivers
        sol_moves: list[tuple[str, float]] = []  # (address, +SOL received)
        if pre_balances and post_balances and len(pre_balances) == len(post_balances):
            for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
                diff = post - pre
                if diff == 0:
                    continue

                # Resolve account
                if i < len(account_keys):
                    ak = account_keys[i]
                    addr = ak if isinstance(ak, str) else ak.get("pubkey", "")
                elif i - len(account_keys) < len(loaded_writable):
                    addr = loaded_writable[i - len(account_keys)]
                else:
                    addr = f"computed_{i}"

                # Skip known program accounts
                if addr in (self.SPL_TOKEN_PROGRAM, self.SPL_TOKEN_2022, self.SYSTEM_PROGRAM):
                    continue

                sol_moves.append((addr, diff / 1e9))

        # Pair senders (negative diff) with receivers (positive diff) as SOL transfers
        if sol_moves:
            senders = [(addr, abs(d)) for addr, d in sol_moves if d < 0 and abs(d) > 0.001]
            receivers = [(addr, d) for addr, d in sol_moves if d > 0 and d > 0.001]

            # Simple pairing: match by amount (within 0.001 SOL tolerance for fees)
            used_receivers: set[int] = set()
            for s_addr, s_amount in senders:
                best_r = None
                best_idx = -1
                best_diff = float("inf")
                for ri, (r_addr, r_amount) in enumerate(receivers):
                    if ri in used_receivers:
                        continue
                    amt_diff = abs(s_amount - r_amount)
                    if amt_diff < best_diff:
                        best_diff = amt_diff
                        best_r = r_addr
                        best_idx = ri

                if best_r is not None and best_diff < 0.01:  # Within 0.01 SOL
                    used_receivers.add(best_idx)
                    sol_amount = s_amount
                    sol_usd = sol_amount * sol_price

                    dedup = (s_addr, best_r, "SOL", int(s_amount * 1e9))
                    if dedup in seen:
                        continue
                    seen.add(dedup)

                    if sol_usd >= self.sol_threshold or s_addr in self.watched or best_r in self.watched:
                        alerts.append(WhaleAlert(
                            timestamp=ts,
                            signature=signature,
                            slot=slot,
                            amount=sol_amount,
                            token_symbol="SOL",
                            token_decimals=9,
                            usd_value=sol_usd,
                            from_address=s_addr,
                            to_address=best_r,
                            from_label=self._label(s_addr),
                            to_label=self._label(best_r),
                            tx_type="sol_transfer",
                        ))

        return alerts

# ─── Output formatter ───────────────────────────────────────────────────────

class Formatter:
    def __init__(self, config: dict):
        self.config = config
        self.console = Console()
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _whale_emoji(self, usd: float) -> str:
        if usd >= 10_000_000:
            return "🐋🐋🐋"
        if usd >= 1_000_000:
            return "🐋"
        if usd >= 500_000:
            return "🐳"
        if usd >= 100_000:
            return "🐬"
        return "🐟"

    def print_banner(self, sol_price: float):
        tokens = ", ".join(t["symbol"] for t in self.config.get("monitored_tokens", []))
        self.console.print(Panel(
            f"[bold green]Monitoring Solana mainnet[/]\n"
            f"SOL price: ${sol_price:,.2f}\n"
            f"SOL threshold: ${self.config['thresholds']['sol_usd']:,.0f}+\n"
            f"SPL threshold: ${self.config['thresholds']['spl_usd']:,.0f}+\n"
            f"Monitored: {tokens}\n"
            f"RPC: {self.config['rpc']['https']}",
            title="🐋 Solana Whale Tracker",
            border_style="bold green",
        ))

    def print_alert(self, alert: WhaleAlert):
        emoji = self._whale_emoji(alert.usd_value)
        decimals = 2 if alert.token_symbol == "SOL" else min(alert.token_decimals, 4)
        sig_short = alert.signature[:8] + "…" + alert.signature[-4:]

        self.console.print(f"\n{emoji} [bold yellow]${alert.usd_value:,.0f}[/] "
                          f"[green]{alert.amount:,.{decimals}} {alert.token_symbol}[/]\n"
                          f"   [cyan]{alert.from_label}[/] → [cyan]{alert.to_label}[/]\n"
                          f"   [{alert.tx_type}] {sig_short}\n"
                          f"   {alert.timestamp}")

    def print_summary(self, alerts: list[WhaleAlert]):
        if not alerts:
            self.console.print("\n[yellow]No whale movements detected.[/]")
            return

        top_n = self.config["thresholds"]["top_n"]
        top = sorted(alerts, key=lambda a: a.usd_value, reverse=True)[:top_n]

        table = Table(title=f"🐋 Top {len(top)} Whale Movements", show_header=True, header_style="bold cyan")
        table.add_column("Time", style="dim", width=20)
        table.add_column("Token", style="bold green", width=8)
        table.add_column("Amount", justify="right", style="green", width=15)
        table.add_column("USD", justify="right", style="bold yellow", width=12)
        table.add_column("From", style="cyan", width=14)
        table.add_column("To", style="cyan", width=14)
        table.add_column("Type", style="dim", width=8)

        for a in top:
            decimals = 2 if a.token_symbol == "SOL" else min(a.token_decimals, 4)
            table.add_row(
                a.timestamp[:19] if a.timestamp else "",
                a.token_symbol,
                f"{a.amount:,.{decimals}}",
                f"${a.usd_value:,.0f}",
                a.from_label[:14],
                a.to_label[:14],
                a.tx_type[:8],
            )

        self.console.print()
        self.console.print(table)

    def log_alert(self, alert: WhaleAlert):
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(alert.to_dict()) + "\n")

    def export_csv(self, alerts: list[WhaleAlert], path: str = str(BASE_DIR / "alerts.csv")):
        if not alerts:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp", "signature", "slot", "amount",
                                                "token_symbol", "usd_value", "from_address",
                                                "to_address", "from_label", "to_label", "tx_type"])
            w.writeheader()
            for a in alerts:
                w.writerow(a.to_dict())
        self.console.print(f"[green]Exported {len(alerts)} alerts → {path}[/]")

# ─── Scanner (historical mode) ──────────────────────────────────────────────

class Scanner:
    """Scan recent transactions for whale movements."""

    # Programs/wallets that handle large volumes
    SCAN_ADDRESSES = [
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # SPL Token
        "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTMBV",  # Jupiter
        "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM
    ]

    def __init__(self, config: dict):
        self.config = config
        self.rpc = SolanaRPC(config)
        self.parser = TxParser(config, PriceFetcher(config))
        self.formatter = Formatter(config)

    async def scan(self, num_txs: int = 500):
        logger.info(f"Scanning last {num_txs} transactions across {len(self.SCAN_ADDRESSES)} sources...")

        all_alerts: list[WhaleAlert] = []
        seen_sigs: set[str] = set()
        per_source = max(num_txs // len(self.SCAN_ADDRESSES), 100)

        for addr in self.SCAN_ADDRESSES:
            sigs = await self.rpc.get_signatures(addr, limit=per_source)
            for s in sigs:
                sig = s["signature"]
                if sig in seen_sigs or s.get("err") is not None:
                    continue
                seen_sigs.add(sig)

                tx = await self.rpc.get_transaction(sig)
                if tx:
                    alerts = await self.parser.parse_transaction(tx)
                    all_alerts.extend(alerts)

            # Progress
            progress = len(seen_sigs)
            logger.info(f"  Scanned {progress} unique TXs from {addr[:8]}…")

        # Dedup by signature
        unique: dict[str, WhaleAlert] = {}
        for a in all_alerts:
            key = f"{a.signature}:{a.token_symbol}:{a.from_address}:{a.to_address}"
            if key not in unique:
                unique[key] = a

        unique_alerts = list(unique.values())
        unique_alerts.sort(key=lambda a: a.usd_value, reverse=True)

        self.formatter.print_summary(unique_alerts)
        self.formatter.export_csv(unique_alerts)

        for a in unique_alerts[:10]:
            self.formatter.log_alert(a)

        logger.info(f"Scan complete: {len(unique_alerts)} whale alerts from {len(seen_sigs)} transactions")

        await self.parser.price.close()
        await self.rpc.close()

# ─── Streamer (real-time mode) ──────────────────────────────────────────────

class Streamer:
    """Real-time whale detection via WebSocket."""

    def __init__(self, config: dict):
        self.config = config
        self.rpc = SolanaRPC(config)
        self.parser = TxParser(config, PriceFetcher(config))
        self.formatter = Formatter(config)
        self.alerts: list[WhaleAlert] = []
        self.running = False

    async def stream(self):
        import websockets

        self.running = True
        self.formatter.print_banner(await self.parser.price.get_sol_price())

        # Subscribe to logs mentioning Token + System programs
        filters = [
            {"mentions": ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"]},
            {"mentions": ["11111111111111111111111111111111"]},
        ]

        seen: set[str] = set()
        pending: asyncio.Queue[str] = asyncio.Queue(maxsize=200)

        async def processor():
            local_rpc = SolanaRPC(self.config)
            try:
                while self.running:
                    sig = await pending.get()
                    try:
                        tx = await local_rpc.get_transaction(sig)
                        if tx:
                            alerts = await self.parser.parse_transaction(tx)
                            for a in alerts:
                                self.formatter.print_alert(a)
                                self.formatter.log_alert(a)
                                self.alerts.append(a)
                                if len(self.alerts) > self.config["behavior"]["max_history"]:
                                    self.alerts = self.alerts[-1000:]
                    except Exception as e:
                        logger.debug(f"Process error: {e}")
                    finally:
                        pending.task_done()
            except asyncio.CancelledError:
                pass
            finally:
                await local_rpc.close()

        proc_task = asyncio.create_task(processor())

        try:
            while self.running:
                async with websockets.connect(
                    self.rpc.wss,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    logger.info(f"WebSocket connected to {self.rpc.wss}")

                    # Subscribe to both filters
                    for i, filt in enumerate(filters):
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0", "id": i + 1,
                            "method": "logsSubscribe",
                            "params": [filt, {"commitment": "confirmed"}],
                        }))
                        resp = await ws.recv()
                        logger.debug(f"Sub {i+1}: {resp[:100]}")

                    try:
                        while self.running:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(msg)
                            if "params" not in data:
                                continue
                            value = data["params"].get("result", {}).get("value", {})
                            sig = value.get("signature", "")

                            if sig and sig not in seen:
                                seen.add(sig)
                                if len(seen) > 20000:
                                    seen = set(list(seen)[-10000:])
                                try:
                                    pending.put_nowait(sig)
                                except asyncio.QueueFull:
                                    logger.warning("Queue full, dropping TX")

                            # Periodic summary
                            if len(self.alerts) > 0 and len(self.alerts) % 10 == 0:
                                self.formatter.print_summary(self.alerts)

                    except websockets.exceptions.ConnectionClosed:
                        logger.info("Connection closed, reconnecting...")
                    except asyncio.TimeoutError:
                        logger.info("Ping timeout, reconnecting...")

        finally:
            proc_task.cancel()
            await self.parser.price.close()
            await self.rpc.close()

# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import click

    @click.group()
    def cli():
        """Solana Whale Tracker — monitor large on-chain fund movements."""
        pass

    @cli.command()
    @click.option("--txs", type=int, default=500, help="Number of recent TXs to scan")
    @click.option("--config", type=click.Path(), default=str(CONFIG_PATH))
    def scan(txs, config):
        """Scan recent transactions for whale movements."""
        cfg = load_config(Path(config))
        scanner = Scanner(cfg)
        asyncio.run(scanner.scan(txs))

    @cli.command()
    @click.option("--config", type=click.Path(), default=str(CONFIG_PATH))
    def stream(config):
        """Stream whale alerts in real-time via WebSocket."""
        cfg = load_config(Path(config))
        st = Streamer(cfg)
        try:
            asyncio.run(st.stream())
        except KeyboardInterrupt:
            st.running = False
            logger.info("\nStopped.")

    @cli.command()
    @click.option("--output", type=click.Path(), default=str(BASE_DIR / "alerts.csv"))
    def export(output):
        """Export logged alerts to CSV."""
        alerts = []
        if LOG_PATH.exists():
            with open(LOG_PATH) as f:
                for line in f:
                    alerts.append(WhaleAlert(**json.loads(line)))

        fmt = Formatter(load_config())
        fmt.print_summary(alerts)
        fmt.export_csv(alerts, output)
        click.echo(f"\nExported {len(alerts)} alerts → {output}")

    cli()


if __name__ == "__main__":
    main()
