"""News indexer — consumes news articles and indexes them in the embedding service.

Flow:
    1. Kafka consumer receives NewsArticle on `trading-platform.news.feed.v1`
    2. NewsIndexer serializes the article into context text
    3. Requests embedding from embedding-service
    4. Indexes the document with entity_type='news'
    5. Records the indexed entity in the local DB for lifecycle tracking
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from data_service.app.embedding.client import EmbeddingServiceClient

logger = logging.getLogger(__name__)


class NewsIndexer:
    """Background indexer for news articles.

    Each news article is serialized into a context text that captures
    the title, summary, tickers, categories, and source, then indexed
    into the vector store via embedding-service.
    """

    def __init__(
        self,
        embedding_client: EmbeddingServiceClient,
        batch_size: int = 5,
        flush_interval: float = 10.0,
    ):
        self._client = embedding_client
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_indexed: Optional[Callable] = None
        """Optional callback(entity_dict) for DB persistence."""

    def set_on_indexed(self, callback: Callable) -> None:
        """Set a callback invoked after each news article is successfully indexed.

        The callback receives the serialized entity dict with keys:
        entity_type, entity_id, context_text, metadata, vector_key.
        """
        self._on_indexed = callback

    def _serialize_article(self, article: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Serialize a news article into context text and metadata.

        Returns:
            (context_text, metadata) tuple.
        """
        article_id = article.get("article_id", "")
        title = article.get("title", "")
        summary = article.get("summary", "")
        content = article.get("content", "")
        source = article.get("source", "")
        author = article.get("author", "")
        published_at = article.get("published_at")
        tickers = article.get("tickers", [])
        categories = article.get("categories", [])

        # Build context text — the natural-language description for embedding
        parts = [title]
        if summary:
            parts.append(summary)
        elif content:
            # Use first 500 chars of content if no summary
            parts.append(content[:500])
        if tickers:
            parts.append(f"Related tickers: {', '.join(tickers)}")
        if categories:
            parts.append(f"Categories: {', '.join(categories)}")
        if source:
            parts.append(f"Source: {source}")
        if author:
            parts.append(f"By {author}")
        if published_at:
            parts.append(f"Published: {published_at}")

        context_text = ". ".join(parts)

        metadata = {
            "article_id": article_id,
            "title": title,
            "source": source,
            "author": author,
            "published_at": str(published_at) if published_at else None,
            "tickers": tickers,
            "categories": categories,
        }

        return context_text, metadata

    def add_article(self, article: dict[str, Any]) -> None:
        """Queue a news article for indexing. Flushes batch if full."""
        article_id = article.get("article_id", "")
        if not article_id:
            logger.warning("Skipping article with no article_id")
            return

        context_text, metadata = self._serialize_article(article)

        entity = {
            "entity_type": "news",
            "entity_id": article_id,
            "context_text": context_text,
            "metadata": metadata,
        }

        self._buffer.append(entity)

        if len(self._buffer) >= self._batch_size:
            asyncio.ensure_future(self._flush())

    async def _flush(self) -> None:
        """Flush buffered articles to the embedding service."""
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:self._batch_size]
            self._buffer = self._buffer[len(batch):]

        if not batch:
            return

        try:
            for entity in batch:
                await self._index_single(entity)
        except Exception:
            logger.exception("Error flushing news batch (%d items)", len(batch))
            # Re-queue failed items
            async with self._lock:
                self._buffer[:0] = batch

    async def _index_single(self, entity: dict[str, Any]) -> None:
        """Index a single news entity."""
        # Get embedding
        try:
            embed_resp = await self._client._client.post(
                "/v1/embed",
                json={"text": entity["context_text"]},
            )
            if embed_resp.status_code == 404:
                logger.warning(
                    "Embedding endpoint /v1/embed not available; "
                    "news indexing requires pre-computed embeddings. "
                    "Skipping %s.", entity["entity_id"]
                )
                return
            embed_resp.raise_for_status()
            embedding = embed_resp.json()["embedding"]
        except Exception:
            logger.exception("Failed to get embedding for article %s", entity["entity_id"])
            return

        # Index the document
        try:
            idx_resp = await self._client.index_document(
                entity_type=entity["entity_type"],
                entity_id=entity["entity_id"],
                embedding=embedding,
                text=entity["context_text"],
                metadata=entity["metadata"],
                timestamp=entity["metadata"].get("published_at"),
            )
            entity["vector_key"] = idx_resp.get("key")

            # Persist to local DB via callback
            if self._on_indexed:
                await self._on_indexed(entity)

            logger.debug(
                "Indexed news: entity_id=%s key=%s",
                entity["entity_id"], entity.get("vector_key"),
            )
        except Exception:
            logger.exception("Failed to index article %s", entity["entity_id"])

    async def start(self) -> None:
        """Start the background flush loop."""
        self._running = True
        self._task = asyncio.ensure_future(self._flush_loop())
        logger.info("NewsIndexer started (batch=%d, interval=%.1fs)",
                     self._batch_size, self._flush_interval)

    async def stop(self) -> None:
        """Stop the indexer and flush remaining items."""
        self._running = False
        if self._buffer:
            await self._flush()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("NewsIndexer stopped")

    async def _flush_loop(self) -> None:
        """Periodically flush buffered articles."""
        while self._running:
            await asyncio.sleep(self._flush_interval)
            if self._buffer:
                await self._flush()
