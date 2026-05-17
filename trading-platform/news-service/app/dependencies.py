async def get_db():
    """Deprecated: use the dependency from app.core.database directly."""
    from app.core.database import db
    async for session in db.get_session():
        yield session
