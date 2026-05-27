"""Encrypted AI data models.

SQLAlchemy models with column-level encryption for:
- copilot_conversations.messages (JSONB → encrypted TEXT)
- weekly_reports.narrative_text (TEXT → encrypted TEXT)
- user_twin_profiles.embedding_vector (BYTEA → encrypted TEXT)

Each sensitive column is encrypted with AES-256-GCM at the application layer
before being written to the database. DB admins and backup operators see only
ciphertext.

"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, func, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from data_infrastructure.models import Base
from data_infrastructure.crypto.aead import (
    encrypt_value,
    decrypt_value,
    encrypt_bytes,
    decrypt_bytes,
)

# Key column identifiers (used by MasterKeyManager.get_data_key())
COL_CONVERSATIONS_MESSAGES = "copilot_conversations.messages"
COL_REPORTS_NARRATIVE = "weekly_reports.narrative_text"
COL_TWIN_EMBEDDING = "user_twin_profiles.embedding_vector"


def _get_data_key(column_name: str) -> bytes:
    """Get data key from MasterKeyManager.

    In production, this is called with the app's initialized MasterKeyManager.
    During migrations and tests, a placeholder key from env is used.
    """
    from data_infrastructure.crypto.keys import MasterKeyManager

    # Lazy initialization for migration context (no app container)
    keyring = os.environ.get("CRYPTO_KEYRING_DIR", "~/.hermes/crypto")
    mgr = MasterKeyManager(keyring_path=keyring)
    mgr.ensure_initialized()
    return mgr.get_data_key(column_name)


class CopilotConversation(Base):
    """Encrypted copilot conversation history.

    The `messages` column stores the full conversation as JSON, encrypted
    with AES-256-GCM. Each wallet_address can have multiple conversations.
    """
    __tablename__ = "copilot_conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    wallet_address: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False,
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True,
    )

    # Encrypted: full conversation messages as JSON
    _messages_encrypted: Mapped[Optional[str]] = mapped_column(
        "messages_encrypted", Text, nullable=True,
    )
    # Metadata about the conversation (not encrypted - structural data)
    message_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=func.cast(func.literal(0), Integer),
    )
    model_used: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_copilot_conversations_wallet_created", "wallet_address", "created_at"),
    )

    @property
    def messages(self) -> Optional[list]:
        """Decrypt and parse messages."""
        if self._messages_encrypted is None:
            return None
        key = _get_data_key(COL_CONVERSATIONS_MESSAGES)
        plaintext = decrypt_value(self._messages_encrypted, key)
        return json.loads(plaintext)

    @messages.setter
    def messages(self, value: Optional[list]) -> None:
        """Encrypt and store messages."""
        if value is None:
            self._messages_encrypted = None
            self.message_count = 0
            return
        json_str = json.dumps(value)
        key = _get_data_key(COL_CONVERSATIONS_MESSAGES)
        self._messages_encrypted = encrypt_value(json_str, key)
        self.message_count = len(value)

    def append_message(self, role: str, content: str, metadata: Optional[dict] = None) -> None:
        """Append a single message to the conversation."""
        current = self.messages or []
        msg = {"role": role, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()}
        if metadata:
            msg["metadata"] = metadata
        current.append(msg)
        self.messages = current  # triggers encryption via setter


class WeeklyReport(Base):
    """Weekly performance reports with encrypted narrative text.

    The `narrative_text` column contains the human-readable AI-generated
    analysis, encrypted with AES-256-GCM. Metrics remain as plaintext JSONB
    since they contain aggregates, not PII.
    """
    __tablename__ = "weekly_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    wallet_address: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False,
    )
    week_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    week_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    # Encrypted: AI-generated narrative analysis
    _narrative_text_encrypted: Mapped[Optional[str]] = mapped_column(
        "narrative_text_encrypted", Text, nullable=True,
    )

    # Plaintext metrics (aggregates, not PII)
    metrics: Mapped[Optional[dict]] = mapped_column(
        "metrics", JSON, nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_weekly_reports_wallet_week", "wallet_address", "week_start"),
    )

    @property
    def narrative_text(self) -> Optional[str]:
        """Decrypt narrative text."""
        if self._narrative_text_encrypted is None:
            return None
        key = _get_data_key(COL_REPORTS_NARRATIVE)
        return decrypt_value(self._narrative_text_encrypted, key)

    @narrative_text.setter
    def narrative_text(self, value: Optional[str]) -> None:
        """Encrypt narrative text."""
        if value is None:
            self._narrative_text_encrypted = None
            return
        key = _get_data_key(COL_REPORTS_NARRATIVE)
        self._narrative_text_encrypted = encrypt_value(value, key)


class UserTwinProfile(Base):
    """User twin profiles with encrypted embedding vectors.

    The `embedding_vector` stores the user's behavioral/strategy embedding
    as encrypted bytes. Strategy params remain plaintext as they are
    configuration, not sensitive data.
    """
    __tablename__ = "user_twin_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    wallet_address: Mapped[str] = mapped_column(
        String(64), index=True, unique=True, nullable=False,
    )

    # Encrypted: embedding vector (raw bytes → encrypted TEXT)
    _embedding_vector_encrypted: Mapped[Optional[str]] = mapped_column(
        "embedding_vector_encrypted", Text, nullable=True,
    )

    # Plaintext configuration
    strategy_params: Mapped[Optional[dict]] = mapped_column(
        "strategy_params", JSON, nullable=True,
    )
    accuracy_score: Mapped[Optional[float]] = mapped_column(
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=func.cast(func.literal(1), Integer),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def embedding_vector(self) -> Optional[bytes]:
        """Decrypt embedding vector."""
        if self._embedding_vector_encrypted is None:
            return None
        key = _get_data_key(COL_TWIN_EMBEDDING)
        return decrypt_bytes(self._embedding_vector_encrypted, key)

    @embedding_vector.setter
    def embedding_vector(self, value: Optional[bytes]) -> None:
        """Encrypt embedding vector."""
        if value is None:
            self._embedding_vector_encrypted = None
            return
        key = _get_data_key(COL_TWIN_EMBEDDING)
        self._embedding_vector_encrypted = encrypt_bytes(value, key)

    def update_embedding(self, vector: bytes, accuracy: Optional[float] = None) -> None:
        """Update embedding and bump version."""
        self.embedding_vector = vector
        self.version += 1
        if accuracy is not None:
            self.accuracy_score = accuracy
        self.updated_at = datetime.now(timezone.utc)
