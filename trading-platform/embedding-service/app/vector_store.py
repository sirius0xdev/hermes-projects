"""
Redis vector store using RedisVL for RediSearch-backed HNSW indexing.

Supports:
- Creating/dropping HNSW vector indexes (768 dimensions, cosine distance)
- Adding documents with metadata tags for filtering
- Semantic search with entity_type, date_range, and min_similarity filters
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from redis import Redis
from redisvl.index import VectorIndex
from redisvl.query import VectorQuery
from redisvl.schema import IndexSchema

from app.config import Settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Redis-backed vector store with RediSearch HNSW indexing."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self._redis: Optional[Redis] = None
        self._index: Optional[VectorIndex] = None
        self._initialized = False

    @property
    def redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(
                self.settings.redis_url, decode_responses=True
            )
        return self._redis

    @property
    def index(self) -> VectorIndex:
        if self._index is None:
            raise RuntimeError(
                "VectorStore not initialized. Call initialize() first."
            )
        return self._index

    def _build_schema(self) -> IndexSchema:
        """Build the RedisVL IndexSchema for HNSW vector index."""
        schema_dict = {
            "index": {
                "name": self.settings.vector_index_name,
                "prefix": self.settings.vector_index_name,
            },
            "storage_type": "hash",
            "fields": [
                {
                    "name": "embedding",
                    "type": "vector",
                    "attrs": {
                        "dims": self.settings.vector_index_dimensions,
                        "algorithm": "HNSW",
                        "distance_metric": "COSINE",
                        "datatype": "FLOAT32",
                    },
                },
                {
                    "name": "entity_type",
                    "type": "tag",
                },
                {
                    "name": "entity_id",
                    "type": "tag",
                },
                {
                    "name": "text",
                    "type": "text",
                },
                {
                    "name": "timestamp",
                    "type": "numeric",
                },
                {
                    "name": "metadata",
                    "type": "text",
                },
            ],
        }
        return IndexSchema.parse_object(schema_dict)

    async def initialize(self, drop_existing: bool = False) -> None:
        """Create the vector index in Redis.

        Args:
            drop_existing: If True, drop the existing index before creating.
        """
        try:
            # Check if index already exists
            info = self.redis.ft(self.settings.vector_index_name).info()
            if info:
                if drop_existing:
                    logger.info(
                        "Dropping existing index: %s",
                        self.settings.vector_index_name,
                    )
                    self.redis.ft(self.settings.vector_index_name).dropindex(
                        delete_documents=True
                    )
                else:
                    logger.info(
                        "Index %s already exists, reusing.",
                        self.settings.vector_index_name,
                    )
                    self._index = VectorIndex.from_dict(
                        self._build_schema().dict(), self.redis
                    )
                    self._initialized = True
                    return
        except Exception:
            # Index doesn't exist yet
            pass

        # Create new index
        self._index = VectorIndex.from_dict(
            self._build_schema().dict(), self.redis
        )
        self._index.create(overwrite=False)
        self._initialized = True
        logger.info(
            "Created vector index: %s (dims=%d, algo=%s)",
            self.settings.vector_index_name,
            self.settings.vector_index_dimensions,
            self.settings.vector_index_algorithm,
        )

    def _make_key(self, entity_type: str, entity_id: str) -> str:
        """Generate Redis key for a document.

        Format: {index_name}:{entity_type}:{entity_id}
        """
        return f"{self.settings.vector_index_name}:{entity_type}:{entity_id}"

    async def add_document(
        self,
        entity_type: str,
        entity_id: str,
        embedding: list[float],
        text: str,
        metadata: Optional[dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Add a single document to the vector index.

        Args:
            entity_type: Type of entity (e.g. 'trade', 'news', 'analysis').
            entity_id: Unique identifier for this entity.
            embedding: Normalized embedding vector (768 dimensions).
            text: Original text content.
            metadata: Additional metadata fields.
            timestamp: When this entity was created/updated.

        Returns:
            The Redis key for this document.
        """
        if not self._initialized:
            raise RuntimeError("VectorStore not initialized.")

        ts = timestamp or datetime.now(timezone.utc)
        key = self._make_key(entity_type, entity_id)

        doc = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "text": text,
            "timestamp": ts.timestamp(),
            "metadata": json.dumps(metadata or {}),
            "embedding": embedding,
        }

        self.index.add_documents([doc], id_field=None, keys=[key])
        logger.debug("Indexed document: %s", key)
        return key

    async def add_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> list[str]:
        """Batch-add documents to the vector index.

        Args:
            documents: List of dicts with keys:
                - entity_type (str)
                - entity_id (str)
                - embedding (list[float])
                - text (str)
                - metadata (dict, optional)
                - timestamp (datetime, optional)

        Returns:
            List of Redis keys for the indexed documents.
        """
        if not self._initialized:
            raise RuntimeError("VectorStore not initialized.")

        keys = []
        docs = []
        for doc in documents:
            ts = doc.get("timestamp") or datetime.now(timezone.utc)
            key = self._make_key(doc["entity_type"], doc["entity_id"])
            keys.append(key)
            docs.append(
                {
                    "entity_type": doc["entity_type"],
                    "entity_id": doc["entity_id"],
                    "text": doc["text"],
                    "timestamp": ts.timestamp(),
                    "metadata": json.dumps(doc.get("metadata") or {}),
                    "embedding": doc["embedding"],
                }
            )

        self.index.add_documents(docs, id_field=None, keys=keys)
        logger.info("Batch indexed %d documents", len(docs))
        return keys

    async def search(
        self,
        query_embedding: list[float],
        entity_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        min_similarity: float = 0.5,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Semantic search against the vector index.

        Args:
            query_embedding: Normalized query embedding (768 dimensions).
            entity_type: Filter by entity type (e.g. 'trade', 'news').
            date_from: Lower bound for timestamp filter (inclusive).
            date_to: Upper bound for timestamp filter (inclusive).
            min_similarity: Minimum cosine similarity threshold (0-1).
            top_k: Maximum number of results to return.

        Returns:
            List of result dicts with keys:
                - key: Redis key
                - entity_type: str
                - entity_id: str
                - text: str
                - score: float (cosine similarity)
                - timestamp: datetime
                - metadata: dict
        """
        if not self._initialized:
            raise RuntimeError("VectorStore not initialized.")

        # Build filter expression
        filters: list[str] = []
        if entity_type:
            filters.append(f'@entity_type:{{{entity_type}}}')
        if date_from:
            filters.append(f"@timestamp:[{date_from.timestamp()} +inf]")
        if date_to:
            filters.append(f"@timestamp:[-inf {date_to.timestamp()}]")

        filter_expr = " ".join(filters) if filters else "*"

        query = VectorQuery(
            vector=query_embedding,
            field_name="embedding",
            return_fields=[
                "entity_type",
                "entity_id",
                "text",
                "timestamp",
                "metadata",
                "embedding",
            ],
            num_results=top_k,
        )

        results = self.index.query(vector=query.vector, query_string=filter_expr, return_fields=query.return_fields, num_results=query.num_results)

        # Parse results and apply similarity threshold
        parsed: list[dict[str, Any]] = []
        for r in results:
            score = r.get("vector_score", 0.0)
            if isinstance(score, str):
                score = float(score)
            if score < min_similarity:
                continue

            ts_val = r.get("timestamp", 0)
            if isinstance(ts_val, str):
                ts_val = float(ts_val)

            meta_raw = r.get("metadata", "{}")
            if isinstance(meta_raw, str):
                try:
                    meta = json.loads(meta_raw)
                except json.JSONDecodeError:
                    meta = {}
            else:
                meta = meta_raw

            parsed.append(
                {
                    "key": r.get("id", ""),
                    "entity_type": r.get("entity_type", ""),
                    "entity_id": r.get("entity_id", ""),
                    "text": r.get("text", ""),
                    "score": round(score, 4),
                    "timestamp": datetime.fromtimestamp(ts_val),
                    "metadata": meta,
                }
            )

        # Sort by score descending
        parsed.sort(key=lambda x: x["score"], reverse=True)
        logger.info(
            "Semantic search: %d results (threshold=%.2f)",
            len(parsed),
            min_similarity,
        )
        return parsed

    async def delete_document(self, entity_type: str, entity_id: str) -> bool:
        """Delete a document from the vector index.

        Args:
            entity_type: Entity type.
            entity_id: Entity ID.

        Returns:
            True if the document was found and deleted.
        """
        if not self._initialized:
            raise RuntimeError("VectorStore not initialized.")

        key = self._make_key(entity_type, entity_id)
        deleted = self.index.delete_document(key)
        if deleted:
            logger.debug("Deleted document: %s", key)
        return bool(deleted)

    async def get_index_info(self) -> dict[str, Any]:
        """Get index statistics.

        Returns:
            Dict with index name, doc_count, and other stats.
        """
        if not self._initialized:
            raise RuntimeError("VectorStore not initialized.")

        info = self.redis.ft(self.settings.vector_index_name).info()
        return {
            "index_name": self.settings.vector_index_name,
            "doc_count": info.get("num_docs", 0) if info else 0,
        }
