"""add encrypted AI data tables

Revision ID: add_encrypted_ai_tables
Revises:
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_encrypted_ai_tables'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create copilot_conversations table
    op.create_table(
        'copilot_conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('wallet_address', sa.String(64), nullable=False),
        sa.Column('session_id', sa.String(128), nullable=True),
        sa.Column('messages_encrypted', sa.Text(), nullable=True, comment='AES-256-GCM encrypted JSON conversation messages'),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('model_used', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_copilot_conversations_wallet_address', 'copilot_conversations', ['wallet_address'])
    op.create_index('ix_copilot_conversations_session_id', 'copilot_conversations', ['session_id'])
    op.create_index('ix_copilot_conversations_wallet_created', 'copilot_conversations', ['wallet_address', 'created_at'])

    # Create weekly_reports table
    op.create_table(
        'weekly_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('wallet_address', sa.String(64), nullable=False),
        sa.Column('week_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('week_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('narrative_text_encrypted', sa.Text(), nullable=True, comment='AES-256-GCM encrypted narrative analysis'),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_weekly_reports_wallet_week', 'weekly_reports', ['wallet_address', 'week_start'])

    # Create user_twin_profiles table
    op.create_table(
        'user_twin_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('wallet_address', sa.String(64), nullable=False, unique=True),
        sa.Column('embedding_vector_encrypted', sa.Text(), nullable=True, comment='AES-256-GCM encrypted embedding vector bytes'),
        sa.Column('strategy_params', sa.JSON(), nullable=True),
        sa.Column('accuracy_score', sa.Float(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_twin_profiles_wallet_address', 'user_twin_profiles', ['wallet_address'])


def downgrade() -> None:
    op.drop_table('user_twin_profiles')
    op.drop_table('weekly_reports')
    op.drop_table('copilot_conversations')
