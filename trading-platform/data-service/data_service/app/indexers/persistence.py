"""Indexer persistence — writes indexed entity records to PostgreSQL.

Used by TradeIndexer and NewsIndexer as the _on_indexed callback
to persist indexed entity metadata locally after successful embedding.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_service.app.db import db_config
from data_service.app.models import IndexedEntity

logger = logging.getLogger(__name__)


class IndexerPersistence:
    """Persists indexed entity records to the local database."""

    def __init__(self):
        self._db = None  # set via set_db_config()

    @classmethod
    def get_db(cls) -> Any:
        """Get the global db_config singleton."""
        if db_config is None:
            raise RuntimeError("Database not initialized")
        return db_config

    async def persist_entity(
        self,
        entity_type: str,
        entity_id: str,
        context_text: str,
        metadata: Optional[dict[str, Any]] = None,
        vector_key: Optional[str] = None,
    ) -> IndexedEntity:
        """Insert or update an indexed entity record.

        On duplicate (entity_type, entity_id), updates the existing row
        with new vector_key and context_text.
        """
        session_factory = self.get_db().session_factory

        async with session_factory() as session:
            # Check if exists
            stmt = select(IndexedEntity).where(
                IndexedEntity.entity_type == entity_type,
                IndexedEntity.entity_id == entity_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.vector_key = vector_key
                existing.context_text = context_text
                existing.metadata = metadata
                existing.indexed = True
                await session.commit()
                logger.debug(
                    "Updated indexed entity: type=%s id=%s", entity_type, entity_id
                )
                return existing

            new_entity = IndexedEntity(
                entity_type=entity_type,
                entity_id=entity_id,
                context_text=context_text,
                metadata=metadata,
                vector_key=vector_key,
                indexed=True,
            )
            session.add(new_entity)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                # Race condition — another indexer thread inserted the same entity
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    existing.vector_key = vector_key
                    await session.commit()
                    logger.debug(
                        "Resolved race on entity: type=%s id=%s", entity_type, entity_id
                    )
                    return existing
                raise

            logger.debug(
                "Persisted indexed entity: type=%s id=%s", entity_type, entity_id
            )
            return new_entity

    async def mark_entity_deleted(
        self,
        entity_type: str,
        entity_id: str,
    ) -> bool:
        """Mark an entity as no longer indexed (soft delete)."""
        session_factory = self.get_db().session_factory

        async with session_factory() as session:
            stmt = select(IndexedEntity).where(
                IndexedEntity.entity_type == entity_type,
                IndexedEntity.entity_id == entity_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.indexed = False
                await session.commit()
                return True
            return False
