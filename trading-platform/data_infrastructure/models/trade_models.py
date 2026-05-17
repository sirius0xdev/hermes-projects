"""Trade data models — orders, positions, and related trade entities.

These models define the PostgreSQL schema for the order management
and position tracking subsystems.

Covers deliverables:
- Orders (new, amend, cancel, status transitions)
- Fills / executions
- Positions (open/closed, leverage, margin)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String, Numeric, DateTime, Integer, Boolean, Text,
    func, Index, ForeignKey, CheckConstraint, Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

import enum

from data_infrastructure.models import Base


# ── Enums ──────────────────────────────────────────────────────────

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
    GTC = "gtc"       # Good-til-canceled
    IOC = "ioc"       # Immediate-or-cancel
    FOK = "fok"       # Fill-or-kill
    GTD = "gtd"       # Good-til-date


class PositionSide(enum.Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


# ── Orders ─────────────────────────────────────────────────────────

class Order(Base):
    """Customer order — the full lifecycle from submission to terminal state.

    An order starts as PENDING, moves through SUBMITTED -> (PARTIALLY_FILLED)*
    -> FILLED/CANCELLED/REJECTED/EXPIRED.
    """
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_wallet_status", "wallet_address", "status"),
        Index("ix_orders_symbol_status", "symbol", "status"),
        Index("ix_orders_external_order_id", "external_order_id"),
        Index("ix_orders_created_at_desc", "created_at", postgresql_ops={"created_at": "DESC"}),
        # Partial index: only open orders for fast lookup
        Index(
            "ix_orders_open",
            "wallet_address", "symbol",
            postgresql_where="status IN ('pending', 'submitted', 'partially_filled')",
        ),
        CheckConstraint("quantity > 0", name="chk_order_qty_positive"),
        CheckConstraint(
            "(order_type = 'market' OR price IS NOT NULL)",
            name="chk_limit_order_has_price",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    client_order_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True,
    )

    # Owner
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))  # hyperliquid, solana, etc.

    # Instrument
    symbol: Mapped[str] = mapped_column(String(32), index=True)

    # Order parameters
    side: Mapped[OrderSide] = mapped_column(
        SQLEnum(OrderSide, name="order_side"),
    )
    order_type: Mapped[OrderType] = mapped_column(
        SQLEnum(OrderType, name="order_type"),
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )  # limit price
    stop_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    time_in_force: Mapped[TimeInForce] = mapped_column(
        SQLEnum(TimeInForce, name="tif"),
        default=TimeInForce.GTC,
    )

    # Leverage (for perps/margin)
    leverage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True, default=1,
    )

    # State
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, name="order_status"),
        default=OrderStatus.PENDING,
        index=True,
    )

    # Fill tracking
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(32, 18), default=0,
    )
    avg_fill_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    remaining_quantity: Mapped[Decimal] = mapped_column(
        Numeric(32, 18),
    )  # computed = quantity - filled_quantity

    # External exchange refs
    external_order_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    external_exchange: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
    )  # binance, hyperliquid, etc.

    # Error tracking
    reject_reason: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True,
    )

    # Metadata
    metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True,
    )

    # Timestamps
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    filled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    fills: Mapped[list["Fill"]] = relationship(
        "Fill", back_populates="order", order_by="Fill.filled_at",
    )


# ── Fills ──────────────────────────────────────────────────────────

class Fill(Base):
    """Execution / fill record — each time a portion of an order is matched.

    A single order may have many fills (partial fills).
    """
    __tablename__ = "fills"
    __table_args__ = (
        Index("ix_fills_order_id", "order_id"),
        Index("ix_fills_wallet_symbol_time", "wallet_address", "symbol", "filled_at"),
        Index("ix_fills_external_fill_id", "external_fill_id"),
        CheckConstraint("fill_quantity > 0", name="chk_fill_qty_positive"),
        CheckConstraint("fill_price > 0", name="chk_fill_price_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    # FK to order
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"),
    )
    client_order_id: Mapped[str] = mapped_column(String(64), index=True)

    # Owner (denormalized for fast queries)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))

    # Instrument
    symbol: Mapped[str] = mapped_column(String(32), index=True)

    # Fill details
    side: Mapped[OrderSide] = mapped_column(
        SQLEnum(OrderSide, name="fill_side"),
    )
    fill_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    fill_quantity: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    # Fee
    fee: Mapped[Decimal] = mapped_column(
        Numeric(32, 18), default=0,
    )
    fee_currency: Mapped[str] = mapped_column(String(8), default="USDC")
    is_maker: Mapped[bool] = mapped_column(Boolean, default=False)

    # External refs
    external_fill_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    external_order_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )

    # Metadata
    metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True,
    )

    filled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="fills")


# ── Positions ──────────────────────────────────────────────────────

class Position(Base):
    """Active or closed position — aggregated from fills.

    Each open position represents a net exposure for a
    (wallet, chain, symbol) combination. When the position
    is fully closed, a new historical record is created and
    the active row is removed or marked closed.
    """
    __tablename__ = "positions"
    __table_args__ = (
        # Unique constraint: one open position per (wallet, chain, symbol)
        Index(
            "ix_positions_wallet_chain_symbol_open",
            "wallet_address", "chain", "symbol",
            unique=True,
            postgresql_where="is_open = true",
        ),
        Index("ix_positions_wallet", "wallet_address"),
        Index("ix_positions_symbol", "symbol"),
        Index("ix_positions_unrealized_pnl", "unrealized_pnl"),
        CheckConstraint(
            "(side = 'flat') OR (size > 0)",
            name="chk_position_size_positive_when_open",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Owner
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))

    # Instrument
    symbol: Mapped[str] = mapped_column(String(32), index=True)

    # Position state
    side: Mapped[PositionSide] = mapped_column(
        SQLEnum(PositionSide, name="position_side"),
    )
    size: Mapped[Decimal] = mapped_column(Numeric(32, 18))  # absolute quantity
    entry_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))  # avg entry
    current_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )  # mark / last price

    # PnL
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(32, 18), default=0,
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(32, 18), default=0,
    )
    total_fees: Mapped[Decimal] = mapped_column(
        Numeric(32, 18), default=0,
    )

    # Leverage / margin
    leverage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True,
    )
    margin: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    liquidation_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )

    # State
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # External refs
    external_exchange: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
    )

    # Metadata
    metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True,
    )

    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


# ── PositionHistory (closed positions) ─────────────────────────────

class PositionHistory(Base):
    """Historical record of closed positions — for PnL analysis and reporting.

    When a position closes (size goes to 0), a row is written here
    and the active position row is marked is_open=false.
    """
    __tablename__ = "position_history"
    __table_args__ = (
        Index("ix_poshist_wallet_chain", "wallet_address", "chain"),
        Index("ix_poshist_symbol", "symbol"),
        Index("ix_poshist_pnl", "realized_pnl"),
        Index("ix_poshist_opened_closed", "opened_at", "closed_at"),
        # GiST index for tsrange queries (position duration)
        Index(
            "ix_poshist_duration",
            "opened_at", "closed_at",
            postgresql_using="gist",
            postgresql_ops={"opened_at": "tsrange_ops", "closed_at": "tsrange_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    position_id: Mapped[int] = mapped_column(
        Integer, index=True,
    )  # reference to original positions.id

    # Owner
    wallet_address: Mapped[str] = mapped_column(String(64))
    chain: Mapped[str] = mapped_column(String(16))

    # Instrument
    symbol: Mapped[str] = mapped_column(String(32))

    # Position summary
    side: Mapped[PositionSide] = mapped_column(
        SQLEnum(PositionSide, name="poshist_side"),
    )
    total_size: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    exit_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    # PnL
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    total_fees: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    return_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4), nullable=True,
    )

    # Leverage
    leverage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True,
    )

    # Duration
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Fill count
    fill_count: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata
    metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
