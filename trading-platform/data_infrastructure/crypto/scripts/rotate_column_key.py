#!/usr/bin/env python3
"""Re-encrypt all rows in a column after key rotation.

Usage:
    python3 scripts/rotate_column_key.py \
      --column copilot_conversations.messages \
      --db-url postgresql+asyncpg://trading:trading@localhost:5432/trading_db
"""
import argparse
import logging
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_infrastructure.crypto.aead import encrypt_value, decrypt_value, encrypt_bytes, decrypt_bytes
from data_infrastructure.crypto.keys import MasterKeyManager
from data_infrastructure.models.encrypted_models import (
    CopilotConversation,
    WeeklyReport,
    UserTwinProfile,
    COL_CONVERSATIONS_MESSAGES,
    COL_REPORTS_NARRATIVE,
    COL_TWIN_EMBEDDING,
)

logger = logging.getLogger(__name__)

# Map column identifiers to (model, encrypted_attr, property_name, is_bytes)
COLUMN_MAP = {
    COL_CONVERSATIONS_MESSAGES: (
        CopilotConversation,
        "_messages_encrypted",
        "messages",
        False,  # text
    ),
    COL_REPORTS_NARRATIVE: (
        WeeklyReport,
        "_narrative_text_encrypted",
        "narrative_text",
        False,  # text
    ),
    COL_TWIN_EMBEDDING: (
        UserTwinProfile,
        "_embedding_vector_encrypted",
        "embedding_vector",
        True,  # bytes
    ),
}


def rotate_column_key(column_name: str, db_url: str, dry_run: bool = False) -> int:
    """Re-encrypt all rows for a column with the new data key."""
    if column_name not in COLUMN_MAP:
        print(f"Unknown column: {column_name}")
        print(f"Known columns: {list(COLUMN_MAP.keys())}")
        return 1

    model, enc_attr, prop_name, is_bytes = COLUMN_MAP[column_name]
    mgr = MasterKeyManager()
    mgr.ensure_initialized()

    # Get the OLD data key (before rotation)
    old_key = mgr.get_data_key(column_name)

    # Rotate to get NEW key
    new_version = mgr.rotate_data_key(column_name)
    new_key = mgr.get_data_key(column_name)

    print(f"Rotating {column_name}: version {new_version}")
    print(f"Using database: {db_url}")

    # Connect to database
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(db_url)
    rows_updated = 0

    with Session(engine) as session:
        rows = session.query(model).filter(getattr(model, enc_attr) != None).all()
        print(f"Found {len(rows)} rows to re-encrypt")

        for row in rows:
            encrypted_val = getattr(row, enc_attr)
            if encrypted_val is None:
                continue

            # Decrypt with old key
            if is_bytes:
                plaintext = decrypt_bytes(encrypted_val, old_key)
            else:
                plaintext = decrypt_value(encrypted_val, old_key)

            # Encrypt with new key
            if is_bytes:
                new_encrypted = encrypt_bytes(plaintext, new_key)
            else:
                new_encrypted = encrypt_value(plaintext, new_key)

            if not dry_run:
                setattr(row, enc_attr, new_encrypted)
                rows_updated += 1

        if not dry_run:
            session.commit()

    print(f"Re-encrypted {rows_updated}/{len(rows)} rows")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Rotate column encryption key and re-encrypt data")
    parser.add_argument("--column", required=True, help="Column identifier (e.g. copilot_conversations.messages)")
    parser.add_argument("--db-url", required=True, help="Database URL")
    parser.add_argument("--dry-run", action="store_true", help="Decrypt/encrypt without writing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    sys.exit(rotate_column_key(args.column, args.db_url, args.dry_run))


if __name__ == "__main__":
    main()
