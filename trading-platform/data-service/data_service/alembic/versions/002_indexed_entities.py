"""Add indexed_entities table for embedding index tracking.

Revision ID: 002_indexed_entities
Revises: 001_initial_schema
Create Date: 2026-05-27 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by alembic.
revision: str = '002_indexed_entities'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'indexed_entities',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('entity_type', sa.String(32), nullable=False),
        sa.Column('entity_id', sa.String(128), nullable=False),
        sa.Column('context_text', sa.Text, nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('indexed', sa.Boolean, nullable=False,
                  server_default=sa.text('true'), index=True),
        sa.Column('vector_key', sa.String(128), nullable=True),
        sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # Unique constraint on (entity_type, entity_id)
    op.create_index(
        'ix_indexed_entities_type_id', 'indexed_entities',
        ['entity_type', 'entity_id'], unique=True,
    )
    op.create_index('ix_indexed_entities_type', 'indexed_entities', ['entity_type'])
    op.create_index(
        'ix_indexed_entities_indexed_at', 'indexed_entities', ['indexed_at'],
        postgresql_ops={'indexed_at': 'DESC'},
    )


def downgrade() -> None:
    op.drop_index('ix_indexed_entities_indexed_at', table_name='indexed_entities')
    op.drop_index('ix_indexed_entities_type', table_name='indexed_entities')
    op.drop_index('ix_indexed_entities_type_id', table_name='indexed_entities')
    op.drop_table('indexed_entities')
