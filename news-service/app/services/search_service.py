"""Search service — provides search endpoints for the News API.

Exposes hybrid keyword + semantic search through FastAPI.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.news.hybrid_search import HybridSearchManager

logger = logging.getLogger(__name__)


class SearchService:
    """Search service for financial news articles.

    Wraps HybridSearchManager with API-level error handling and validation.
    """

    def __init__(self, search_manager: Optional[HybridSearchManager] = None):
        self.manager = search_manager or HybridSearchManager()

    def search(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        symbol: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search news articles with hybrid keyword + semantic matching.

        Args:
            query: Search query string.
            page: Page number (1-based).
            page_size: Results per page.
            symbol: Optional ticker symbol filter.
            category: Optional category filter.

        Returns:
            Paginated search results dict.
        """
        if not query or not query.strip():
            return {
                "results": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "query": query,
            }

        result = self.manager.search(
            query=query.strip(),
            top_k=page_size * 3,  # Fetch extra for pagination
            symbol_filter=symbol,
            category_filter=category,
        )

        results = result["results"]

        # Paginate
        total = len(results)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = results[start:end]

        return {
            "results": paginated,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
            "query": query,
            "search_ms": result.get("search_ms"),
        }

    def search_by_symbols(
        self,
        query: str,
        symbols: List[str],
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """Search across multiple ticker symbols.

        Args:
            query: Search query string.
            symbols: List of ticker symbols.
            page: Page number (1-based).
            page_size: Results per page.

        Returns:
            Paginated search results dict.
        """
        result = self.manager.multi_symbol_search(
            query=query,
            symbols=symbols,
            top_k=page_size * 2,
        )

        results = result["results"]

        # Paginate
        total = len(results)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = results[start:end]

        return {
            "results": paginated,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
            "query": query,
            "symbols_searched": symbols,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get search engine stats."""
        return self.manager.get_stats()

    def health_check(self) -> Dict[str, Any]:
        """Check search health."""
        return self.manager.health_check()
