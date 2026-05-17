"""
SQLAlchemy database session setup.
Supports SQLite (dev) and PostgreSQL (prod) via async drivers.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

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


async def init_db():
    """Create all tables. Call on service startup."""
    # Import all models so Base knows about them
    from app import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
