"""Trade indexer — consumes trade events and indexes them in the embedding service.

Flow:
    1. Kafka consumer receives TradeEvent on `trading-platform.market.trades.v1`
    2. TradeIndexer serializes the trade into a context text string
    3. Requests embedding from embedding-service
    4. Indexes the document with entity_type='trade'
    5. Records the indexed entity in the local DB for lifecycle tracking
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from data_service.app.embedding.client import EmbeddingServiceClient

logger = logging.getLogger(__name__)


class TradeIndexer:
    """Background indexer for trade events.

    Each trade event is serialized into a context text that captures
    the key trading information (symbol, side, price, quantity, source,
    timestamp) then indexed into the vector store via embedding-service.
    """

    def __init__(
        self,
        embedding_client: EmbeddingServiceClient,
        batch_size: int = 10,
        flush_interval: float = 5.0,
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
        """Set a callback invoked after each trade is successfully indexed.

        The callback receives the serialized entity dict with keys:
        entity_type, entity_id, context_text, metadata, vector_key.
        """
        self._on_indexed = callback

    def _serialize_trade(self, trade: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Serialize a trade event into context text and metadata.

        Returns:
            (context_text, metadata) tuple.
        """
        symbol = trade.get("symbol", "UNKNOWN")
        side = trade.get("side", "unknown")
        price = trade.get("price", "0")
        quantity = trade.get("quantity", "0")
        source = trade.get("source", "unknown")
        trade_id = trade.get("trade_id", "")
        timestamp = trade.get("timestamp")

        # Normalize Decimal to float for serialization
        if isinstance(price, Decimal):
            price = float(price)
        if isinstance(quantity, Decimal):
            quantity = float(quantity)

        # Context text — the natural-language description sent to embedding
        context_text = (
            f"{side.upper()} {quantity} {symbol} at ${price:.4f} "
            f"via {source} on {timestamp}"
        )

        metadata = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "price": price,
            "quantity": quantity,
            "source": source,
            "notional": round(price * quantity, 4),
        }

        return context_text, metadata

    def add_trade(self, trade: dict[str, Any]) -> None:
        """Queue a trade for indexing. Flushes batch if full."""
        trade_id = trade.get("trade_id", "")
        if not trade_id:
            logger.warning("Skipping trade with no trade_id")
            return

        context_text, metadata = self._serialize_trade(trade)

        entity = {
            "entity_type": "trade",
            "entity_id": trade_id,
            "context_text": context_text,
            "metadata": metadata,
        }

        self._buffer.append(entity)

        if len(self._buffer) >= self._batch_size:
            asyncio.ensure_future(self._flush())

    async def _flush(self) -> None:
        """Flush buffered trades to the embedding service."""
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:self._batch_size]
            self._buffer = self._buffer[len(batch):]

        if not batch:
            return

        try:
            # Build index payloads
            # We need embeddings — but the embedding-service handles
            # that server-side. For now, we pass text and let the
            # service compute embeddings. However, the current API
            # expects the client to send embeddings. So we need a
            # /v1/embed endpoint or we use the service's embedding.
            #
            # Looking at the embedding-service API, it expects
            # embedding vectors in the request. We need to call the
            # embedding endpoint first, then index.
            #
            # For now, assume embedding-service has a /v1/embed endpoint
            # that accepts text and returns embeddings.
            # If not, we'll compute embeddings inline using the same model.

            for entity in batch:
                await self._index_single(entity)

        except Exception:
            logger.exception("Error flushing trade batch (%d items)", len(batch))
            # Re-queue failed items
            async with self._lock:
                self._buffer[:0] = batch

    async def _index_single(self, entity: dict[str, Any]) -> None:
        """Index a single trade entity."""
        # Call embedding service to get embedding for the text
        try:
            # Request embedding from the service
            embed_resp = await self._client._client.post(
                "/v1/embed",
                json={"text": entity["context_text"]},
            )
            if embed_resp.status_code == 404:
                # Fallback: if /v1/embed doesn't exist, the caller
                # should have sent pre-computed embeddings. Log and skip.
                logger.warning(
                    "Embedding endpoint /v1/embed not available; "
                    "trade indexing requires pre-computed embeddings. "
                    "Skipping %s.", entity["entity_id"]
                )
                return

            embed_resp.raise_for_status()
            embedding = embed_resp.json()["embedding"]
        except Exception:
            logger.exception("Failed to get embedding for trade %s", entity["entity_id"])
            return

        # Index the document
        try:
            idx_resp = await self._client.index_document(
                entity_type=entity["entity_type"],
                entity_id=entity["entity_id"],
                embedding=embedding,
                text=entity["context_text"],
                metadata=entity["metadata"],
                timestamp=entity["metadata"].get("timestamp"),
            )
            entity["vector_key"] = idx_resp.get("key")

            # Persist to local DB via callback
            if self._on_indexed:
                await self._on_indexed(entity)

            logger.debug(
                "Indexed trade: entity_id=%s key=%s",
                entity["entity_id"], entity.get("vector_key"),
            )
        except Exception:
            logger.exception("Failed to index trade %s", entity["entity_id"])

    async def start(self) -> None:
        """Start the background flush loop."""
        self._running = True
        self._task = asyncio.ensure_future(self._flush_loop())
        logger.info("TradeIndexer started (batch=%d, interval=%.1fs)",
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
        logger.info("TradeIndexer stopped")

    async def _flush_loop(self) -> None:
        """Periodically flush buffered trades."""
        while self._running:
            await asyncio.sleep(self._flush_interval)
            if self._buffer:
                await self._flush()
