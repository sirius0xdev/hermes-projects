"""
Order management service: handles order lifecycle (place, cancel, modify, track).
Coordinates between Hyperliquid and Solana executors.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_models import OrderRecord
from app.models.position_models import PositionRecord
from app.executors.hyperliquid import HyperliquidExecutor
from app.executors.solana import SolanaExecutor

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages order lifecycle across chains."""

    def __init__(self, hl_exec: HyperliquidExecutor, sol_exec: SolanaExecutor) -> None:
        self.hl = hl_exec
        self.sol = sol_exec

    def _generate_client_order_id(self) -> str:
        return f"ord-{uuid.uuid4().hex[:12]}"

    async def place_order(
        self,
        session: AsyncSession,
        wallet_address: str,
        chain: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        reduce_only: bool = False,
        time_in_force: str = "GTC",
    ) -> OrderRecord:
        """Place an order and persist the record."""
        client_order_id = self._generate_client_order_id()

        record = OrderRecord(
            client_order_id=client_order_id,
            wallet_address=wallet_address,
            chain=chain,
            symbol=symbol,
            side=side,
            order_type=order_type,
            status="pending",
            quantity=str(quantity),
            price=str(price) if price else None,
            stop_price=str(stop_price) if stop_price else None,
            reduce_only=reduce_only,
            time_in_force=time_in_force,
        )
        session.add(record)
        await session.flush()

        try:
            if chain == "hyperliquid":
                result = await self._place_hyperliquid_order(
                    symbol=symbol,
                    is_buy=(side == "buy"),
                    size=quantity,
                    order_type=order_type,
                    price=price,
                    stop_price=stop_price,
                    reduce_only=reduce_only,
                    tif=time_in_force,
                )
            elif chain == "solana":
                result = await self._place_solana_order(
                    symbol=symbol,
                    is_buy=(side == "buy"),
                    size=quantity,
                    price=price,
                )
            else:
                raise ValueError(f"Unsupported chain: {chain}")

            record.status = "submitted"
            record.external_order_id = result.get("tx_signature") or result.get("response", {}).get("response", {}).get("statuses", [{}])[0].get("resting", {}).get("oid", "")
            await session.commit()
            return record

        except Exception as e:
            record.status = "rejected"
            record.error_message = str(e)
            await session.commit()
            logger.error("Order %s rejected: %s", client_order_id, e)
            raise

    async def _place_hyperliquid_order(
        self,
        symbol: str,
        is_buy: bool,
        size: Decimal,
        order_type: str,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        reduce_only: bool = False,
        tif: str = "GTC",
    ) -> dict[str, Any]:
        """Route to the correct Hyperliquid order method."""
        if order_type == "market":
            return await self.hl.place_market_order(
                coin=symbol, is_buy=is_buy, size=size, reduce_only=reduce_only,
            )
        elif order_type == "limit":
            if price is None:
                raise ValueError("Limit order requires a price")
            return await self.hl.place_limit_order(
                coin=symbol, is_buy=is_buy, size=size, price=price,
                reduce_only=reduce_only, tif=tif,
            )
        elif order_type in ("stop", "stop_market"):
            if stop_price is None:
                raise ValueError("Stop order requires a stop_price")
            return await self.hl.place_stop_order(
                coin=symbol, is_buy=is_buy, size=size,
                trigger_price=stop_price, reduce_only=reduce_only,
            )
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

    async def _place_solana_order(
        self,
        symbol: str,
        is_buy: bool,
        size: Decimal,
        price: Decimal | None = None,
    ) -> dict[str, Any]:
        """Place a Solana swap order via Jupiter aggregator."""
        from app.executors.solana import SOL_MINT, USDC_MINT

        # Determine input/output mints based on side
        if is_buy:
            # Buying symbol with SOL
            input_mint = SOL_MINT
            output_mint = self._symbol_to_mint(symbol)
        else:
            # Selling symbol for SOL
            input_mint = self._symbol_to_mint(symbol)
            output_mint = SOL_MINT

        # Get quote
        # Convert to lamport-like amount (multiply by token decimals as needed)
        amount = int(float(size) * 1_000_000)  # default 6 decimals
        quote = await self.sol.get_token_price(input_mint, output_mint, amount)

        return await self.sol.swap(quote)

    def _symbol_to_mint(self, symbol: str) -> str:
        """Convert a token symbol to its mint address."""
        mints = {
            "SOL": "So11111111111111111111111111111111111111112",
            "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        }
        return mints.get(symbol.upper(), symbol)

    async def cancel_order(
        self,
        session: AsyncSession,
        client_order_id: str,
    ) -> dict[str, Any]:
        """Cancel an order and update its status."""
        stmt = select(OrderRecord).where(
            OrderRecord.client_order_id == client_order_id,
        )
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError(f"Order not found: {client_order_id}")
        if order.status not in ("pending", "submitted"):
            raise ValueError(f"Cannot cancel order in state: {order.status}")

        try:
            if order.chain == "hyperliquid":
                # Need external_order_id and coin for Hyperliquid cancel
                oid = int(order.external_order_id) if order.external_order_id else 0
                resp = await self.hl.cancel_order(order.symbol, oid)
                order.status = "cancelled"
            else:
                raise ValueError(f"Cancel not supported for chain: {order.chain}")

            await session.commit()
            return resp

        except Exception as e:
            order.error_message = str(e)
            await session.commit()
            raise

    async def get_order(
        self,
        session: AsyncSession,
        client_order_id: str,
    ) -> OrderRecord | None:
        """Get a specific order."""
        stmt = select(OrderRecord).where(
            OrderRecord.client_order_id == client_order_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_orders(
        self,
        session: AsyncSession,
        wallet_address: str,
        chain: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get orders for a wallet with optional filters."""
        stmt = select(OrderRecord).where(
            OrderRecord.wallet_address == wallet_address,
        )
        if chain:
            stmt = stmt.where(OrderRecord.chain == chain)
        if status:
            stmt = stmt.where(OrderRecord.status == status)
        stmt = stmt.order_by(OrderRecord.submitted_at.desc())

        result = await session.execute(stmt)
        orders = result.scalars().all()
        return [
            {
                "client_order_id": o.client_order_id,
                "chain": o.chain,
                "symbol": o.symbol,
                "side": o.side,
                "order_type": o.order_type,
                "status": o.status,
                "quantity": o.quantity,
                "price": o.price,
                "fill_price": o.fill_price,
                "create_at": o.submitted_at.isoformat() if o.submitted_at else None,
                "update_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in orders
        ]

    async def update_position(
        self,
        session: AsyncSession,
        wallet_address: str,
        chain: str,
        symbol: str,
        side: str,
        size: Decimal,
    ) -> None:
        """Update position tracking after order fill."""
        stmt = select(PositionRecord).where(
            PositionRecord.wallet_address == wallet_address,
            PositionRecord.chain == chain,
            PositionRecord.symbol == symbol,
            PositionRecord.is_open == True,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing position
            existing.size = str(size)
        else:
            # Create new position
            new_pos = PositionRecord(
                wallet_address=wallet_address,
                chain=chain,
                symbol=symbol,
                side=side,
                size=str(size),
                entry_price="0",  # Will be updated when fill data is available
                is_open=True,
            )
            session.add(new_pos)

    async def get_positions(
        self,
        session: AsyncSession,
        wallet_address: str,
        chain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get current positions for a wallet."""
        stmt = select(PositionRecord).where(
            PositionRecord.wallet_address == wallet_address,
            PositionRecord.is_open == True,
        )
        if chain:
            stmt = stmt.where(PositionRecord.chain == chain)

        result = await session.execute(stmt)
        positions = result.scalars().all()
        return [
            {
                "symbol": p.symbol,
                "side": p.side,
                "size": p.size,
                "entry_price": p.entry_price,
                "unrealized_pnl": p.unrealized_pnl,
                "leverage": p.leverage,
                "margin": p.margin,
                "liquidation_price": p.liquidation_price,
            }
            for p in positions
        ]
