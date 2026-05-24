"""Whale alert storage models — persistent storage for large on-chain transactions."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

import uuid

from data_infrastructure.models import Base


class WhaleAlert(Base):
    """Whale alert events — large on-chain transactions worth monitoring."""
    __tablename__ = "whale_alerts"
    __table_args__ = (
        Index("ix_wa_token_timestamp", "token_symbol", "timestamp"),
        Index("ix_wa_usd_value", "usd_value", postgresql_ops={"usd_value": "DESC"}),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    signature: Mapped[str] = mapped_column(String(88), unique=True)
    slot: Mapped[int] = mapped_column(Integer)

    amount: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    token_symbol: Mapped[str] = mapped_column(String(16))
    token_decimals: Mapped[int] = mapped_column(Integer)
    usd_value: Mapped[Decimal] = mapped_column(Numeric(32, 18))

    from_address: Mapped[str] = mapped_column(String(44))
    to_address: Mapped[str] = mapped_column(String(44))

    from_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tx_type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32), default="solana-whale")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
