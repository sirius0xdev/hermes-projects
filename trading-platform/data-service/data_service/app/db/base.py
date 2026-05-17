"""SQLAlchemy declarative base for the data service."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all data service models."""
    pass
