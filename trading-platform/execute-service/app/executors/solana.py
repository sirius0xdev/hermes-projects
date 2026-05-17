"""
Solana SDK integration for on-chain trade execution.
Uses solana-py for chain-level transaction construction and signing.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solana.transaction import Transaction

from app.config import settings

logger = logging.getLogger(__name__)

# Jupiter v6 router API for quote + swap
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6"


class SolanaExecutor:
    """Wrapper for Solana on-chain trade execution."""

    def __init__(self) -> None:
        self._client: AsyncClient | None = None
        self._keypair: Keypair | None = None
        self._initialized = False

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
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{JUPITER_QUOTE_API}/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": amount,
                    "slippageBps": 50,  # 0.5%
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def swap(
        self,
        quote_response: dict,
        priority_fee_lamports: int = 50000,
    ) -> dict[str, Any]:
        """Execute a swap using Jupiter quote and the signer's keypair."""
        await self.initialize()
        if not self._keypair:
            raise RuntimeError("No Solana keypair configured")
        if not self._client:
            raise RuntimeError("No RPC client")

        # Fetch swap transaction from Jupiter
        import httpx
        import base64
        from solders.transaction import VersionedTransaction

        async with httpx.AsyncClient() as client:
            swap_resp = await client.post(
                f"{JUPITER_QUOTE_API}/swap",
                json={
                    "quoteResponse": quote_response,
                    "userPublicKey": str(self._keypair.pubkey()),
                    "wrapAndUnwrapSol": True,
                    "priorityFeeLamports": priority_fee_lamports,
                    "dynamicComputeUnitLimit": True,
                },
                timeout=30,
            )
            swap_resp.raise_for_status()
            swap_data = swap_resp.json()

        # Deserialize and sign
        txn_bytes = base64.b64decode(swap_data["swapTransaction"])
        txn = VersionedTransaction.from_bytes(txn_bytes)
        signed = self._keypair.sign_transaction(txn)

        # Send to RPC
        result = await self._client.send_raw_transaction(
            bytes(signed.message),
            opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
        )
        tx_sig = result.value

        logger.info("Solana swap tx: %s", tx_sig)
        return {"tx_signature": str(tx_sig), "status": "submitted"}

    async def send_sol(
        self,
        to_address: str,
        lamports: int,
    ) -> dict[str, Any]:
        """Send raw SOL to an address."""
        await self.initialize()
        if not self._keypair:
            raise RuntimeError("No keypair configured")
        assert self._client is not None

        to_pubkey = Pubkey.from_string(to_address)
        txn = Transaction(fee_payer=self._keypair.pubkey()).add(
            self._create_transfer_instruction(to_pubkey, lamports)
        )

        txn.sign(self._keypair)
        result = await self._client.send_raw_transaction(
            bytes(txn.serialize()),
            opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
        )
        return {"tx_signature": str(result.value), "status": "submitted"}

    @staticmethod
    def _create_transfer_instruction(to: Pubkey, lamports: int):
        """Create a system transfer instruction (manual to avoid full Program import)."""
        from solana.system_program import TransferParams, transfer
        params = TransferParams(
            from_pubkey=Pubkey.from_string(""),  # placeholder, set by SDK
            to_pubkey=to,
            lamports=lamports,
        )
        return transfer(params)

    async def close(self) -> None:
        if self._client:
            await self._client.close()


# Minimal known mints for common tokens
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
