"""Data infrastructure layer configuration.

Combines database, Redis, and Kafka settings for the trading platform.
Environment variables are prefixed with DATA_ to avoid conflicts.
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import field_validator


class DataInfrastructureSettings(BaseSettings):
    """Consolidated settings for the data infrastructure layer."""

    # Database
    database_url: str = "sqlite+aiosqlite:///./trading.db"

    # Redis
    redis_url: str = "redis://redis-master:6379/0"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # Logging
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if v.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
            return v
        raise ValueError("database_url must use asyncpg or aiosqlite dialect")

    model_config = {
        "env_prefix": "DATA_",
        "env_file": ".env",
        "extra": "ignore",
    }


settings = DataInfrastructureSettings()


def setup_logging(level: Optional[str] = None):
    """Configure logging for data infrastructure."""
    log_level = level or settings.log_level
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
