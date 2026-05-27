"""Solana + Jupiter WebSocket ingester — subscribes to on-chain events via
Helius and Jupiter WebSocket feeds, parses them, and publishes to Kafka.

Helius WebSocket (account/signature/slot subscriptions):
  - Token transfers  -> solana.token.data
  - Pool LP events   -> solana.pool.data
  - New blocks       -> solana.block.v1

Jupiter WebSocket (swap event notifications):
  - DEX swaps        -> market-data.trades

Usage as sidecar (started from consumer_service.py lifespan):
    helius = HeliusIngester(producer, helius_api_key)
    helius.start()  # spawns asyncio task

    jupiter = JupiterIngester(producer)
    jupiter.start()
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Union

import websockets  # type: ignore

from data_service.app.kafka.schemas import (
    JupiterSwapEvent,
    SolanaBlockEvent,
    SolanaPoolEvent,
    SolanaTokenTransfer,
)

logger = logging.getLogger(__name__)


# ─── Known mint -> symbol map (populated at runtime, seed here) ───────────

KNOWN_MINTS: dict[str, str] = {
    "So11111111111111111111111111111111111111112": "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtk6BWo3eB6L9wqbF2j": "JUP",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "ETH",
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
    "7dHbWXmci3dT4UF99gs68iPjkOfUCzg5V2TLBoQD9vtn": "PYTH",
    "7i5KKsX2weiTkry7jA4ZwSuHuc7QDb9RHmapZYkrcVy3": "BOME",
    "rndrizKT3MK1iimdxRdWabcFfZ7RvdefNgj4aVorD3a": "rndr",
}


# ─── Helius WebSocket Ingester ─────────────────────────────────────────────

class HeliusIngester:
    """Subscribe to Solana mainnet events via Helius WebSocket API.

    Subscriptions:
      - newSlots             -> SolanaBlockEvent -> solana.block.v1
      - signatureSubscribe   -> SolanaTokenTransfer / SolanaPoolEvent
      - accountSubscribe     -> Pool LP events
    """

    def __init__(
        self,
        producer: Any,
        api_key: Optional[str] = None,
        monitored_mints: Optional[list[str]] = None,
        monitored_pools: Optional[list[str]] = None,
    ):
        self.producer = producer
        self.api_key = api_key or os.getenv("HELIUS_API_KEY", "")
        self.monitored_mints = monitored_mints or []
        self.monitored_pools = monitored_pools or []

        # WebSocket URL — Helius mainnet
        if self.api_key:
            self.ws_url = f"wss://atlas.mainnet.helius.xyz/v0/WS?api-key={self.api_key}"
        else:
            # Fallback to public Solana WS
            self.ws_url = "wss://api.mainnet-beta.solana.com"

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._mints: dict[str, str] = dict(KNOWN_MINTS)

    def start(self) -> None:
        """Start the Helius WebSocket ingester as an asyncio background task."""
        self._running = True
        self._task = asyncio.ensure_future(self._run_loop())
        logger.info(
            "HeliusIngester started (ws=%s, mints=%d, pools=%d)",
            self.ws_url, len(self.monitored_mints), len(self.monitored_pools),
        )

    def stop(self) -> None:
        """Stop the Helius WebSocket ingester."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("HeliusIngester stopped")

    async def _run_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        reconnect_delay = 1
        max_reconnect_delay = 60

        while self._running:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                logger.info("HeliusIngester task cancelled")
                break
            except Exception:
                logger.exception("HeliusIngester error, reconnecting in %ds", reconnect_delay)
            finally:
                if self._running:
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    async def _connect_and_run(self) -> None:
        """Connect, subscribe, then read messages."""
        async with websockets.connect(self.ws_url) as ws:
            logger.info("HeliusIngester connected to %s", self.ws_url)

            # Subscribe to new slots (blocks)
            await self._subscribe_slots(ws)

            # Subscribe to monitored mints (token transfers)
            for mint in self.monitored_mints:
                await self._subscribe_account(ws, mint)

            # Subscribe to monitored pool accounts (LP events)
            for pool in self.monitored_pools:
                await self._subscribe_account(ws, pool)

            # Read messages
            async for raw in ws:
                if not self._running:
                    break
                try:
                    self._handle_helius_message(raw)
                except Exception:
                    logger.exception("Error handling Helius message")

    async def _subscribe_slots(self, ws: Any) -> None:
        """Subscribe to new slots (blocks)."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "slotSubscribe",
            "params": [
                {"postFilter": {"status": "rooted"}},
                {"commitment": "rooted"}
            ],
        }
        await ws.send(json.dumps(payload))
        logger.debug("Subscribed to slot events")

    async def _subscribe_account(self, ws: Any, account: str) -> None:
        """Subscribe to an account (mint or pool)."""
        payload = {
            "jsonrpc": "2.0",
            "id": hash(account) % 100000,
            "method": "accountSubscribe",
            "params": [
                account,
                {"encoding": "jsonParsed"}
            ],
        }
        await ws.send(json.dumps(payload))
        logger.debug("Subscribed to account %s", account)

    def _handle_helius_message(self, raw: Union[str, bytes]) -> None:
        """Parse a Helius WS message and dispatch to handlers."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Subscription notifications have "result" key
        result = msg.get("result")
        if result is None:
            return

        # Check subscription method in context
        ctx = result.get("context", {})
        slot = ctx.get("slot", 0)

        value = result.get("value", {})
        err = result.get("err")
        if err:
            logger.debug("Helius event error: %s", err)
            return

        # New slot / block event
        if isinstance(value, int) or isinstance(result, dict) and "slot" in result:
            self._handle_block_event(result)
            return

        # Account update
        if value and isinstance(value, dict):
            account_data = value.get("data", {})
            account_type = account_data.get("program", "")
            account_parsed = account_data.get("parsed", {})

            # Check if this is a slot notification
            if isinstance(value, int):
                self._handle_block_event({"slot": value})
                return

            self._handle_account_event(account_data, account_type, account_parsed, slot)

    def _handle_block_event(self, data: dict) -> None:
        """Handle new Solana block event."""
        slot = data.get("slot", data.get("parentSlot", 0))
        if not slot:
            return

        try:
            block_event = SolanaBlockEvent(
                slot=slot,
                block_height=slot,  # approximate
                blockhash=data.get("parentRoot", ""),
                parent_slot=data.get("parentSlot", 0),
                block_time=datetime.utcnow(),
                transactions_count=data.get("transactionsCount"),
            )
            self.producer.send_solana_block_event(block_event)
        except Exception:
            logger.exception("Error publishing SolanaBlockEvent for slot %d", slot)

    def _handle_account_event(
        self,
        account_data: dict,
        program: str,
        parsed: dict,
        slot: int,
    ) -> None:
        """Handle account update events (token transfers, pool LP)."""
        # Token program account
        if program in ("spl-token", "spl-token-2022"):
            info = parsed.get("info", {})
            token_type = parsed.get("type", "")

            # Check if this is a token mint account with transfers
            mint = info.get("mint", "")
            if mint and mint in self.monitored_mints:
                # This account changed — likely a transfer
                self._handle_token_transfer(
                    account_data, mint, token_type, slot, info
                )

        # Pool program account (e.g., Raydium, Orca, Jupiter)
        if self._is_pool_account(account_data):
            self._handle_pool_event(account_data, slot)

    def _handle_token_transfer(
        self,
        account_data: dict,
        mint: str,
        token_type: str,
        slot: int,
        info: dict,
    ) -> None:
        """Parse and publish a token transfer event."""
        try:
            token_amount = info.get("tokenAmount", {})
            amount_str = token_amount.get("amount", "0")
            decimals = token_amount.get("decimals", 6)
            ui_amount = token_amount.get("uiAmount", 0)

            symbol = self._mints.get(mint, mint[:8])

            # Owner is the token account holder
            owner = info.get("owner", "")

            event = SolanaTokenTransfer(
                signature=account_data.get("signature", ""),
                slot=slot,
                mint=mint,
                token_symbol=symbol,
                amount=Decimal(str(ui_amount)) if ui_amount else Decimal("0"),
                decimals=decimals,
                from_address=owner,
                to_address=owner,
                tx_type=token_type,
                block_time=datetime.utcnow(),
            )
            self.producer.send_solana_token_transfer(event)
        except (InvalidOperation, ValueError) as e:
            logger.warning("Invalid token amount for mint %s: %s", mint, e)

    def _handle_pool_event(self, account_data: dict, slot: int) -> None:
        """Parse and publish a pool LP event."""
        try:
            data = account_data.get("data", {})
            parsed = data.get("parsed", {})
            info = parsed.get("info", {})

            event = SolanaPoolEvent(
                signature=account_data.get("signature", ""),
                slot=slot,
                pool_address=account_data.get("pubkey", ""),
                token_a_mint=info.get("mintA", ""),
                token_b_mint=info.get("mintB", ""),
                token_a_amount=Decimal(str(info.get("reserveA", 0))),
                token_b_amount=Decimal(str(info.get("reserveB", 0))),
                lp_amount=Decimal(str(info.get("lpSupply", 0))),
                action="update",
                actor=info.get("authority", ""),
                block_time=datetime.utcnow(),
            )
            self.producer.send_solana_pool_event(event)
        except (InvalidOperation, ValueError) as e:
            logger.warning("Invalid pool data: %s", e)

    def _is_pool_account(self, account_data: dict) -> bool:
        """Check if account belongs to a monitored pool."""
        pubkey = account_data.get("pubkey", "")
        return pubkey in self.monitored_pools

    @property
    def is_running(self) -> bool:
        return self._running


