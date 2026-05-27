"""SQLAlchemy database setup for simulation-service."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


def _ensure_sqlite_dir(db_url: str) -> None:
    if not db_url.startswith("sqlite"):
        return
    try:
        url = make_url(db_url)
        if not url.database:
            return
        db_path = Path(url.database)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Ensured SQLite parent directory: %s", db_path.parent)
    except Exception as e:
        logger.error("Failed to ensure SQLite directory: %s", e)
        raise


def _is_production() -> bool:
    return not settings.database_url.startswith("sqlite")


_ensure_sqlite_dir(settings.database_url)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Initialize database connection and tables."""
    _ensure_sqlite_dir(settings.database_url)

    # Import models so Base knows about them
    from app import models  # noqa: F401

    if _is_production():
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified (production)")
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created (development)")
