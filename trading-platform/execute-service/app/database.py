"""
SQLAlchemy database session setup.
Supports SQLite (dev) and PostgreSQL (prod) via async drivers.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.engine.url import make_url
from pathlib import Path
import logging

from app.config import settings

logger = logging.getLogger(__name__)


def _ensure_sqlite_dir(db_url: str) -> None:
    """Ensure the parent directory for a SQLite database file exists.

    Critical under K8s readOnlyRootFilesystem + emptyDir mounts.
    Called early (at module import) to cover lazy connection cases.
    """
    if not db_url.startswith("sqlite"):
        return

    try:
        url = make_url(db_url)
        if not url.database:
            return

        db_path = Path(url.database)
        parent = db_path.parent

        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensured SQLite parent directory exists: {parent}")
    except Exception as e:
        logger.error(f"Failed to ensure SQLite directory for {db_url}: {e}")
        raise  # Re-raise so we get a clear error instead of a vague 'unable to open'


def _is_production() -> bool:
    """Return True when running against PostgreSQL (production)."""
    return not settings.database_url.startswith("sqlite")


# IMPORTANT: Ensure directory exists BEFORE creating the engine.
# This prevents "unable to open database file" when the first connection is attempted.
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
    """FastAPI dependency: provides a per-request async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            pass  # session auto-closes via context manager


async def init_db() -> None:
    """Initialize database connection and tables.

    In production (PostgreSQL): verify connectivity only — tables are created
    by Alembic migrations, not DDL at runtime.
    In development (SQLite): create all tables for convenience.
    """
    # Double-ensure (harmless if already done)
    _ensure_sqlite_dir(settings.database_url)

    # Import all models so Base knows about them
    from app import models  # noqa: F401

    if _is_production():
        # Production: verify connection, optionally create tables
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified (production)")

        if settings.db_auto_create_tables:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables auto-created (production)")
    else:
        # Development: create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created (development)")
