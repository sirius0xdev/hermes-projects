"""Market data storage models — persistent storage for ticks, candles, and orderbook snapshots."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, DateTime, Index, Integer, Text, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

import uuid

from data_infrastructure.models import Base


class CandleRecord(Base):
    """OHLCV candle data — stored for backtesting and replay."""
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "open_time"),
        Index("ix_candles_symbol_interval_time", "symbol", "interval", "open_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(32))
    interval: Mapped[str] = mapped_column(String(8))  # 1m, 5m, 15m, 1h, 4h, 1d

    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    open_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    high_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    low_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    close_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    volume: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    quote_volume: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    trade_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Source tracking
    source: Mapped[str] = mapped_column(String(32), default="aggregated")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


class OrderBookSnapshot(Base):
    """Orderbook snapshots — full L2 state at intervals."""
    __tablename__ = "orderbook_snapshots"
    __table_args__ = (
        Index("ix_ob_symbol_time", "symbol", "snapshot_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    # Full orderbook as JSONB (bids/asks with price+qty)
    bids: Mapped[dict] = mapped_column(JSONB)  # [[price, qty], ...]
    asks: Mapped[dict] = mapped_column(JSONB)

    source: Mapped[str] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


class TradeRecord(Base):
    """Executed market trades — the raw trade feed."""
    __tablename__ = "market_trades"
    __table_args__ = (
        Index("ix_mt_symbol_time", "symbol", "trade_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    trade_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    price: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    quantity: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    side: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    is_buyer_maker: Mapped[Optional[bool]] = mapped_column(nullable=True)

    trade_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    source: Mapped[str] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
