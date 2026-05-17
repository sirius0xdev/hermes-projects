"""
Trade execution API endpoints for frontend consumption.
Handles order placement, cancellation, position queries, and account state.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.order_models import OrderRecord
from app.auth.service import decode_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trades", tags=["trade-execution"])


# --- Dependency: Extract wallet address from JWT ---
async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Extract wallet address from JWT in Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "wallet_address": payload["sub"],
        "chain": payload["chain"],
        "jti": payload["jti"],
    }


# --- Request/Response Schemas ---
class PlaceOrderRequest(BaseModel):
    chain: Literal["hyperliquid", "solana"]
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_market"]
    quantity: str  # decimal as string
    price: str | None = None
    stop_price: str | None = None
    reduce_only: bool = False
    time_in_force: Literal["GTC", "IOC", "FOK"] = "GTC"


class PlaceOrderResponse(BaseModel):
    client_order_id: str
    chain: str
    symbol: str
    side: str
    order_type: str
    status: str
    quantity: str
    price: str | None = None
    reduce_only: bool


class CancelOrderRequest(BaseModel):
    client_order_id: str


class OrderStatusResponse(BaseModel):
    client_order_id: str
    chain: str
    symbol: str
    side: str
    order_type: str
    status: str
    quantity: str
    price: str | None = None
    fill_price: str | None = None
    create_at: str | None = None


class PositionResponse(BaseModel):
    symbol: str
    side: str
    size: str
    entry_price: str
    unrealized_pnl: str | None = None
    leverage: str | None = None
    liquidation_price: str | None = None


class AccountStateResponse(BaseModel):
    total_equity: str | None = None
    margin_total: str | None = None
    positions: list[PositionResponse] = []


def _wallet(user: dict) -> str:
    return user["wallet_address"]


def _wallet_compat(user: dict) -> str:
    """Handle backwards compat for wallet address key."""
    return user.get("wallet_address", user.get("wallet_account", ""))


# --- Endpoints ---
@router.post("/place", response_model=PlaceOrderResponse)
async def place_order(
    req: PlaceOrderRequest,
    order_mgr: Annotated["OrderManager", Depends()],
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlaceOrderResponse:
    """Place a new trading order."""
    order = await order_mgr.place_order(
        session=session,
        wallet_address=user["wallet_address"],
        chain=req.chain,
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=Decimal(req.quantity),
        price=Decimal(req.price) if req.price else None,
        stop_price=Decimal(req.stop_price) if req.stop_price else None,
        reduce_only=req.reduce_only,
        time_in_force=req.time_in_force,
    )

    return PlaceOrderResponse(
        client_order_id=order.client_order_id,
        chain=order.chain,
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        status=order.status,
        quantity=order.quantity,
        price=order.price,
        reduce_only=order.reduce_only,
    )


@router.post("/cancel")
async def cancel_order(
    req: CancelOrderRequest,
    order_mgr: Annotated["OrderManager", Depends()],
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Cancel an existing order."""
    try:
        result = await order_mgr.cancel_order(
            session=session,
            client_order_id=req.client_order_id,
        )
        return {"status": "cancelled", "response": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders", response_model=list[OrderStatusResponse])
async def get_orders(
    user: Annotated[dict, Depends(get_current_user)],
    order_mgr: Annotated["OrderManager", Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
    chain: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[OrderStatusResponse]:
    """Get all orders for the current user."""
    orders = await order_mgr.get_orders(
        session=session,
        wallet_address=_wallet(user),
        chain=chain,
        status=status,
    )
    return [OrderStatusResponse(**o) for o in orders]


@router.get("/orders/{client_order_id}", response_model=OrderStatusResponse)
async def get_order(
    client_order_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    order_mgr: Annotated["OrderManager", Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderStatusResponse:
    """Get a specific order by ID."""
    order = await order_mgr.get_order(session, client_order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.wallet_address != user["wallet_address"]:
        raise HTTPException(status_code=403, detail="Not your order")

    return OrderStatusResponse(
        client_order_id=order.client_order_id,
        chain=order.chain,
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        status=order.status,
        quantity=order.quantity,
        price=order.price,
        fill_price=order.fill_price,
        create_at=order.submitted_at.isoformat() if order.submitted_at else None,
    )


@router.get("/positions", response_model=list[PositionResponse])
async def get_positions(
    user: Annotated[dict, Depends(get_current_user)],
    order_mgr: Annotated["OrderManager", Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
    chain: Annotated[str | None, Query()] = None,
) -> list[PositionResponse]:
    """Get current positions for the user."""
    positions = await order_mgr.get_positions(
        session=session,
        wallet_address=_wallet(user),
        chain=chain,
    )
    return [PositionResponse(**p) for p in positions]


@router.get("/account", response_model=AccountStateResponse)
async def get_account_state(
    user: Annotated[dict, Depends(get_current_user)],
    hl_exec: Annotated["HyperliquidExecutor", Depends()],
    sol_exec: Annotated["SolanaExecutor", Depends()],
    order_mgr: Annotated["OrderManager", Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccountStateResponse:
    """Get combined account state across chains."""
    positions = await order_mgr.get_positions(
        session=session,
        wallet_address=_wallet(user),
    )

    total_equity = None
    margin_total = None

    try:
        hl_state = await hl_exec.get_user_state()
        total_equity = hl_state.get("marginSummary", {}).get("totalMarginRequirement")
        margin_total = hl_state.get("marginSummary", {}).get("totalRawUsd")
    except Exception:
        pass

    # Add Solana balance
    try:
        sol_balance = await sol_exec.get_balance()
        margin_total = str(sol_balance) if margin_total is None else margin_total
    except Exception:
        pass

    return AccountStateResponse(
        total_equity=total_equity,
        margin_total=margin_total,
        positions=[PositionResponse(**p) for p in positions],
    )
