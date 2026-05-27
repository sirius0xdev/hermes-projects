"""Tests for embedding service client, trade indexer, news indexer, and persistence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from data_service.app.embedding.client import EmbeddingServiceClient
from data_service.app.indexers.trade_indexer import TradeIndexer
from data_service.app.indexers.news_indexer import NewsIndexer


# ── EmbeddingServiceClient tests ──────────────────────────────────

class TestEmbeddingServiceClient:
    """Test the embedding service HTTP client."""

    @pytest.fixture
    def client(self):
        return EmbeddingServiceClient(base_url="http://localhost:9999", timeout=5.0)

    @pytest.mark.asyncio
    async def test_index_document(self, client):
        """Test indexing a single document."""
        fake_embedding = [0.1] * 768
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"key": "trade:abc123", "entity_type": "trade", "entity_id": "abc123", "status": "indexed"},
            )
            result = await client.index_document(
                entity_type="trade",
                entity_id="abc123",
                embedding=fake_embedding,
                text="BUY 1.5 BTC-USD at $50000.0000",
                metadata={"symbol": "BTC-USD"},
            )
            assert result["key"] == "trade:abc123"
            mock_post.assert_called_once_with("/v1/index", json={
                "entity_type": "trade",
                "entity_id": "abc123",
                "embedding": fake_embedding,
                "text": "BUY 1.5 BTC-USD at $50000.0000",
                "metadata": {"symbol": "BTC-USD"},
            })

    @pytest.mark.asyncio
    async def test_batch_index_documents(self, client):
        """Test batch indexing."""
        docs = [
            {"entity_type": "trade", "entity_id": "t1", "embedding": [0.1] * 768, "text": "trade1"},
            {"entity_type": "trade", "entity_id": "t2", "embedding": [0.2] * 768, "text": "trade2"},
        ]
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"indexed": [{"key": "trade:t1", "entity_type": "trade", "entity_id": "t1"},
                                           {"key": "trade:t2", "entity_type": "trade", "entity_id": "t2"}],
                               "total": 2},
            )
            result = await client.batch_index_documents(docs)
            assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_batch_index_exceeds_max(self, client):
        """Test batch indexing rejects >500 documents."""
        docs = [{"entity_type": "trade", "entity_id": str(i), "embedding": [0.1] * 768, "text": "t"} for i in range(501)]
        with pytest.raises(ValueError, match="exceeds maximum"):
            await client.batch_index_documents(docs)

    @pytest.mark.asyncio
    async def test_delete_document(self, client):
        """Test deleting a document."""
        with patch.object(client._client, "delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = MagicMock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"status": "deleted", "entity_type": "news", "entity_id": "n1"},
            )
            result = await client.delete_document("news", "n1")
            assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_search(self, client):
        """Test semantic search."""
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"results": [{"key": "trade:t1", "entity_type": "trade", "entity_id": "t1",
                                           "text": "BUY BTC", "score": 0.95, "timestamp": "2026-01-01",
                                           "metadata": {}}], "total": 1},
            )
            result = await client.search(
                query_embedding=[0.1] * 768,
                entity_type="trade",
                min_similarity=0.8,
                top_k=5,
            )
            assert result["total"] == 1
            assert result["results"][0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_get_index_stats(self, client):
        """Test getting index stats."""
        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"index_name": "embedding_index", "doc_count": 150},
            )
            result = await client.get_index_stats()
            assert result["doc_count"] == 150

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        async with EmbeddingServiceClient(base_url="http://test") as c:
            assert isinstance(c, EmbeddingServiceClient)


# ── TradeIndexer tests ─────────────────────────────────────────────

class TestTradeIndexer:
    """Test trade event serialization and indexing."""

    @pytest.fixture
    def embedding_client(self):
        return MagicMock(spec=EmbeddingServiceClient)

    @pytest.fixture
    def indexer(self, embedding_client):
        return TradeIndexer(embedding_client=embedding_client, batch_size=5, flush_interval=1.0)

    def test_serialize_trade_basic(self, indexer):
        """Test basic trade serialization."""
        trade = {
            "trade_id": "t_001",
            "symbol": "BTC-USD",
            "side": "buy",
            "price": Decimal("50000.00"),
            "quantity": Decimal("1.5"),
            "source": "binance",
            "timestamp": "2026-01-01T12:00:00",
        }
        context_text, metadata = indexer._serialize_trade(trade)
        assert "BUY" in context_text
        assert "1.5" in context_text
        assert "BTC-USD" in context_text
        assert "50000" in context_text
        assert metadata["symbol"] == "BTC-USD"
        assert metadata["side"] == "buy"
        assert metadata["price"] == 50000.0
        assert metadata["quantity"] == 1.5
        assert metadata["notional"] == 75000.0

    def test_serialize_trade_float_values(self, indexer):
        """Test trade serialization with float values."""
        trade = {
            "trade_id": "t_002",
            "symbol": "ETH-USD",
            "side": "sell",
            "price": 3200.50,
            "quantity": 10.0,
            "source": "hyperliquid",
            "timestamp": "2026-01-01T13:00:00",
        }
        context_text, metadata = indexer._serialize_trade(trade)
        assert "SELL" in context_text
        assert metadata["notional"] == 32005.0

    def test_add_trade_queues(self, indexer):
        """Test that add_trade queues the trade."""
        trade = {
            "trade_id": "t_003",
            "symbol": "SOL-USD",
            "side": "buy",
            "price": 150.0,
            "quantity": 100.0,
            "source": "helius",
            "timestamp": "2026-01-01T14:00:00",
        }
        indexer.add_trade(trade)
        assert len(indexer._buffer) == 1
        assert indexer._buffer[0]["entity_type"] == "trade"
        assert indexer._buffer[0]["entity_id"] == "t_003"

    def test_add_trade_no_id_skips(self, indexer):
        """Test that trades without trade_id are skipped."""
        indexer.add_trade({"symbol": "BTC-USD", "side": "buy"})
        assert len(indexer._buffer) == 0

    @pytest.mark.asyncio
    async def test_flush_empty_noop(self, indexer):
        """Test that flushing an empty buffer is a no-op."""
        await indexer._flush()  # should not raise

    @pytest.mark.asyncio
    async def test_start_stop(self, indexer):
        """Test start and stop lifecycle."""
        await indexer.start()
        assert indexer._running
        await indexer.stop()
        assert not indexer._running

    @pytest.mark.asyncio
    async def test_set_on_indexed_callback(self, indexer):
        """Test that the on_indexed callback is stored."""
        callback_called = []
        async def mock_callback(entity):
            callback_called.append(entity)
        indexer.set_on_indexed(mock_callback)
        assert indexer._on_indexed is mock_callback


# ── NewsIndexer tests ──────────────────────────────────────────────

class TestNewsIndexer:
    """Test news article serialization and indexing."""

    @pytest.fixture
    def embedding_client(self):
        return MagicMock(spec=EmbeddingServiceClient)

    @pytest.fixture
    def indexer(self, embedding_client):
        return NewsIndexer(embedding_client=embedding_client, batch_size=3, flush_interval=2.0)

    def test_serialize_article_full(self, indexer):
        """Test full article serialization."""
        article = {
            "article_id": "n_001",
            "title": "Bitcoin Surges Past $50K",
            "summary": "BTC breaks resistance level amid institutional buying.",
            "source": "CoinDesk",
            "author": "Jane Doe",
            "published_at": "2026-01-01T10:00:00",
            "tickers": ["BTC-USD"],
            "categories": ["market"],
        }
        context_text, metadata = indexer._serialize_article(article)
        assert "Bitcoin Surges" in context_text
        assert "BTC breaks resistance" in context_text
        assert "BTC-USD" in context_text
        assert "CoinDesk" in context_text
        assert metadata["article_id"] == "n_001"
        assert metadata["tickers"] == ["BTC-USD"]
        assert metadata["categories"] == ["market"]

    def test_serialize_article_minimal(self, indexer):
        """Test minimal article serialization (title only)."""
        article = {
            "article_id": "n_002",
            "title": "Ethereum Update Released",
        }
        context_text, metadata = indexer._serialize_article(article)
        assert "Ethereum Update Released" in context_text
        assert metadata["title"] == "Ethereum Update Released"

    def test_serialize_article_content_fallback(self, indexer):
        """Test content used as fallback when no summary."""
        article = {
            "article_id": "n_003",
            "title": "Long Article",
            "content": "A" * 600,
        }
        context_text, metadata = indexer._serialize_article(article)
        # Should use first 500 chars of content
        assert "AAAA" in context_text

    def test_add_article_queues(self, indexer):
        """Test that add_article queues the article."""
        article = {
            "article_id": "n_004",
            "title": "Solana DEX Volume Hits Record",
            "tickers": ["SOL-USD"],
        }
        indexer.add_article(article)
        assert len(indexer._buffer) == 1
        assert indexer._buffer[0]["entity_type"] == "news"
        assert indexer._buffer[0]["entity_id"] == "n_004"

    def test_add_article_no_id_skips(self, indexer):
        """Test that articles without article_id are skipped."""
        indexer.add_article({"title": "No ID Article"})
        assert len(indexer._buffer) == 0

    @pytest.mark.asyncio
    async def test_flush_empty_noop(self, indexer):
        """Test that flushing an empty buffer is a no-op."""
        await indexer._flush()

    @pytest.mark.asyncio
    async def test_start_stop(self, indexer):
        """Test start and stop lifecycle."""
        await indexer.start()
        assert indexer._running
        await indexer.stop()
        assert not indexer._running
