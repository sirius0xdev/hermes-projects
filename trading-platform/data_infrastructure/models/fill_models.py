"""Fill/execution models — records each individual fill when an order is partially or fully executed."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import String, Numeric, DateTime, Enum as SAEnum, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

import uuid

from data_infrastructure.models import Base


class FillSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class FillRecord(Base):
    """Individual fill records — one order can have multiple fills."""
    __tablename__ = "fills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    order_id: Mapped[int] = mapped_column(
        Integer, index=True
    )  # FK to orders.id
    client_order_id: Mapped[str] = mapped_column(String(64), index=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))  # hyperliquid, solana

    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[FillSide] = mapped_column(SAEnum(FillSide))
    quantity: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    fill_price: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    # Fee charged by exchange
    fee: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    fee_currency: Mapped[Optional[str]] = mapped_column(
        String(8), nullable=True,
    )

    # Liquidity provision
    is_maker: Mapped[bool] = mapped_column(server_default="false")

    # Exchange metadata
    external_fill_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    trade_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    raw_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON from exchange

    filled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
