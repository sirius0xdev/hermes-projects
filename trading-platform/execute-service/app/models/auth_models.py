"""Wallet auth SQLAlchemy models."""
from __future__ import annotations

from sqlalchemy import String, Text, DateTime, Boolean, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

from datetime import datetime


class AuthNonce(Base):
    """Single-use nonces for wallet sign-in: prevents replay attacks."""
    __tablename__ = "auth_nonces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(  # type: ignore
        DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(  # type: ignore
        DateTime(timezone=True),
        server_default=func.now(),  # type: ignore
    )


class WalletSession(Base):
    """Active JWT sessions with rotation support."""
    __tablename__ = "wallet_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(256))
    refresh_token_hash: Mapped[str] = mapped_column(String(64), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(  # type: ignore
        DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(  # type: ignore
        DateTime(timezone=True),
        server_default=func.now(),  # type: ignore
    )
