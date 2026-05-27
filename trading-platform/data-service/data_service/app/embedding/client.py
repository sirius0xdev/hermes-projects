"""Embedding service client for data-service.

Wraps the embedding-service REST API with typed methods for
indexing documents, searching, and managing the vector index.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class EmbeddingServiceClient:
    """Async HTTP client for the embedding-service.

    Endpoints:
        POST /v1/index          — index a single document
        POST /v1/index/batch    — batch index documents
        DELETE /v1/index/:type/:id — delete a document
        GET  /v1/index/stats    — index statistics
        POST /v1/search         — semantic search
    """

    def __init__(
        self,
        base_url: str = "http://embedding-service:8000",
        timeout: float = 10.0,
        dimensions: int = 768,
    ):
        self.base_url = base_url.rstrip("/")
        self.dimensions = dimensions
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ── Indexing ───────────────────────────────────────────────────

    async def index_document(
        self,
        entity_type: str,
        entity_id: str,
        embedding: list[float],
        text: str,
        metadata: Optional[dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> dict[str, Any]:
        """Index a single document."""
        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "embedding": embedding,
            "text": text,
            "metadata": metadata or {},
        }
        if timestamp:
            payload["timestamp"] = timestamp

        resp = await self._client.post("/v1/index", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def batch_index_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Batch index multiple documents (max 500)."""
        if len(documents) > 500:
            raise ValueError("Batch size exceeds maximum (500 documents)")

        payload = {"documents": documents}
        resp = await self._client.post("/v1/index/batch", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def delete_document(
        self,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """Delete a document from the vector index."""
        resp = await self._client.delete(f"/v1/index/{entity_type}/{entity_id}")
        resp.raise_for_status()
        return resp.json()

    # ── Search ─────────────────────────────────────────────────────

    async def search(
        self,
        query_embedding: list[float],
        entity_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        min_similarity: float = 0.5,
        top_k: int = 20,
    ) -> dict[str, Any]:
        """Semantic search against the vector index."""
        payload: dict[str, Any] = {
            "query_embedding": query_embedding,
            "min_similarity": min_similarity,
            "top_k": top_k,
        }
        if entity_type:
            payload["entity_type"] = entity_type
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to

        resp = await self._client.post("/v1/search", json=payload)
        resp.raise_for_status()
        return resp.json()

    # ── Stats ──────────────────────────────────────────────────────

    async def get_index_stats(self) -> dict[str, Any]:
        """Get vector index statistics."""
        resp = await self._client.get("/v1/index/stats")
        resp.raise_for_status()
        return resp.json()

    # ── Context manager support ────────────────────────────────────

    async def __aenter__(self) -> EmbeddingServiceClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
