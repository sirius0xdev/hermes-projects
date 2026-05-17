"""Async SQLAlchemy engine and session management.

Configured with connection pooling optimized for PostgreSQL in both
local development and production Kubernetes deployments.

Supports:
- PostgreSQL (production) via asyncpg
- SQLite (local dev fallback) via aiosqlite
"""
from __future__ import annotations

from typing import AsyncGenerator, Optional
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import (
    NullPool,
    AsyncAdaptedQueuePool,
    StaticPool,
)

from data_service.app.db.base import Base


# ── Configuration defaults ───────────────────────────────────────

# Pool sizes tuned for typical FastAPI service:
#   - pool_size: simultaneous connections held open
#   - max_overflow: burst capacity beyond pool_size
#   - pool_timeout: seconds to wait for a connection from the pool
#   - pool_recycle: seconds before a connection is recycled (Postgres idle timeout handling)

DEFAULT_POOL_CONFIG = {
    "pool_size": 20,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 300,       # 5 min — below PG default idle timeout
    "pool_pre_ping": True,     # Test connection health before each use
}

# Minimal pool for SQLite dev (single process, no real pooling needed)
SQLITE_POOL_CONFIG = {
    "poolclass": StaticPool,
    "connect_args": {"check_same_thread": False},
}


class DatabaseConfig:
    """Async database engine and session factory.

    Usage:
        db = DatabaseConfig(settings.database_url)
        await db.init()

        # As a FastAPI dependency:
        async def get_session() -> AsyncGenerator[AsyncSession]:
            async with db.session_factory() as session:
                yield session
    """

    def __init__(
        self,
        url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading_db",
        echo: bool = False,
        pool_size: Optional[int] = None,
        max_overflow: Optional[int] = None,
        pool_timeout: Optional[int] = None,
        pool_recycle: Optional[int] = None,
        pool_pre_ping: Optional[bool] = None,
    ):
        self.url = url
        self.echo = echo
        self._pool_size = pool_size or DEFAULT_POOL_CONFIG["pool_size"]
        self._max_overflow = max_overflow or DEFAULT_POOL_CONFIG["max_overflow"]
        self._pool_timeout = pool_timeout or DEFAULT_POOL_CONFIG["pool_timeout"]
        self._pool_recycle = pool_recycle or DEFAULT_POOL_CONFIG["pool_recycle"]
        self._pool_pre_ping = pool_pre_ping if pool_pre_ping is not None else DEFAULT_POOL_CONFIG["pool_pre_ping"]
        self._engine = None
        self._session_factory = None

    async def init(self) -> None:
        """Create the async engine and session factory."""
        self._engine = self._create_engine()
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    def _create_engine(self):
        """Create engine with pool configuration based on the DB driver."""
        is_sqlite = self.url.startswith("sqlite")

        if is_sqlite:
            return create_async_engine(
                self.url, echo=self.echo, **SQLITE_POOL_CONFIG,
            )

        return create_async_engine(
            self.url,
            echo=self.echo,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=self._pool_size,
            max_overflow=self._max_overflow,
            pool_timeout=self._pool_timeout,
            pool_recycle=self._pool_recycle,
            pool_pre_ping=self._pool_pre_ping,
        )

    @property
    def engine(self):
        if self._engine is None:
            raise RuntimeError("Call init() first")
        return self._engine

    @property
    def session_factory(self):
        if self._session_factory is None:
            raise RuntimeError("Call init() first")
        return self._session_factory

    async def close(self) -> None:
        """Dispose the engine and release all pooled connections."""
        if self._engine:
            await self._engine.dispose()

    async def create_all(self) -> None:
        """Create all tables from registered models. Use in dev only."""
        if self._engine is None:
            raise RuntimeError("Call init() first")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Drop all tables. Use in dev/test only."""
        if self._engine is None:
            raise RuntimeError("Call init() first")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# ── FastAPI dependency ───────────────────────────────────────────

# Global instance — initialized at service startup
db_config: Optional[DatabaseConfig] = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — provides a per-request async DB session.

    Yields a session that is automatically committed on success or
    rolled back on exception.
    """
    if db_config is None or db_config.session_factory is None:
        raise RuntimeError("Database not initialized. Call db_config.init() at startup.")

    async with db_config.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
