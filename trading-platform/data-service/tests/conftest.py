"""Fixtures for data service tests."""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from data_service.app.db.base import Base  # noqa: F401


# In-memory SQLite for testing (no real Postgres needed)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine():
    """Create an async SQLite engine for tests."""
    eng = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create schema and provide a test session per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sample_order_data():
    """Standard fixture for creating test orders."""
    return {
        "user_id": "user_test_001",
        "wallet_address": "0x1234567890abcdef",
        "chain": "hyperliquid",
        "symbol": "BTC-PERP",
        "side": "buy",
        "type": "limit",
        "price": 50000.00,
        "quantity": 0.5,
        "status": "pending",
        "client_order_id": f"test_order_{uuid4()}",
    }


@pytest.fixture
def sample_position_data():
    """Standard fixture for creating test positions."""
    return {
        "user_id": "user_test_001",
        "wallet_address": "0x1234567890abcdef",
        "symbol": "BTC-PERP",
        "side": "long",
        "size": 0.5,
        "entry_price": 50000.00,
        "chain": "hyperliquid",
    }


@pytest.fixture
def sample_fill_data():
    """Standard fixture for creating test fills."""
    return {
        "user_id": "user_test_001",
        "wallet_address": "0x1234567890abcdef",
        "chain": "hyperliquid",
        "symbol": "BTC-PERP",
        "side": "buy",
        "quantity": 0.5,
        "fill_price": 50000.00,
    }
