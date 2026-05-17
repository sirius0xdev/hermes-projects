"""SQLAlchemy models for trade data.

Defines the PostgreSQL schema for:
- orders table (order lifecycle)
- positions table (current/historical positions)
- fills table (trade history with fees)

These models are designed to work with both the Redis cache layer (T5b)
and Kafka event pipeline (T5c) — all timestamps are timezone-aware,
numeric fields use Decimal types, and IDs are UUIDs for distributed systems.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    Integer,
    Boolean,
    Text,
    func,
    Index,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from data_service.app.db.base import Base


# ── Order enums ───────────────────────────────────────────────────

class OrderSide(enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_MARKET = "stop_market"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(enum.Enum):
    GTC = "gtc"       # Good-til-cancelled
    IOC = "ioc"       # Immediate-or-cancel
    FOK = "fok"       # Fill-or-kill
    GTD = "gtd"       # Good-til-date


# ── Order model ───────────────────────────────────────────────────

class Order(Base):
    """Customer order — full lifecycle from submission to terminal state.

    Status transitions:
        PENDING -> SUBMITTED -> (PARTIALLY_FILLED)* -> FILLED
        PENDING/SUBMITTED -> CANCELLED / REJECTED / EXPIRED
    """
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_wallet_status", "wallet_address", "status"),
        Index("ix_orders_user_status", "user_id", "status"),
        Index("ix_orders_symbol_status", "symbol", "status"),
        Index("ix_orders_external_id", "external_order_id"),
        Index("ix_orders_created_desc", "created_at", postgresql_ops={"created_at": "DESC"}),
        # Partial index for fast open-order lookups
        Index(
            "ix_orders_open",
            "wallet_address", "symbol",
            postgresql_where="status IN ('pending', 'submitted', 'partially_filled')",
        ),
        CheckConstraint("quantity > 0", name="chk_order_qty_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    # user_id links to the auth/identity service; wallet_address is the on-chain address
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)

    chain: Mapped[str] = mapped_column(String(16))  # hyperliquid, solana, etc.
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[OrderSide] = mapped_column(SQLEnum(OrderSide))
    type: Mapped[OrderType] = mapped_column(SQLEnum(OrderType))

    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus), default=OrderStatus.PENDING,
    )

    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    external_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Execution details (populated on fill)
    filled_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    filled_quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    avg_fill_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)

    # Optional fields for advanced order types
    stop_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    time_in_force: Mapped[TimeInForce] = mapped_column(SQLEnum(TimeInForce), default=TimeInForce.GTC)

    # Audit
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, name="metadata")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    fills: Mapped[list["Fill"]] = relationship(
        "Fill", back_populates="order", cascade="all, delete-orphan",
    )


# ── Position model ────────────────────────────────────────────────

class Position(Base):
    """Current position for a wallet/symbol pair.

    One open position per (user_id, symbol) — closed positions are
    archived to the trade history or kept with is_open=False.
    """
    __tablename__ = "positions"
    __table_args__ = (
        Index("ix_positions_wallet_symbol", "wallet_address", "symbol"),
        Index("ix_positions_user_symbol", "user_id", "symbol"),
        Index("ix_positions_symbol_side", "symbol", "side"),
        UniqueConstraint("user_id", "symbol", "is_open", name="uq_position_user_symbol_open"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)

    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))       # long / short
    size: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    # Mark-to-market
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    realized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)

    # Margin / leverage
    leverage: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    liquidation_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)

    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)

    chain: Mapped[str] = mapped_column(String(16))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Fill (trade history) model ────────────────────────────────────

class Fill(Base):
    """Individual fill record — each execution of an order.

    One order can produce multiple fills (partial fills).
    This is the authoritative trade history / execution ledger.
    """
    __tablename__ = "fills"
    __table_args__ = (
        Index("ix_fills_order_id", "order_id"),
        Index("ix_fills_wallet_time", "wallet_address", "filled_at", postgresql_ops={"filled_at": "DESC"}),
        Index("ix_fills_user_time", "user_id", "filled_at", postgresql_ops={"filled_at": "DESC"}),
        Index("ix_fills_symbol_time", "symbol", "filled_at", postgresql_ops={"filled_at": "DESC"}),
        Index("ix_fills_external_id", "external_fill_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), index=True,
    )

    user_id: Mapped[str] = mapped_column(String(64), index=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))

    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))  # buy / sell
    quantity: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    fill_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    # Fee charged by the exchange for this fill
    fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(32, 18), nullable=True)
    fee_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    # Maker / taker liquidity provision
    is_maker: Mapped[bool] = mapped_column(Boolean, default=False)

    # Exchange identifiers
    external_fill_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    trade_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    raw_data: Mapped[Optional[str]] = mapped_column(JSONB, nullable=True)

    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="fills")
