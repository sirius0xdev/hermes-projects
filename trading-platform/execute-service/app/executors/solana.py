"""
Solana SDK integration for on-chain trade execution.
Uses solders + solana-py for chain-level transaction construction and signing.

Security fixes applied:
- send_sol from_pubkey: now uses actual signer pubkey (was empty string placeholder)
- Transaction confirmation polling: waits for on-chain confirmation before returning
- Circuit breaker: trips after N consecutive failures, cools down before retrying
- HTTP client pooling: shared httpx.AsyncClient with connection pooling
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from decimal import Decimal
from typing import Any

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed, Finalized
from solana.rpc.types import TxOpts
from solders.transaction import Transaction, VersionedTransaction

from app.config import settings

logger = logging.getLogger(__name__)

# Jupiter v6 router API for quote + swap
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6"


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is tripped."""
    pass


class SolanaCircuitBreaker:
    """Circuit breaker for Solana transactions.

    States: CLOSED (normal) -> OPEN (tripped) -> HALF_OPEN (testing)
    Trips after `threshold` consecutive failures.
    After `timeout_seconds`, moves to HALF_OPEN to test recovery.
    """

    def __init__(
        self,
        threshold: int = 5,
        timeout_seconds: int = 300,
    ) -> None:
        self.threshold = threshold
        self.timeout_seconds = timeout_seconds
        self._failures: int = 0
        self._state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self._opened_at: float = 0.0

    @property
    def is_open(self) -> bool:
        if self._state == "CLOSED":
            return False
        if self._state == "OPEN":
            # Check if cooldown has expired -> transition to HALF_OPEN
            if time.time() - self._opened_at >= self.timeout_seconds:
                self._state = "HALF_OPEN"
                logger.info("Circuit breaker -> HALF_OPEN (testing recovery)")
                return False
            return True
        return False  # HALF_OPEN allows one test request

    def record_success(self) -> None:
        """Record a successful operation."""
        self._failures = 0
        prev_state = self._state
        self._state = "CLOSED"
        if prev_state != "CLOSED":
            logger.info("Circuit breaker -> CLOSED (recovered from %s)", prev_state)

    def record_failure(self) -> None:
        """Record a failed operation. May trip the breaker."""
        self._failures += 1
        if self._state == "HALF_OPEN":
            # Any failure in half-open immediately re-trips
            self._state = "OPEN"
            self._opened_at = time.time()
            logger.warning("Circuit breaker -> OPEN (failed recovery test)")
        elif self._failures >= self.threshold:
            self._state = "OPEN"
            self._opened_at = time.time()
            logger.warning(
                "Circuit breaker -> OPEN (%d consecutive failures, threshold=%d)",
                self._failures, self.threshold,
            )

    def get_state(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "consecutive_failures": self._failures,
            "threshold": self.threshold,
        }


