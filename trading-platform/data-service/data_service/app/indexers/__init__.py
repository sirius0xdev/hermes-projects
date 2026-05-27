"""Indexer module — background indexers that feed the embedding service."""

from data_service.app.indexers.trade_indexer import TradeIndexer  # noqa: F401
from data_service.app.indexers.news_indexer import NewsIndexer  # noqa: F401

__all__ = ["TradeIndexer", "NewsIndexer"]
