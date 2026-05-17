"""Order management SQLAlchemy models."""
from __future__ import annotations

from sqlalchemy import String, Numeric, DateTime, Enum, Integer, Text, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

from datetime import datetime


class OrderRecord(Base):
    """Records all orders placed through the execution service."""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))  # hyperliquid, solana

    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))  # buy / sell
    order_type: Mapped[str] = mapped_column(String(16))  # market, limit, stop, stop_market
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending, submitted, filled, cancelled, expired, rejected
    quantity: Mapped[str] = mapped_column(String(32))  # stored as decimal string
    price: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stop_price: Mapped[str | None] = mapped_column(String(32), nullable=True)

    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    time_in_force: Mapped[str] = mapped_column(String(4), default="GTC")

    external_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fill_price: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fill_quantity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fee: Mapped[str | None] = mapped_column(String(32), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(  # type: ignore
        DateTime(timezone=True),
        server_default=func.now(),  # type: ignore
    )
    updated_at: Mapped[datetime] = mapped_column(  # type: ignore
        DateTime(timezone=True),
        server_default=func.now(),  # type: ignore
        onupdate=func.now(),  # type: ignore
    )
