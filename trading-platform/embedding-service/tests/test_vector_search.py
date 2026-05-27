"""
Unit tests for vector_store.py and search/indexing routes.

Uses fully mocked Redis since redis/redisvl are not installed in the
workspace venv (they ship in the Docker image).  Tests cover:

- Index creation and document indexing
- Semantic search with filters (entity_type, date_range, min_similarity)
- Batch indexing
- Document deletion
- Index stats
- Route endpoints (via FastAPI TestClient)
"""

import asyncio
import json
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Mock redis and redisvl *before* any import of app.vector_store
# ---------------------------------------------------------------------------
sys.modules["redis"] = MagicMock()
sys.modules["redisvl"] = MagicMock()
sys.modules["redisvl.index"] = MagicMock()
sys.modules["redisvl.query"] = MagicMock()
sys.modules["redisvl.schema"] = MagicMock()


class TestVectorStore:
    """Tests for VectorStore class (with mocked Redis)."""

    @pytest.fixture
    def mock_redis(self):
        redis = MagicMock()
        ft_mock = MagicMock()
        ft_mock.info.return_value = {}  # no existing index
        redis.ft.return_value = ft_mock
        return redis

    @pytest.fixture
    def mock_settings(self):
        from app.config import Settings

        return Settings(
            vector_index_name="test_index",
            vector_index_dimensions=768,
            vector_index_algorithm="HNSW",
            redis_url="redis://localhost:6379/0",
        )

    @pytest.fixture
    def vector_store(self, mock_redis, mock_settings):
        from app.vector_store import VectorStore

        vs = VectorStore(mock_settings)
        vs._redis = mock_redis  # bypass property
        yield vs

    def test_build_schema_dimensions(self, vector_store, mock_settings):
        """Schema dict should have correct vector dimensions."""
        # Test the raw dict produced by _build_schema before IndexSchema wraps it
        # We patch parse_object to capture the input dict
        captured = {}

        def capture_parse(obj):
            captured.update(obj)
            return MagicMock(dict=lambda: obj)

        with patch("app.vector_store.IndexSchema") as MockSchema:
            MockSchema.parse_object = capture_parse
            vector_store._build_schema()

        vector_field = None
        for field in captured.get("fields", []):
            if field.get("name") == "embedding":
                vector_field = field
                break
        assert vector_field is not None
        assert vector_field["attrs"]["dims"] == 768
        assert vector_field["attrs"]["algorithm"] == "HNSW"
        assert vector_field["attrs"]["distance_metric"] == "COSINE"

    def test_build_schema_fields(self, vector_store):
        """Schema dict should include all expected fields."""
        captured = {}

        def capture_parse(obj):
            captured.update(obj)
            return MagicMock(dict=lambda: obj)

        with patch("app.vector_store.IndexSchema") as MockSchema:
            MockSchema.parse_object = capture_parse
            vector_store._build_schema()

        field_names = [f["name"] for f in captured.get("fields", [])]
        assert "embedding" in field_names
        assert "entity_type" in field_names
        assert "entity_id" in field_names
        assert "text" in field_names
        assert "timestamp" in field_names
        assert "metadata" in field_names

    def test_make_key(self, vector_store, mock_settings):
        """Key format should be {index_name}:{entity_type}:{entity_id}."""
        key = vector_store._make_key("trade", "abc123")
        assert key == "test_index:trade:abc123"

    @pytest.mark.asyncio
    async def test_add_document(self, vector_store):
        """Adding a document should store it in the index."""
        vector_store._initialized = True
        vector_store._index = MagicMock()
        vector_store._index.add_documents = MagicMock()

        embedding = [0.1] * 768
        key = await vector_store.add_document(
            entity_type="trade",
            entity_id="trade-001",
            embedding=embedding,
            text="Bought AAPL at $150",
            metadata={"symbol": "AAPL"},
        )

        assert key == "test_index:trade:trade-001"
        vector_store._index.add_documents.assert_called_once()
        call_args = vector_store._index.add_documents.call_args
        docs = call_args[0][0]
        assert len(docs) == 1
        assert docs[0]["entity_type"] == "trade"
        assert docs[0]["entity_id"] == "trade-001"
        assert docs[0]["text"] == "Bought AAPL at $150"
        assert docs[0]["embedding"] == embedding
        # metadata is JSON string
        assert json.loads(docs[0]["metadata"]) == {"symbol": "AAPL"}

    @pytest.mark.asyncio
    async def test_add_documents_batch(self, vector_store):
        """Batch add should index all documents in one call."""
        vector_store._initialized = True
        vector_store._index = MagicMock()
        vector_store._index.add_documents = MagicMock()

        docs = [
            {
                "entity_type": "trade",
                "entity_id": "trade-001",
                "embedding": [0.1] * 768,
                "text": "Trade 1",
            },
            {
                "entity_type": "news",
                "entity_id": "news-001",
                "embedding": [0.2] * 768,
                "text": "News 1",
            },
        ]

        keys = await vector_store.add_documents(docs)

        assert len(keys) == 2
        assert "test_index:trade:trade-001" in keys
        assert "test_index:news:news-001" in keys

    @pytest.mark.asyncio
    async def test_search_no_filters(self, vector_store):
        """Search without filters returns all results above threshold."""
        vector_store._initialized = True
        vector_store._index = MagicMock()
        mock_results = [
            {
                "id": "test_index:trade:trade-001",
                "entity_type": "trade",
                "entity_id": "trade-001",
                "text": "Bought AAPL",
                "timestamp": datetime(2026, 1, 1).timestamp(),
                "metadata": json.dumps({"symbol": "AAPL"}),
                "vector_score": 0.95,
            },
            {
                "id": "test_index:trade:trade-002",
                "entity_type": "trade",
                "entity_id": "trade-002",
                "text": "Sold TSLA",
                "timestamp": datetime(2026, 2, 1).timestamp(),
                "metadata": json.dumps({"symbol": "TSLA"}),
                "vector_score": 0.85,
            },
        ]
        vector_store._index.query = MagicMock(return_value=mock_results)

        results = await vector_store.search(
            query_embedding=[0.1] * 768,
            min_similarity=0.5,
            top_k=10,
        )

        assert len(results) == 2
        assert results[0]["score"] == 0.95
        assert results[0]["entity_id"] == "trade-001"
        assert results[1]["score"] == 0.85

    @pytest.mark.asyncio
    async def test_search_min_similarity_filter(self, vector_store):
        """Results below min_similarity should be excluded."""
        vector_store._initialized = True
        vector_store._index = MagicMock()
        mock_results = [
            {
                "id": "k1",
                "entity_type": "trade",
                "entity_id": "trade-001",
                "text": "Trade 1",
                "timestamp": datetime(2026, 1, 1).timestamp(),
                "metadata": "{}",
                "vector_score": 0.95,
            },
            {
                "id": "k2",
                "entity_type": "trade",
                "entity_id": "trade-002",
                "text": "Trade 2",
                "timestamp": datetime(2026, 1, 1).timestamp(),
                "metadata": "{}",
                "vector_score": 0.3,  # below threshold
            },
        ]
        vector_store._index.query = MagicMock(return_value=mock_results)

        results = await vector_store.search(
            query_embedding=[0.1] * 768,
            min_similarity=0.5,
        )

        assert len(results) == 1
        assert results[0]["entity_id"] == "trade-001"

    @pytest.mark.asyncio
    async def test_search_entity_type_filter(self, vector_store):
        """Search with entity_type filter should include the tag filter."""
        vector_store._initialized = True
        vector_store._index = MagicMock()
        vector_store._index.query = MagicMock(return_value=[])

        await vector_store.search(
            query_embedding=[0.1] * 768,
            entity_type="trade",
        )

        assert vector_store._index.query.called
        call_kwargs = vector_store._index.query.call_args
        query_string = call_kwargs[1].get("query_string") or call_kwargs[0][1]
        assert "trade" in query_string

    @pytest.mark.asyncio
    async def test_search_date_filter(self, vector_store):
        """Search with date range should include timestamp filters."""
        vector_store._initialized = True
        vector_store._index = MagicMock()
        vector_store._index.query = MagicMock(return_value=[])

        date_from = datetime(2026, 1, 1)
        date_to = datetime(2026, 6, 1)

        await vector_store.search(
            query_embedding=[0.1] * 768,
            date_from=date_from,
            date_to=date_to,
        )

        assert vector_store._index.query.called
        call_kwargs = vector_store._index.query.call_args
        query_string = call_kwargs[1].get("query_string") or call_kwargs[0][1]
        assert "timestamp" in query_string

    @pytest.mark.asyncio
    async def test_delete_document(self, vector_store):
        """Delete should return True when document exists."""
        vector_store._initialized = True
        vector_store._index = MagicMock()
        vector_store._index.delete_document = MagicMock(return_value=1)

        deleted = await vector_store.delete_document("trade", "trade-001")
        assert deleted is True
        vector_store._index.delete_document.assert_called_with(
            "test_index:trade:trade-001"
        )

    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, vector_store):
        """Delete should return False when document doesn't exist."""
        vector_store._initialized = True
        vector_store._index = MagicMock()
        vector_store._index.delete_document = MagicMock(return_value=0)

        deleted = await vector_store.delete_document("trade", "nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_get_index_info(self, vector_store):
        """Index info should return doc count."""
        vector_store._initialized = True
        ft_mock = vector_store._redis.ft.return_value
        ft_mock.info.return_value = {"num_docs": 42}

        info = await vector_store.get_index_info()
        assert info["doc_count"] == 42
        assert info["index_name"] == "test_index"

    @pytest.mark.asyncio
    async def test_uninitialized_raises(self, vector_store):
        """Operations on uninitialized store should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await vector_store.add_document(
                entity_type="trade",
                entity_id="x",
                embedding=[0.1] * 768,
                text="test",
            )

        with pytest.raises(RuntimeError, match="not initialized"):
            await vector_store.search(query_embedding=[0.1] * 768)


def _make_async_mock(return_value):
    """Helper: create an AsyncMock that returns the given value."""
    mock = AsyncMock()
    mock.return_value = return_value
    return mock


class TestSearchRoutes:
    """Tests for search and indexing route endpoints."""

    @pytest.fixture
    def mock_vector_store(self):
        vs = MagicMock()
        vs.search = _make_async_mock([])
        vs.add_document = _make_async_mock("test_index:trade:t1")
        vs.add_documents = _make_async_mock(["k1", "k2"])
        vs.delete_document = _make_async_mock(True)
        vs.get_index_info = _make_async_mock(
            {"index_name": "embedding_index", "doc_count": 5}
        )
        return vs

    @pytest.fixture
    def client(self, mock_vector_store):
        from app.routes import search as search_routes

        search_routes._vector_store = mock_vector_store
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.include_router(search_routes.router)
        return TestClient(test_app)

    def test_search_endpoint(self, client, mock_vector_store):
        """POST /v1/search should return search results."""
        mock_vector_store.search = _make_async_mock(
            [
                {
                    "key": "embedding_index:trade:t1",
                    "entity_type": "trade",
                    "entity_id": "t1",
                    "text": "Bought AAPL",
                    "score": 0.92,
                    "timestamp": datetime(2026, 1, 15),
                    "metadata": {"symbol": "AAPL"},
                }
            ]
        )

        response = client.post(
            "/v1/search",
            json={
                "query_embedding": [0.1] * 768,
                "min_similarity": 0.5,
                "top_k": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["entity_id"] == "t1"
        assert data["results"][0]["score"] == 0.92

    def test_search_with_entity_type_filter(self, client, mock_vector_store):
        """Search with entity_type filter."""
        mock_vector_store.search = _make_async_mock([])
        response = client.post(
            "/v1/search",
            json={
                "query_embedding": [0.1] * 768,
                "entity_type": "trade",
                "min_similarity": 0.5,
            },
        )

        assert response.status_code == 200
        call_args = mock_vector_store.search.call_args
        assert call_args[1]["entity_type"] == "trade"

    def test_search_with_date_range(self, client, mock_vector_store):
        """Search with date_from and date_to."""
        mock_vector_store.search = _make_async_mock([])
        response = client.post(
            "/v1/search",
            json={
                "query_embedding": [0.1] * 768,
                "date_from": "2026-01-01T00:00:00",
                "date_to": "2026-06-01T00:00:00",
            },
        )

        assert response.status_code == 200
        call_args = mock_vector_store.search.call_args
        assert call_args[1]["date_from"] is not None
        assert call_args[1]["date_to"] is not None

    def test_search_invalid_embedding_dimensions(self, client):
        """Search with wrong embedding dimensions should return 400."""
        response = client.post(
            "/v1/search",
            json={
                "query_embedding": [0.1, 0.2, 0.3],  # wrong size
            },
        )

        assert response.status_code == 400
        assert "dimensions" in response.json()["detail"]

    def test_search_invalid_date_format(self, client):
        """Search with invalid date format should return 400."""
        response = client.post(
            "/v1/search",
            json={
                "query_embedding": [0.1] * 768,
                "date_from": "not-a-date",
            },
        )

        assert response.status_code == 400

    def test_index_document(self, client, mock_vector_store):
        """POST /v1/index should index a single document."""
        mock_vector_store.add_document = _make_async_mock(
            "test_index:trade:trade-001"
        )
        response = client.post(
            "/v1/index",
            json={
                "entity_type": "trade",
                "entity_id": "trade-001",
                "embedding": [0.1] * 768,
                "text": "Bought AAPL at $150",
                "metadata": {"symbol": "AAPL"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "indexed"
        assert data["entity_type"] == "trade"
        assert data["entity_id"] == "trade-001"

    def test_index_document_wrong_dimensions(self, client):
        """Index with wrong embedding dimensions should return 400."""
        response = client.post(
            "/v1/index",
            json={
                "entity_type": "trade",
                "entity_id": "t1",
                "embedding": [0.1, 0.2],  # wrong size
                "text": "test",
            },
        )

        assert response.status_code == 400

    def test_index_document_invalid_timestamp(self, client):
        """Index with invalid timestamp should return 400."""
        response = client.post(
            "/v1/index",
            json={
                "entity_type": "trade",
                "entity_id": "t1",
                "embedding": [0.1] * 768,
                "text": "test",
                "timestamp": "not-a-date",
            },
        )

        assert response.status_code == 400

    def test_batch_index(self, client, mock_vector_store):
        """POST /v1/index/batch should index multiple documents."""
        mock_vector_store.add_documents = _make_async_mock(
            ["k1", "k2", "k3"]
        )
        docs = [
            {
                "entity_type": "trade",
                "entity_id": f"trade-{i}",
                "embedding": [float(i)] * 768,
                "text": f"Trade {i}",
            }
            for i in range(3)
        ]

        response = client.post(
            "/v1/index/batch",
            json={"documents": docs},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["indexed"]) == 3

    def test_batch_index_too_large(self, client):
        """Batch exceeding 500 documents should return 400."""
        docs = [
            {
                "entity_type": "trade",
                "entity_id": f"trade-{i}",
                "embedding": [0.1] * 768,
                "text": f"Trade {i}",
            }
            for i in range(501)
        ]

        response = client.post(
            "/v1/index/batch",
            json={"documents": docs},
        )

        assert response.status_code == 400
        assert "exceeds maximum" in response.json()["detail"]

    def test_delete_document(self, client, mock_vector_store):
        """DELETE /v1/index/{type}/{id} should remove a document."""
        mock_vector_store.delete_document = _make_async_mock(True)
        response = client.delete("/v1/index/trade/trade-001")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

    def test_delete_document_not_found(self, client, mock_vector_store):
        """Delete non-existent document should return 404."""
        mock_vector_store.delete_document = _make_async_mock(False)
        response = client.delete("/v1/index/trade/nonexistent")

        assert response.status_code == 404

    def test_index_stats(self, client, mock_vector_store):
        """GET /v1/index/stats should return index statistics."""
        mock_vector_store.get_index_info = _make_async_mock(
            {"index_name": "embedding_index", "doc_count": 5}
        )
        response = client.get("/v1/index/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["index_name"] == "embedding_index"
        assert data["doc_count"] == 5

    def test_uninitialized_vector_store(self):
        """Endpoints should return 503 when vector store is not initialized."""
        from app.routes import search as search_routes
        from fastapi import FastAPI

        saved = search_routes._vector_store
        search_routes._vector_store = None

        test_app = FastAPI()
        test_app.include_router(search_routes.router)
        client = TestClient(test_app)

        try:
            response = client.post(
                "/v1/search",
                json={"query_embedding": [0.1] * 768},
            )
            assert response.status_code == 503
        finally:
            search_routes._vector_store = saved
