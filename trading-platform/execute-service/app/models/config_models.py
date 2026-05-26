"""Service configuration stored in DB — API keys set via dashboard settings page."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import String, DateTime, Text, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServiceConfig(Base):
    """Key-value configuration store for runtime settings."""
    __tablename__ = "service_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )