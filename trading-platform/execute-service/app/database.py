"""
SQLAlchemy database session setup.
Supports SQLite (dev) and PostgreSQL (prod) via async drivers.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from pathlib import Path
import logging

from app.config import settings

logger = logging.getLogger(__name__)

def _ensure_sqlite_dir(db_url: str) -> None:
    """Ensure the parent directory for a SQLite database file exists.
    Critical for containers with readOnlyRootFilesystem + emptyDir mounts.
    """
    if not db_url.startswith("sqlite"):
        return
    try:
        # Parse path from URL e.g. sqlite+aiosqlite:////tmp/execute.db -> /tmp/execute.db
        # or sqlite+aiosqlite:///relative.db -> relative.db
        rest = db_url.split("://", 1)[1]
        if rest.startswith("//"):
            db_path_str = "/" + rest[2:].lstrip("/")
        else:
            db_path_str = rest
        db_path = Path(db_path_str)
        if db_path.parent and str(db_path.parent) not in (".", ""):
            db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured SQLite directory: {db_path.parent}")
    except Exception as e:
        logger.warning(f"Could not ensure SQLite dir for {db_url}: {e}")


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
    _ensure_sqlite_dir(settings.database_url)
    # Import all models so Base knows about them
    from app import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
