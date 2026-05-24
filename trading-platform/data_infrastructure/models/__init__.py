"""Data infrastructure SQLAlchemy models.

These models define the PostgreSQL schema for:
- Trade data (orders, fills, positions)
- PnL history and accounting
- Market data storage (candles, ticks)
- Whale alerts (large on-chain transactions)
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


def __getattr__(name: str):
    """Lazy-import whale models to avoid circular imports.

    Individual model modules import `Base` from this package, but importing
    those modules at module level would create a cycle since this __init__
    defines Base at runtime.  So we only load WhaleAlert when requested.
    """
    if name == "WhaleAlert":
        from data_infrastructure.models.whale_models import WhaleAlert
        return WhaleAlert
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
