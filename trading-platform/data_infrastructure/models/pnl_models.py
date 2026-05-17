"""PnL history models — tracks realized and unrealized PnL over time."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, DateTime, Integer, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

import uuid

from data_infrastructure.models import Base


class PnLRecord(Base):
    """PnL snapshot per wallet per symbol — recorded on fill close and periodically."""
    __tablename__ = "pnl_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))
    symbol: Mapped[str] = mapped_column(String(32))

    # Position identifiers
    position_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )  # FK to positions.id

    # PnL values
    realized_pnl: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    open_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    close_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )
    fees_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )

    # Currency of PnL
    currency: Mapped[str] = mapped_column(String(8), default="USDC")

    # Snapshot type — "realized" on close, "mark" for periodic mark-to-market
    pnl_type: Mapped[str] = mapped_column(
        String(16), default="realized"
    )  # realized, mark

    # Market price at snapshot time
    mark_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(32, 18), nullable=True,
    )

    # Exchange identifiers
    external_fill_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    # Extra data
    event_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON, nullable=True,
    )

    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
