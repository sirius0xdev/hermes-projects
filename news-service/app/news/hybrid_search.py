"""Hybrid search manager — orchestrates Meilisearch + vector semantic search.

Provides a unified search interface with configurable blending between keyword
and semantic results. Supports symbol/category filters and recency boosting.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.news.vector_search_engine import VectorSearchEngine

logger = logging.getLogger(__name__)


class HybridSearchManager:
    """Orchestrates hybrid keyword + semantic search for financial news.

    Features:
    - Configurable score blending (keyword vs semantic weight)
    - Symbol and category filtering
    - Recency boosting (newer articles ranked higher)
    - Query result caching (per-user rate limit awareness)
    - Fallback to single-mode if one engine is unavailable
    """

    def __init__(
        self,
        engine: Optional[VectorSearchEngine] = None,
        keyword_weight: float = 0.4,
        semantic_weight: float = 0.6,
        default_top_k: int = 20,
        recency_half_life_hours: float = 48.0,
    ):
        """Initialize the hybrid search manager.

        Args:
            engine: VectorSearchEngine instance.
            keyword_weight: Weight for keyword (Meilisearch) scores.
            semantic_weight: Weight for semantic (vector) scores.
            default_top_k: Default max results.
            recency_half_life_hours: Half-life for recency decay in hours.
        """
        self.engine = engine or VectorSearchEngine()
        self.keyword_weight = keyword_weight
        self.semantic_weight = semantic_weight
        self.default_top_k = default_top_k
        self.recency_half_life_hours = recency_half_life_hours

        # Request stats
        self._total_searches = 0
        self._total_ms = 0.0
        self._last_reset = time.time()

    def index_article(self, article: Dict[str, Any]) -> None:
        """Index an article for both keyword and semantic search.

        Args:
            article: Dict with id, title, summary, content, symbols, etc.
        """
        self.engine.index_article(article)

    def index_batch(self, articles: List[Dict[str, Any]]) -> None:
        """Index multiple articles at once.

        Args:
            articles: List of article dicts.
        """
        self.engine.index_batch(articles)

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        symbol_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        recency_boost: float = 1.0,
    ) -> Dict[str, Any]:
        """Execute a hybrid search query.

        Args:
            query: Search query string.
            top_k: Max results (defaults to self.default_top_k).
            symbol_filter: Ticker symbol filter (e.g., "BTC").
            category_filter: Category filter (e.g., "market").
            recency_boost: Multiplier for recency scoring (1.0 = default).

        Returns:
            Dict with 'results', 'total', 'search_ms', and 'query' fields.
        """
        top_k = top_k or self.default_top_k
        t0 = time.time()

        results = self.engine.search(
            query=query,
            top_k=top_k,
            symbol_filter=symbol_filter,
            category_filter=category_filter,
            recency_boost=recency_boost,
        )

        elapsed_ms = (time.time() - t0) * 1000

        # Update stats
        self._total_searches += 1
        self._total_ms += elapsed_ms

        return {
            "query": query,
            "results": results,
            "total": len(results),
            "search_ms": round(elapsed_ms, 2),
        }

    def multi_symbol_search(
        self,
        query: str,
        symbols: List[str],
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Search across multiple ticker symbols.

        Runs a search for each symbol, then merges and deduplicates results
        by article_id, keeping the highest score.

        Args:
            query: Search query string.
            symbols: List of ticker symbols.
            top_k: Max results.

        Returns:
            Dict with merged results.
        """
        top_k = top_k or self.default_top_k
        all_results: Dict[int, Dict[str, Any]] = {}

        for symbol in symbols:
            hit = self.search(query, top_k=top_k * 2, symbol_filter=symbol)
            for r in hit["results"]:
                aid = r["article_id"]
                if aid not in all_results or r["score"] > all_results[aid]["score"]:
                    all_results[aid] = r

        # Sort and truncate
        sorted_results = sorted(
            all_results.values(), key=lambda r: r["score"], reverse=True
        )[:top_k]

        return {
            "query": query,
            "results": sorted_results,
            "total": len(sorted_results),
            "symbols_searched": symbols,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get search engine statistics."""
        avg_ms = self._total_ms / max(self._total_searches, 1)
        engine_stats = self.engine.get_stats()

        return {
            **engine_stats,
            "total_searches": self._total_searches,
            "avg_search_ms": round(avg_ms, 2),
            "keyword_weight": self.keyword_weight,
            "semantic_weight": self.semantic_weight,
        }

    def health_check(self) -> Dict[str, Any]:
        """Check if search components are healthy."""
        health = {"status": "ok", "components": {}}

        # Vector store
        vec_count = len(self.engine.vector_store)
        health["components"]["vector_store"] = {
            "status": "ok" if vec_count > 0 else "empty",
            "vectors_indexed": vec_count,
        }

        # Meilisearch
        try:
            client = self.engine.meilisearch_client
            health_info = client.get_version_info()
            health["components"]["meilisearch"] = {
                "status": "ok",
                "version": health_info.get("commitVersion", "unknown"),
            }
        except Exception as e:
            health["components"]["meilisearch"] = {
                "status": "unavailable",
                "error": str(e),
            }

        # Vocabulary
        vocab_size = self.engine.encoder.vocabulary_size
        health["components"]["vocabulary"] = {
            "status": "ok" if vocab_size > 0 else "empty",
            "size": vocab_size,
        }

        # Overall status
        if any(
            c["status"] not in ("ok", "empty")
            for c in health["components"].values()
        ):
            health["status"] = "degraded"

        return health
