"""Initial schema — orders, positions, fills (trade history).

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-05-17 07:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Enum types ────────────────────────────────────────────────────

order_side = postgresql.ENUM(
    'buy', 'sell',
    name='orderside',
    create_type=True,
)

order_type = postgresql.ENUM(
    'market', 'limit', 'stop', 'stop_market', 'trailing_stop',
    name='ordertype',
    create_type=True,
)

order_status = postgresql.ENUM(
    'pending', 'submitted', 'partially_filled', 'filled',
    'cancelled', 'rejected', 'expired',
    name='orderstatus',
    create_type=True,
)

time_in_force = postgresql.ENUM(
    'gtc', 'ioc', 'fok', 'gtd',
    name='timeinforce',
    create_type=True,
)


def upgrade() -> None:
    # ── Create enum types ──────────────────────────────────────────

    order_side.create(op.get_bind(), checkfirst=True)
    order_type.create(op.get_bind(), checkfirst=True)
    order_status.create(op.get_bind(), checkfirst=True)
    time_in_force.create(op.get_bind(), checkfirst=True)

    # ── Orders table ───────────────────────────────────────────────

    op.create_table(
        'orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(64), nullable=False, index=True),
        sa.Column('wallet_address', sa.String(64), nullable=False, index=True),
        sa.Column('chain', sa.String(16), nullable=False),
        sa.Column('symbol', sa.String(32), nullable=False),
        sa.Column('side', order_side, nullable=False),
        sa.Column('type', order_type, nullable=False),
        sa.Column('price', sa.Numeric(32, 18), nullable=True),
        sa.Column('quantity', sa.Numeric(32, 18), nullable=False),
        sa.Column('status', order_status, nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column('client_order_id', sa.String(64), nullable=False,
                  unique=True, index=True),
        sa.Column('external_order_id', sa.String(128), nullable=True, index=True),
        sa.Column('filled_price', sa.Numeric(32, 18), nullable=True),
        sa.Column('filled_quantity', sa.Numeric(32, 18), nullable=True),
        sa.Column('avg_fill_price', sa.Numeric(32, 18), nullable=True),
        sa.Column('fee', sa.Numeric(32, 18), nullable=True),
        sa.Column('stop_price', sa.Numeric(32, 18), nullable=True),
        sa.Column('reduce_only', sa.Boolean, nullable=False,
                  server_default=sa.text('false')),
        sa.Column('time_in_force', time_in_force, nullable=False,
                  server_default=sa.text("'gtc'")),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('quantity > 0', name='chk_order_qty_positive'),
    )

    # Indexes for orders
    op.create_index('ix_orders_wallet_status', 'orders', ['wallet_address', 'status'])
    op.create_index('ix_orders_user_status', 'orders', ['user_id', 'status'])
    op.create_index('ix_orders_symbol_status', 'orders', ['symbol', 'status'])
    op.create_index('ix_orders_created_desc', 'orders', ['created_at'],
                    postgresql_ops={'created_at': 'DESC'})

    # ── Positions table ────────────────────────────────────────────

    op.create_table(
        'positions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(64), nullable=False, index=True),
        sa.Column('wallet_address', sa.String(64), nullable=False, index=True),
        sa.Column('symbol', sa.String(32), nullable=False),
        sa.Column('side', sa.String(4), nullable=False),
        sa.Column('size', sa.Numeric(32, 18), nullable=False),
        sa.Column('entry_price', sa.Numeric(32, 18), nullable=False),
        sa.Column('current_price', sa.Numeric(32, 18), nullable=True),
        sa.Column('unrealized_pnl', sa.Numeric(32, 18), nullable=True),
        sa.Column('realized_pnl', sa.Numeric(32, 18), nullable=True),
        sa.Column('leverage', sa.String(8), nullable=True),
        sa.Column('margin', sa.Numeric(32, 18), nullable=True),
        sa.Column('liquidation_price', sa.Numeric(32, 18), nullable=True),
        sa.Column('is_open', sa.Boolean, nullable=False,
                  server_default=sa.text('true'), index=True),
        sa.Column('pnl', sa.Numeric(32, 18), nullable=True),
        sa.Column('chain', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for positions
    op.create_index('ix_positions_wallet_symbol', 'positions', ['wallet_address', 'symbol'])
    op.create_index('ix_positions_user_symbol', 'positions', ['user_id', 'symbol'])
    op.create_index('ix_positions_symbol_side', 'positions', ['symbol', 'side'])
    op.create_unique_constraint(
        'uq_position_user_symbol_open', 'positions',
        ['user_id', 'symbol', 'is_open'],
    )

    # ── Fills table (trade history) ────────────────────────────────

    op.create_table(
        'fills',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('order_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(64), nullable=False, index=True),
        sa.Column('wallet_address', sa.String(64), nullable=False, index=True),
        sa.Column('chain', sa.String(16), nullable=False),
        sa.Column('symbol', sa.String(32), nullable=False),
        sa.Column('side', sa.String(4), nullable=False),
        sa.Column('quantity', sa.Numeric(32, 18), nullable=False),
        sa.Column('fill_price', sa.Numeric(32, 18), nullable=False),
        sa.Column('fee', sa.Numeric(32, 18), nullable=True),
        sa.Column('fee_currency', sa.String(8), nullable=True),
        sa.Column('is_maker', sa.Boolean, nullable=False,
                  server_default=sa.text('false')),
        sa.Column('external_fill_id', sa.String(128), nullable=True, index=True),
        sa.Column('trade_id', sa.String(128), nullable=True),
        sa.Column('raw_data', postgresql.JSONB, nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("TIMEZONE('utc', now())")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # Indexes for fills
    op.create_index('ix_fills_wallet_time', 'fills', ['wallet_address', 'filled_at'],
                    postgresql_ops={'filled_at': 'DESC'})
    op.create_index('ix_fills_user_time', 'fills', ['user_id', 'filled_at'],
                    postgresql_ops={'filled_at': 'DESC'})
    op.create_index('ix_fills_symbol_time', 'fills', ['symbol', 'filled_at'],
                    postgresql_ops={'filled_at': 'DESC'})


def downgrade() -> None:
    op.drop_table('fills')
    op.drop_table('positions')
    op.drop_table('orders')

    # Drop enum types
    time_in_force.drop(op.get_bind(), checkfirst=True)
    order_status.drop(op.get_bind(), checkfirst=True)
    order_type.drop(op.get_bind(), checkfirst=True)
    order_side.drop(op.get_bind(), checkfirst=True)
