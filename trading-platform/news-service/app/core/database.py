"""Database session manager."""

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import get_settings


def create_engine():
    """Create async SQLAlchemy engine from settings."""
    settings = get_settings()
    return create_async_engine(
        settings.db_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections every hour
    )


def create_news_engine():
    """Create async SQLAlchemy engine for the secondary news_app_db (scraper data)."""
    settings = get_settings()
    return create_async_engine(
        settings.news_db_url,
        pool_size=settings.news_db_pool_size,
        max_overflow=settings.news_db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


class DatabaseSession:
    """Global database session manager."""
    
    def __init__(self):
        self._engine = None
        self._session_factory = None

    async def init(self):
        """Initialize engine and session factory."""
        self._engine = create_engine()
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def close(self):
        """Dispose of the engine."""
        if self._engine:
            await self._engine.dispose()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an async session."""
        async with self._session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    @property
    def engine(self):
        return self._engine


# Primary DB singleton (trading_data)
db = DatabaseSession()


class NewsDatabaseSession:
    """Secondary database session manager for news_app_db (scraper data — read-only)."""

    def __init__(self):
        self._engine = None
        self._session_factory = None

    async def init(self):
        """Initialize engine and session factory."""
        self._engine = create_news_engine()
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def close(self):
        """Dispose of the engine."""
        if self._engine:
            await self._engine.dispose()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an async session for the secondary DB."""
        async with self._session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    @property
    def engine(self):
        return self._engine


# Secondary DB singleton (news_app_db)
news_db = NewsDatabaseSession()
