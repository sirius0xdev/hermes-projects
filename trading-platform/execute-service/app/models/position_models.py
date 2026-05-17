"""Position tracking SQLAlchemy models."""
from __future__ import annotations

from sqlalchemy import String, Integer, DateTime, func, Boolean, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

from datetime import datetime


class PositionRecord(Base):
    """Current and historical positions."""
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))
    symbol: Mapped[str] = mapped_column(String(32))
    
    # Position state
    side: Mapped[str] = mapped_column(String(4))  # long / short
    size: Mapped[str] = mapped_column(String(32))  # decimal string
    entry_price: Mapped[str] = mapped_column(String(32))
    unrealized_pnl: Mapped[str | None] = mapped_column(String(32), nullable=True)
    leverage: Mapped[str | None] = mapped_column(String(8), nullable=True)
    margin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    liquidation_price: Mapped[str | None] = mapped_column(String(32), nullable=True)

    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    realized_pnl: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # External IDs for reconciliation
    external_position_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(  # type: ignore
        DateTime(timezone=True),
        server_default=func.now(),  # type: ignore
    )
    updated_at: Mapped[datetime] = mapped_column(  # type: ignore
        DateTime(timezone=True),
        server_default=func.now(),  # type: ignore
        onupdate=func.now(),  # type: ignore
    )