# ─── Jupiter WebSocket Ingester ────────────────────────────────────────────

class JupiterIngester:
    """Subscribe to Jupiter DEX swap events via Jupiter WebSocket API.

    Jupiter's OpenAPI provides transaction notifications via WebSocket:
    wss://openapi.jup.ag/v1/transactions/v2/notifications

    Falls back to polling if WS unavailable.
    """

    def __init__(
        self,
        producer: Any,
        api_key: Optional[str] = None,
    ):
        self.producer = producer
        self.api_key = api_key or os.getenv("JUPITER_API_KEY", "")
        self.ws_url = "wss://quote-api.jup.ag/v6/update"
        # Jupiter also has a dedicated swap notifications endpoint
        self.swap_ws_url = "wss://openapi.jup.ag/v1/transactions/v2/notifications"

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._mints: dict[str, str] = dict(KNOWN_MINTS)

    def start(self) -> None:
        """Start the Jupiter WebSocket ingester."""
        self._running = True
        self._task = asyncio.ensure_future(self._run_loop())
        logger.info("JupiterIngester started (ws=%s)", self.ws_url)

    def stop(self) -> None:
        """Stop the Jupiter WebSocket ingester."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("JupiterIngester stopped")

    async def _run_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        reconnect_delay = 1
        max_reconnect_delay = 60

        while self._running:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                logger.info("JupiterIngester task cancelled")
                break
            except Exception:
                logger.exception("JupiterIngester error, reconnecting in %ds", reconnect_delay)
            finally:
                if self._running:
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    async def _connect_and_run(self) -> None:
        """Connect to Jupiter WS, subscribe, then read messages."""
        # Try swap notifications first, fall back to quote updates
        try:
            await self._run_swap_notifications()
        except Exception:
            logger.warning("Swap notifications failed, falling back to quote API")
            await self._run_quote_updates()

    async def _run_swap_notifications(self) -> None:
        """Subscribe to Jupiter swap transaction notifications."""
        async with websockets.connect(self.swap_ws_url) as ws:
            logger.info("Connected to Jupiter swap notifications")

            # Subscribe to swap events
            subscribe_payload = {
                "type": "subscribe",
                "filters": {
                    "eventTypes": ["swap"]
                },
            }
            if self.api_key:
                subscribe_payload["apiKey"] = self.api_key

            await ws.send(json.dumps(subscribe_payload))
            logger.info("Subscribed to Jupiter swap events")

            # Read messages
            async for raw in ws:
                if not self._running:
                    break
                try:
                    self._handle_jupiter_message(raw)
                except Exception:
                    logger.exception("Error handling Jupiter message")

    async def _run_quote_updates(self) -> None:
        """Fallback: subscribe to Jupiter quote price updates."""
        async with websockets.connect(self.ws_url) as ws:
            logger.info("Connected to Jupiter quote API")

            # Subscribe to price updates
            subscribe_payload = {
                "type": "subscribe",
                "pairs": [],  # empty = all pairs
            }
            await ws.send(json.dumps(subscribe_payload))

            async for raw in ws:
                if not self._running:
                    break
                try:
                    self._handle_quote_update(raw)
                except Exception:
                    logger.exception("Error handling Jupiter quote update")

    def _handle_jupiter_message(self, raw: Union[str, bytes]) -> None:
        """Parse and publish Jupiter swap event."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Handle different Jupiter message formats
        event_type = data.get("type", "")
        if event_type == "swap":
            swap_data = data.get("data", data)
            self._publish_swap_event(swap_data)
        elif event_type == "transaction":
            tx_data = data.get("data", data)
            self._publish_swap_event(tx_data)
        elif "inMint" in data or "inputMint" in data:
            # Direct swap event
            self._publish_swap_event(data)

    def _publish_swap_event(self, data: dict) -> None:
        """Create and publish a JupiterSwapEvent."""
        try:
            # Handle Jupiter API field naming
            in_mint = data.get("inMint") or data.get("inputMint", "")
            out_mint = data.get("outMint") or data.get("outputMint", "")
            in_amount = data.get("inAmount") or data.get("inputAmount", "0")
            out_amount = data.get("outAmount") or data.get("outputAmount", "0")
            in_ui = data.get("inTokenAmount") or data.get("inputTokenAmount", in_amount)
            out_ui = data.get("outTokenAmount") or data.get("outputTokenAmount", out_amount)

            # Handle numeric types (string vs int vs Decimal)
            def to_decimal(v: Any) -> Decimal:
                if v is None:
                    return Decimal("0")
                if isinstance(v, (int, float, Decimal)):
                    return Decimal(str(v))
                return Decimal(str(v))

            event = JupiterSwapEvent(
                signature=data.get("signature", data.get("txId", "")),
                slot=data.get("slot", 0),
                in_mint=in_mint,
                in_amount=to_decimal(in_amount),
                in_token_amount=to_decimal(in_ui),
                out_mint=out_mint,
                out_amount=to_decimal(out_amount),
                out_token_amount=to_decimal(out_ui),
                platform_fee=to_decimal(data.get("platformFee")),
                referrer_fee=to_decimal(data.get("referrerFee")),
                fee_amount=to_decimal(data.get("feeAmount", 0)),
                fee_mint=data.get("feeMint"),
                swap_source=data.get("swapSource") or data.get("amm", ""),
                user=data.get("user") or data.get("userPubkey", ""),
                block_time=data.get("blockTime") and datetime.fromtimestamp(
                    data["blockTime"] / 1000, tz=timezone.utc
                ).replace(tzinfo=None) or datetime.utcnow(),
            )

            # Also publish as a market trade for Jupiter swaps
            from data_service.app.kafka.schemas import TradeEvent, TradeSide

            # Derive trade side from token flow
            side = TradeSide.BUY if out_mint in (
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
            ) else TradeSide.SELL

            trade = TradeEvent(
                trade_id=f"jup-{data.get('signature', '')}",
                symbol=f"{self._mints.get(in_mint, in_mint[:8])}-{self._mints.get(out_mint, out_mint[:8])}",
                price=to_decimal(out_amount) / to_decimal(in_amount) if to_decimal(in_amount) > 0 else Decimal("0"),
                quantity=to_decimal(in_ui),
                side=side,
                source="jupiter",  # type: ignore
                timestamp=event.block_time,
                metadata={
                    "signature": event.signature,
                    "slot": event.slot,
                    "swap_source": event.swap_source,
                    "user": event.user,
                },
            )
            self.producer.send_trade(trade)

        except (InvalidOperation, ValueError, ZeroDivisionError) as e:
            logger.warning("Error parsing Jupiter swap event: %s", e)
        except Exception:
            logger.exception("Error publishing JupiterSwapEvent")

    def _handle_quote_update(self, raw: Union[str, bytes]) -> None:
        """Handle Jupiter quote price update (fallback mode)."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Publish price updates as market price events
        pairs = data.get("data", data)
        if isinstance(pairs, dict):
            pairs = [pairs]

        for pair in pairs:
            try:
                from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource

                symbol = pair.get("symbol", "")
                price = pair.get("price")
                if not symbol or not price:
                    continue

                event = MarketPriceEvent(
                    symbol=symbol,
                    price=Decimal(str(price)),
                    bid=Decimal(str(pair.get("bidPrice", 0))),
                    ask=Decimal(str(pair.get("askPrice", 0))),
                    volume_24h=Decimal(str(pair.get("volume24h", 0))),
                    change_24h=Decimal(str(pair.get("change24h", 0))),
                    high_24h=Decimal(str(pair.get("high24h", 0))),
                    low_24h=Decimal(str(pair.get("low24h", 0))),
                    source=PriceSource.JUPITER,
                    timestamp=datetime.utcnow(),
                )
                self.producer.send_price(event)
            except (InvalidOperation, ValueError) as e:
                logger.warning("Error parsing quote update: %s", e)

    @property
    def is_running(self) -> bool:
        return self._running
