"""Data infrastructure SQLAlchemy models.

These models define the PostgreSQL schema for:
- Trade data (orders, fills, positions)
- PnL history and accounting
- Market data storage (candles, ticks)
"""
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase


def _get_base():
    """Return a shared Base. Falls back to a local DeclarativeBase if
    execute_service is not on the path (e.g. in isolated test or standalone use)."""
    try:
        from execute_service.app.database import Base as ExecBase
        return ExecBase
    except ImportError:
        pass
    try:
        from app.database import Base as AppBase
        return AppBase
    except ImportError:
        pass

    # Standalone fallback: create our own Base
    class _StandaloneBase(DeclarativeBase):
        pass
    return _StandaloneBase


Base = _get_base()
