"""Search router — /search endpoint for hybrid keyword + semantic search."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# --- Models ---


class SearchRequest(BaseModel):
    """Search request model."""

    q: str = Field(..., min_length=1, max_length=500, description="Search query")
    page: int = Field(1, ge=1, description="Page number (1-based)")
    page_size: int = Field(
        20, ge=1, le=100, description="Results per page (max 100)"
    )
    symbol: Optional[str] = Field(None, description="Filter by ticker symbol")
    category: Optional[str] = Field(None, description="Filter by category")


class SearchResult(BaseModel):
    """Single search result."""

    article_id: int
    score: float
    match_type: str  # "vector", "keyword", or "hybrid"
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None


class SearchResponse(BaseModel):
    """Paginated search response."""

    results: List[SearchResult]
    total: int
    page: int
    page_size: int
    total_pages: int
    query: str
    search_ms: Optional[float] = None


class SearchStatsResponse(BaseModel):
    """Search engine statistics."""

    vocabulary_size: int
    vector_dim: int
    vectors_indexed: int
    articles_indexed: int
    total_searches: int
    avg_search_ms: float
    keyword_weight: float
    semantic_weight: float


class SearchHealthResponse(BaseModel):
    """Search health check response."""

    status: str
    components: dict


class MultiSymbolSearchRequest(BaseModel):
    """Multi-symbol search request."""

    q: str = Field(..., min_length=1, max_length=500)
    symbols: List[str] = Field(..., min_items=1, max_items=20)
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


# --- Dependency ---


def get_search_service() -> SearchService:
    """Get or create search service (singleton)."""
    if not hasattr(get_search_service, "_instance"):
        from app.news.hybrid_search import HybridSearchManager

        get_search_service._instance = SearchService(
            search_manager=HybridSearchManager()
        )
    return get_search_service._instance


# --- Routes ---


@router.post("/", response_model=SearchResponse, summary="Hybrid search")
async def search(
    req: SearchRequest,
    service: SearchService = Depends(get_search_service),
):
    """Search news articles with hybrid keyword + semantic matching.

    Combines Meilisearch full-text search with vector-based semantic similarity
    from extracted financial vocabulary. Results are blended and ranked.
    """
    result = service.search(
        query=req.q,
        page=req.page,
        page_size=req.page_size,
        symbol=req.symbol,
        category=req.category,
    )
    return SearchResponse(**result)


@router.post("/multi-symbol", summary="Multi-symbol search")
async def multi_symbol_search(
    req: MultiSymbolSearchRequest,
    service: SearchService = Depends(get_search_service),
):
    """Search across multiple ticker symbols.

    Runs search for each symbol, merges and deduplicates results.
    """
    result = service.search_by_symbols(
        query=req.q,
        symbols=req.symbols,
        page=req.page,
        page_size=req.page_size,
    )
    return result


@router.get("/stats", response_model=SearchStatsResponse, summary="Search stats")
async def search_stats(
    service: SearchService = Depends(get_search_service),
):
    """Get search engine statistics."""
    return SearchStatsResponse(**service.get_stats())


@router.get("/health", response_model=SearchHealthResponse, summary="Search health")
async def search_health(
    service: SearchService = Depends(get_search_service),
):
    """Check search components health."""
    return SearchHealthResponse(**service.health_check())
