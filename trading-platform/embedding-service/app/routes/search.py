"""
Semantic search and indexing endpoints for embedding-service.

Endpoints:
    POST /v1/search          — semantic search with filters
    POST /v1/index            — index a single document
    POST /v1/index/batch      — batch index multiple documents
    DELETE /v1/index/:type/:id — remove a document from the index
    GET  /v1/index/stats      — index statistics
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["vector-search"])

# Global vector store instance (initialized at startup)
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get the global vector store instance."""
    if _vector_store is None:
        raise HTTPException(
            status_code=503,
            detail="Vector store not initialized. Check Redis connectivity.",
        )
    return _vector_store


# --- Request/Response Models ---


class IndexDocumentRequest(BaseModel):
    entity_type: str = Field(
        ..., description="Entity type: 'trade', 'news', 'analysis', etc."
    )
    entity_id: str = Field(..., description="Unique identifier for this entity")
    embedding: list[float] = Field(
        ..., description="Normalized embedding vector (768 dimensions)"
    )
    text: str = Field(..., description="Original text content")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata fields"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp. Defaults to current UTC time.",
    )


class BatchIndexRequest(BaseModel):
    documents: list[IndexDocumentRequest] = Field(
        ..., description="Documents to index (max 500 per batch)"
    )


class SearchRequest(BaseModel):
    query_embedding: list[float] = Field(
        ..., description="Normalized query embedding (768 dimensions)"
    )
    entity_type: Optional[str] = Field(
        default=None,
        description="Filter by entity type (e.g. 'trade', 'news')",
    )
    date_from: Optional[str] = Field(
        default=None,
        description="Lower bound for timestamp (ISO 8601, inclusive)",
    )
    date_to: Optional[str] = Field(
        default=None,
        description="Upper bound for timestamp (ISO 8601, inclusive)",
    )
    min_similarity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity threshold (0-1)",
    )
    top_k: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum results to return (1-100)",
    )


class SearchResult(BaseModel):
    key: str
    entity_type: str
    entity_id: str
    text: str
    score: float
    timestamp: str
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int


class IndexResponse(BaseModel):
    key: str
    entity_type: str
    entity_id: str
    status: str = "indexed"


class BatchIndexResponse(BaseModel):
    indexed: list[dict[str, str]]
    total: int


class IndexStatsResponse(BaseModel):
    index_name: str
    doc_count: int


# --- Endpoints ---


@router.post("/index", response_model=IndexResponse)
async def index_document(req: IndexDocumentRequest):
    """Index a single document with its embedding.

    Stores the document in the Redis vector index for semantic search.
    If a document with the same (entity_type, entity_id) already exists,
    it is overwritten.
    """
    store = get_vector_store()

    ts = None
    if req.timestamp:
        try:
            ts = datetime.fromisoformat(req.timestamp)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timestamp format: {req.timestamp}. Use ISO 8601.",
            )

    # Validate embedding dimensions
    settings = Settings()
    if len(req.embedding) != settings.vector_index_dimensions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Embedding must have {settings.vector_index_dimensions} "
                f"dimensions, got {len(req.embedding)}"
            ),
        )

    key = await store.add_document(
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        embedding=req.embedding,
        text=req.text,
        metadata=req.metadata,
        timestamp=ts,
    )

    return IndexResponse(
        key=key,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        status="indexed",
    )


@router.post("/index/batch", response_model=BatchIndexResponse)
async def batch_index_documents(req: BatchIndexRequest):
    """Batch index multiple documents.

    More efficient than calling /v1/index repeatedly.
    Max 500 documents per batch.
    """
    if len(req.documents) > 500:
        raise HTTPException(
            status_code=400,
            detail="Batch size exceeds maximum (500 documents)",
        )

    store = get_vector_store()
    settings = Settings()

    # Validate all embeddings before indexing any
    for i, doc in enumerate(req.documents):
        if len(doc.embedding) != settings.vector_index_dimensions:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Document {i}: embedding must have "
                    f"{settings.vector_index_dimensions} dimensions, "
                    f"got {len(doc.embedding)}"
                ),
            )

    docs = []
    for doc in req.documents:
        ts = None
        if doc.timestamp:
            try:
                ts = datetime.fromisoformat(doc.timestamp)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid timestamp in document {doc.entity_id}",
                )

        docs.append(
            {
                "entity_type": doc.entity_type,
                "entity_id": doc.entity_id,
                "embedding": doc.embedding,
                "text": doc.text,
                "metadata": doc.metadata,
                "timestamp": ts,
            }
        )

    keys = await store.add_documents(docs)

    indexed = []
    for key, doc in zip(keys, req.documents):
        indexed.append(
            {
                "key": key,
                "entity_type": doc.entity_type,
                "entity_id": doc.entity_id,
            }
        )

    return BatchIndexResponse(indexed=indexed, total=len(indexed))


@router.post("/search", response_model=SearchResponse)
async def semantic_search(req: SearchRequest):
    """Semantic search against the vector index.

    Accepts a query embedding and optional filters, returns the most
    similar documents ranked by cosine similarity.
    """
    store = get_vector_store()
    settings = Settings()

    # Validate embedding dimensions
    if len(req.query_embedding) != settings.vector_index_dimensions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"query_embedding must have {settings.vector_index_dimensions} "
                f"dimensions, got {len(req.query_embedding)}"
            ),
        )

    # Parse date filters
    date_from = None
    date_to = None
    if req.date_from:
        try:
            date_from = datetime.fromisoformat(req.date_from)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date_from format: {req.date_from}. Use ISO 8601.",
            )
    if req.date_to:
        try:
            date_to = datetime.fromisoformat(req.date_to)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date_to format: {req.date_to}. Use ISO 8601.",
            )

    results = await store.search(
        query_embedding=req.query_embedding,
        entity_type=req.entity_type,
        date_from=date_from,
        date_to=date_to,
        min_similarity=req.min_similarity,
        top_k=req.top_k,
    )

    return SearchResponse(
        results=[
            SearchResult(
                key=r["key"],
                entity_type=r["entity_type"],
                entity_id=r["entity_id"],
                text=r["text"],
                score=r["score"],
                timestamp=r["timestamp"].isoformat(),
                metadata=r["metadata"],
            )
            for r in results
        ],
        total=len(results),
    )


@router.delete("/index/{entity_type}/{entity_id}")
async def delete_document(entity_type: str, entity_id: str) -> dict[str, str]:
    """Delete a document from the vector index."""
    store = get_vector_store()
    deleted = await store.delete_document(entity_type, entity_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {entity_type}/{entity_id}",
        )

    return {"status": "deleted", "entity_type": entity_type, "entity_id": entity_id}


@router.get("/index/stats", response_model=IndexStatsResponse)
async def index_stats():
    """Get vector index statistics."""
    store = get_vector_store()
    info = await store.get_index_info()
    return IndexStatsResponse(
        index_name=info["index_name"],
        doc_count=info["doc_count"],
    )