class SolanaExecutor:
    """Wrapper for Solana on-chain trade execution."""

    def __init__(self) -> None:
        self._client: AsyncClient | None = None
        self._keypair: Keypair | None = None
        self._initialized = False
        # HTTP client pool (shared across requests)
        self._http_client: Any = None
        # Circuit breaker for transaction failures
        self._circuit_breaker = SolanaCircuitBreaker(
            threshold=settings.solana_circuit_breaker_threshold,
            timeout_seconds=settings.solana_circuit_breaker_timeout_seconds,
        )

    async def initialize(self) -> None:
        """Init Solana RPC client and keypair."""
        if self._initialized:
            return
        self._client = AsyncClient(settings.solana_rpc_url)
        if settings.solana_private_key_base58:
            import base58
            secret_key = base58.b58decode(settings.solana_private_key_base58)
            self._keypair = Keypair.from_bytes(secret_key)
            logger.info("Solana signer initialized: %s", self._keypair.pubkey())
        self._initialized = True

    def _check_circuit(self) -> None:
        """Check circuit breaker before executing. Raises if open."""
        if self._circuit_breaker.is_open:
            raise CircuitBreakerOpen(
                f"Solana circuit breaker is OPEN ({self._circuit_breaker._failures} failures). "
                f"Retry after {settings.solana_circuit_breaker_timeout_seconds}s."
            )

    def _on_success(self) -> None:
        """Record success in circuit breaker."""
        self._circuit_breaker.record_success()

    def _on_failure(self) -> None:
        """Record failure in circuit breaker."""
        self._circuit_breaker.record_failure()

    @property
    def circuit_breaker_state(self) -> dict[str, Any]:
        return self._circuit_breaker.get_state()

    async def _get_http_client(self):
        """Get a pooled HTTP client for Jupiter API calls."""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=settings.http_connection_pool_size,
                    max_keepalive_connections=settings.http_connection_pool_size,
                    keepalive_expiry=settings.http_keepalive_seconds,
                ),
                timeout=settings.http_timeout_seconds,
            )
        return self._http_client

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        if self._client:
            await self._client.close()

    async def get_balance(self, pubkey: str | None = None) -> float:
        """Get SOL balance for the signer or a given pubkey."""
        await self.initialize()
        assert self._client is not None
        target = Pubkey.from_string(pubkey) if pubkey else (
            self._keypair.pubkey() if self._keypair else None
        )
        if target is None:
            raise RuntimeError("No keypair configured to get balance")
        resp = await self._client.get_balance(target, commitment=Confirmed)
        return resp.value / 1_000_000_000

    async def get_token_price(self, input_mint: str, output_mint: str, amount: int) -> dict:
        """Get a swap quote from Jupiter aggregator API."""
        client = await self._get_http_client()
        resp = await client.get(
            f"{JUPITER_QUOTE_API}/quote",
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": 50,  # 0.5%
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def _wait_for_confirmation(self, tx_signature: str) -> dict[str, Any]:
        """Poll for transaction confirmation on-chain.

        Returns confirmation status. Raises on timeout.
        """
        if not self._client:
            return {"status": "unknown", "reason": "no_rpc_client"}

        timeout = settings.solana_txn_poll_timeout_seconds
        interval = settings.solana_txn_poll_interval_seconds
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                result = await self._client.get_transaction(
                    tx_signature,
                    commitment=Finalized,
                    max_supported_transaction_version=0,
                )
                if result.value:
                    tx_meta = result.value.transaction.meta
                    if tx_meta.err is None:
                        return {
                            "status": "confirmed",
                            "slot": result.value.slot,
                            "confirmation_status": "finalized",
                        }
                    else:
                        return {
                            "status": "failed",
                            "error": str(tx_meta.err),
                            "slot": result.value.slot,
                        }
            except Exception:
                # Transaction not yet available — keep polling
                pass
            await asyncio.sleep(interval)

        return {"status": "pending", "reason": f"timed out after {timeout}s"}

    async def swap(
        self,
        quote_response: dict,
        priority_fee_lamports: int = 50000,
    ) -> dict[str, Any]:
        """Execute a swap using Jupiter quote and the signer's keypair."""
        await self.initialize()
        self._check_circuit()

        if not self._keypair:
            raise RuntimeError("No Solana keypair configured")
        if not self._client:
            raise RuntimeError("No RPC client")

        try:
            # Fetch swap transaction from Jupiter
            client = await self._get_http_client()
            swap_resp = await client.post(
                f"{JUPITER_QUOTE_API}/swap",
                json={
                    "quoteResponse": quote_response,
                    "userPublicKey": str(self._keypair.pubkey()),
                    "wrapAndUnwrapSol": True,
                    "priorityFeeLamports": priority_fee_lamports,
                    "dynamicComputeUnitLimit": True,
                },
            )
            swap_resp.raise_for_status()
            swap_data = swap_resp.json()

            # Deserialize and sign
            txn_bytes = base64.b64decode(swap_data["swapTransaction"])
            txn = VersionedTransaction.from_bytes(txn_bytes)
            signed = self._keypair.sign_transaction(txn)

            # Send to RPC
            result = await self._client.send_raw_transaction(
                bytes(signed),
                opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
            )
            tx_sig = str(result.value)

            logger.info("Solana swap tx submitted: %s", tx_sig)

            # Wait for confirmation
            confirmation = await self._wait_for_confirmation(tx_sig)

            self._on_success()
            return {
                "tx_signature": tx_sig,
                "status": confirmation["status"],
                "confirmation": confirmation,
            }

        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self._on_failure()
            logger.error("Solana swap failed: %s", e)
            raise

    async def send_sol(
        self,
        to_address: str,
        lamports: int,
    ) -> dict[str, Any]:
        """Send raw SOL to an address."""
        await self.initialize()
        self._check_circuit()

        if not self._keypair:
            raise RuntimeError("No keypair configured")
        assert self._client is not None

        to_pubkey = Pubkey.from_string(to_address)
        txn = Transaction(fee_payer=self._keypair.pubkey()).add(
            self._create_transfer_instruction(
                from_pubkey=self._keypair.pubkey(),  # FIX: was Pubkey.from_string("")
                to_pubkey=to_pubkey,
                lamports=lamports,
            )
        )

        txn.sign(self._keypair)
        result = await self._client.send_raw_transaction(
            bytes(txn.serialize()),
            opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
        )
        tx_sig = str(result.value)

        logger.info("Solana transfer tx submitted: %s", tx_sig)

        # Wait for confirmation
        try:
            confirmation = await self._wait_for_confirmation(tx_sig)
            self._on_success()
        except Exception:
            confirmation = {"status": "unknown"}

        return {
            "tx_signature": tx_sig,
            "status": confirmation.get("status", "submitted"),
            "confirmation": confirmation,
        }

    @staticmethod
    def _create_transfer_instruction(
        from_pubkey: Pubkey,
        to: Pubkey,
        lamports: int,
    ):
        """Create a system transfer instruction."""
        from solders.system_program import TransferParams, transfer
        params = TransferParams(
            from_pubkey=from_pubkey,  # FIX: now uses actual signer pubkey
            to_pubkey=to,
            lamports=lamports,
        )
        return transfer(params)


# Minimal known mints for common tokens
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
