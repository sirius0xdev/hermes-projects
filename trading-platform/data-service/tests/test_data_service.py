"""Tests for data service: models, DB config, Alembic migrations."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from data_service.app.db.base import Base


# ── Model schema tests ─────────────────────────────────────────────

class TestModelSchema:
    """Verify that all expected tables and columns exist."""

    async def test_orders_table_exists(self, db_session: AsyncSession):
        cols = await db_session.run_sync(
            lambda sync: [c["name"] for c in inspect(sync).get_columns("orders")]
        )
        expected = [
            "id", "user_id", "wallet_address", "chain", "symbol",
            "side", "type", "price", "quantity", "status",
            "client_order_id", "external_order_id",
            "filled_price", "filled_quantity", "avg_fill_price", "fee",
            "stop_price", "reduce_only", "time_in_force",
            "error_message", "metadata",
            "created_at", "updated_at", "filled_at",
        ]
        for col in expected:
            assert col in cols, f"Missing column {col} in orders table"

    async def test_positions_table_exists(self, db_session: AsyncSession):
        cols = await db_session.run_sync(
            lambda sync: [c["name"] for c in inspect(sync).get_columns("positions")]
        )
        expected = [
            "id", "user_id", "wallet_address", "symbol", "side", "size",
            "entry_price", "current_price", "unrealized_pnl", "realized_pnl",
            "leverage", "margin", "liquidation_price", "is_open", "pnl",
            "chain", "created_at", "updated_at", "closed_at",
        ]
        for col in expected:
            assert col in cols, f"Missing column {col} in positions table"

    async def test_fills_table_exists(self, db_session: AsyncSession):
        cols = await db_session.run_sync(
            lambda sync: [c["name"] for c in inspect(sync).get_columns("fills")]
        )
        expected = [
            "id", "order_id", "user_id", "wallet_address", "chain", "symbol",
            "side", "quantity", "fill_price", "fee", "fee_currency",
            "is_maker", "external_fill_id", "trade_id", "raw_data",
            "filled_at", "created_at",
        ]
        for col in expected:
            assert col in cols, f"Missing column {col} in fills table"

    async def test_all_tables_listed(self, db_session: AsyncSession):
        tables = await db_session.run_sync(
            lambda sync: inspect(sync).get_table_names()
        )
        assert set(tables) >= {"orders", "positions", "fills"}


# ── CRUD tests ──────────────────────────────────────────────────────

class TestOrderCRUD:
    """Test insert, query, and lifecycle of orders."""

    async def test_create_order(self, db_session: AsyncSession, sample_order_data):
        from data_service.app.models import Order, OrderSide, OrderType, OrderStatus

        order = Order(**sample_order_data)
        db_session.add(order)
        await db_session.flush()

        assert order.id is not None
        assert order.status == OrderStatus.PENDING
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.LIMIT

    async def test_order_lifecycle(self, db_session: AsyncSession, sample_order_data):
        from data_service.app.models import Order, OrderStatus

        order = Order(**sample_order_data)
        db_session.add(order)
        await db_session.commit()

        # Transition through states
        order.status = OrderStatus.SUBMITTED
        await db_session.commit()

        from sqlalchemy import select
        result = await db_session.execute(
            select(Order).where(Order.id == order.id)
        )
        updated = result.scalar_one()
        assert updated.status == OrderStatus.SUBMITTED


class TestPositionCRUD:
    """Test position creation and queries."""

    async def test_create_position(self, db_session: AsyncSession, sample_position_data):
        from data_service.app.models import Position

        position = Position(**sample_position_data)
        db_session.add(position)
        await db_session.flush()

        assert position.id is not None
        assert position.is_open is True
        assert Decimal(str(position.size)) > 0


class TestFillCRUD:
    """Test fill records and order relationships."""

    async def _create_order(self, db_session: AsyncSession, sample_order_data):
        from data_service.app.models import Order

        order = Order(**sample_order_data)
        db_session.add(order)
        await db_session.flush()
        await db_session.refresh(order)
        return order

    async def test_create_fill(self, db_session: AsyncSession, sample_order_data, sample_fill_data):
        from data_service.app.models import Fill

        order = await self._create_order(db_session, sample_order_data)

        fill = Fill(order_id=order.id, **sample_fill_data)
        db_session.add(fill)
        await db_session.flush()

        assert fill.id is not None

    async def test_fill_order_relationship(self, db_session: AsyncSession, sample_order_data, sample_fill_data):
        from data_service.app.models import Fill
        from sqlalchemy import select
        from data_service.app.models import Order

        order = await self._create_order(db_session, sample_order_data)
        fill = Fill(order_id=order.id, **sample_fill_data)
        db_session.add(fill)
        await db_session.commit()

        # Verify relationship loading
        result = await db_session.execute(select(Order).where(Order.id == order.id))
        loaded_order = result.scalar_one()
        assert len(loaded_order.fills) == 1
        assert loaded_order.fills[0].fill_price == Decimal("50000")


# ── Database config unit tests ──────────────────────────────────────

class TestDatabaseConfig:
    """Test connection pool configuration."""

    def test_defaults(self):
        from data_service.app.db import DatabaseConfig
        db = DatabaseConfig()
        assert db.url == "postgresql+asyncpg://trading:trading@localhost:5432/trading_db"
        assert not db.echo
        assert db._pool_size == 20
        assert db._max_overflow == 10

    def test_sqlite_dev_config(self):
        from data_service.app.db import SQLITE_POOL_CONFIG
        assert "poolclass" in SQLITE_POOL_CONFIG
        assert "connect_args" in SQLITE_POOL_CONFIG

    def test_custom_pool_settings(self):
        from data_service.app.db import DatabaseConfig
        db = DatabaseConfig(pool_size=50, max_overflow=20, pool_timeout=10)
        assert db._pool_size == 50
        assert db._max_overflow == 20
        assert db._pool_timeout == 10


# ── Alembic migration validation ───────────────────────────────────

class TestAlembicMigration:
    """Validate the migration file can be parsed and has correct metadata."""

    def test_migration_file_parsable(self):
        import importlib.util
        import pathlib

        migration_path = pathlib.Path(__file__).parent.parent / "alembic" / "versions" / "001_initial_schema.py"
        assert migration_path.exists()

        spec = importlib.util.spec_from_file_location("migration", str(migration_path))
        assert spec is not None
        # We can't load it without alembic/sqlalchemy installed, but we
        # verify it's valid Python by compiling:
        with open(migration_path) as f:
            compile(f.read(), str(migration_path), "exec")

    def test_migration_has_required_functions(self):
        import pathlib
        migration_path = pathlib.Path(__file__).parent.parent / "alembic" / "versions" / "001_initial_schema.py"
        content = migration_path.read_text()
        assert "def upgrade()" in content
        assert "def downgrade()" in content
        assert 'revision: str' in content
        assert 'down_revision' in content
