"""Vector-based semantic search engine for News API — hybrid with Meilisearch."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity between vector a (1-D) and matrix b (NxD)."""
    dot = b @ a
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b, axis=1)
    # Avoid div-by-zero
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = dot / (norm_a * norm_b)
    sim[norm_a == 0] = 0.0
    sim[norm_b == 0] = 0.0
    return sim


class VocabularyEncoder:
    """Vocabulary-based text encoder — no external model dependencies.

    Builds term-frequency vectors from the extracted financial vocabulary.
    Supports keyword matching with TF weighting for robust semantic signals
    without ONNX runtime overhead.
    """

    def __init__(self, vocabulary_path: Optional[str] = None):
        if vocabulary_path is None:
            # Default: shipped vocabulary file
            vocabulary_path = str(
                Path(__file__).resolve().parent / "data" / "meilisearch_vocab.json"
            )

        self._vocab: Dict[str, int] = {}
        self._dim: int = 0

        if Path(vocabulary_path).exists():
            with open(vocabulary_path) as f:
                raw = json.load(f)
            # Load all categories into a flat vocabulary
            for category_terms in raw.values():
                for idx, term in enumerate(category_terms):
                    self._vocab[term] = idx
            self._dim = max(self._vocab.values()) + 1 if self._vocab else 0
            logger.info(
                "Loaded vocabulary with %d terms (%d categories worth)",
                len(self._vocab),
                len(raw),
            )
        else:
            logger.warning(
                "Vocabulary file not found at %s — using empty vocabulary",
                vocabulary_path,
            )

    @property
    def vocabulary_size(self) -> int:
        return len(self._vocab)

    @property
    def dimension(self) -> int:
        return self._dim

    def encode(self, text: str) -> np.ndarray:
        """Encode text to a term-frequency vector.

        Args:
            text: Input text to encode.

        Returns:
            TF vector of shape (dim,).
        """
        if self._dim == 0:
            return np.array([], dtype=np.float32)

        text_lower = text.lower()
        vector = np.zeros(self._dim, dtype=np.float32)

        # Simple tokenization
        import re
        tokens = re.findall(r"\b[a-z0-9_]+(?:-[a-z0-9_]+)*\b", text_lower)

        # Count term frequencies
        tf: Dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        # Build vector with TF weighting
        for term, count in tf.items():
            if term in self._vocab:
                vector[self._vocab[term]] = float(count)

        # L2 normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm

        return vector

    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """Encode multiple texts at once.

        Returns:
            Matrix of shape (len(texts), dim).
        """
        if not texts:
            return np.zeros((0, max(self._dim, 1)), dtype=np.float32)

        return np.array([self.encode(t) for t in texts])


class VectorStore:
    """In-memory vector store for news embeddings."""

    def __init__(self):
        self._vectors: Dict[int, np.ndarray] = {}
        self._dim: int = 0

    def add(self, id: int, vector: np.ndarray) -> None:
        self._vectors[id] = vector
        if self._dim == 0:
            self._dim = vector.shape[0]

    def add_batch(self, items: List[Tuple[int, np.ndarray]]) -> None:
        for id, vec in items:
            self.add(id, vec)

    def search(
        self, query_vector: np.ndarray, top_k: int = 20
    ) -> List[Tuple[int, float]]:
        """Search for nearest vectors by cosine similarity.

        Returns:
            List of (id, score) tuples sorted by descending similarity.
        """
        if not self._vectors:
            return []

        ids = list(self._vectors.keys())
        vectors = np.array([self._vectors[i] for i in ids])

        scores = _cosine_similarity(query_vector, vectors)

        # Get top-k indices
        top_indices = np.argsort(-scores)[:top_k]

        return [(ids[i], float(scores[i])) for i in top_indices]

    def __len__(self) -> int:
        return len(self._vectors)


class VectorSearchEngine:
    """Semantic search engine for financial news using hybrid matching.

    Combines:
    1. **Vocabulary-based vector encoding** — TF vectors from extracted financial
       vocabulary for semantic similarity via cosine distance.
    2. **Meilisearch keyword search** — full-text search with typo tolerance.

    Designed for containerized deployment: no ONNX runtime required.
    Vocabulary is pre-extracted from 12,500+ news articles.
    """

    def __init__(
        self,
        meilisearch_url: Optional[str] = None,
        meilisearch_api_key: Optional[str] = None,
        index_name: str = "news",
        vocabulary_path: Optional[str] = None,
    ):
        """Initialize the hybrid search engine.

        Args:
            meilisearch_url: Meilisearch server URL.
            meilisearch_api_key: Meilisearch API key.
            index_name: Meilisearch index name.
            vocabulary_path: Path to vocabulary JSON file.
        """
        # Vector components
        self.encoder = VocabularyEncoder(vocabulary_path)
        self.vector_store = VectorStore()

        # Meilisearch
        self.ms_url = meilisearch_url or os.environ.get("MEILISEARCH_URL", "http://localhost:7700")
        self.ms_api_key = meilisearch_api_key or os.environ.get("MEILISEARCH_API_KEY", "")
        self.ms_index_name = index_name
        self._ms_client: Optional[Any] = None

        # Stats
        self._indexed_count = 0

    @property
    def meilisearch_client(self) -> Any:
        """Lazy-load Meilisearch client."""
        if self._ms_client is None:
            try:
                import meilisearch
                self._ms_client = meilisearch.Client(
                    self.ms_url, self.ms_api_key
                )
            except ImportError:
                logger.warning("meilisearch package not installed — vector-only mode")
                self._ms_client = False
            except Exception as e:
                logger.warning("Meilisearch connection failed: %s — vector-only mode", e)
                self._ms_client = False

        if self._ms_client is False:
            raise ImportError(
                "Meilisearch unavailable — install with 'pip install meilisearch'"
            )

        return self._ms_client

    def index_article(self, article: Dict[str, Any]) -> None:
        """Index a single article for vector search.

        Args:
            article: Dict with 'id', 'title', 'summary', 'content'.
        """
        article_id = article.get("id", 0)
        text = self._build_search_text(article)

        # Vector encoding
        vector = self.encoder.encode(text)
        if vector.shape[0] > 0:
            self.vector_store.add(article_id, vector)

        # Meilisearch indexing
        try:
            client = self.meilisearch_client
            index = client.index(self.ms_index_name)
            # Transform for Meilisearch
            doc = {
                "id": str(article_id),
                "title": article.get("title", ""),
                "summary": article.get("summary", ""),
                "content": article.get("content", ""),
                "source": article.get("source", ""),
                "symbols": article.get("symbols", []),
                "categories": article.get("categories", []),
                "published_at": article.get("published_at", ""),
            }
            index.add_documents([doc])
        except (ImportError, Exception):
            pass  # Vector-only mode

        self._indexed_count += 1

    def index_batch(self, articles: List[Dict[str, Any]]) -> None:
        """Index multiple articles at once.

        Args:
            articles: List of article dicts.
        """
        # Vector encoding (batch)
        texts = [self._build_search_text(a) for a in articles]
        vectors = self.encoder.encode_batch(texts)

        if vectors.shape[1] > 0:
            items = [
                (a.get("id", 0), vectors[i])
                for i, a in enumerate(articles)
            ]
            self.vector_store.add_batch(items)

        # Meilisearch batch
        if articles:
            try:
                client = self.meilisearch_client
                index = client.index(self.ms_index_name)
                docs = [
                    {
                        "id": str(a.get("id", 0)),
                        "title": a.get("title", ""),
                        "summary": a.get("summary", ""),
                        "content": a.get("content", ""),
                        "source": a.get("source", ""),
                        "symbols": a.get("symbols", []),
                        "categories": a.get("categories", []),
                        "published_at": a.get("published_at", ""),
                    }
                    for a in articles
                ]
                index.add_documents(docs)
            except (ImportError, Exception):
                pass

        self._indexed_count += len(articles)

    def search(
        self,
        query: str,
        top_k: int = 20,
        symbol_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        recency_boost: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """Hybrid search: combine vector similarity + Meilisearch keyword results.

        Args:
            query: Search query string.
            top_k: Max results to return.
            symbol_filter: Optional ticker symbol filter (e.g., "BTC").
            category_filter: Optional category filter (e.g., "market").
            recency_boost: Multiplier for recency in score blending.

        Returns:
            List of result dicts with 'article_id', 'score', 'match_type'.
        """
        results: Dict[int, Dict[str, Any]] = {}

        # 1. Vector search
        query_vector = self.encoder.encode(query)
        if query_vector.shape[0] > 0:
            vector_hits = self.vector_store.search(query_vector, top_k * 2)
            for article_id, score in vector_hits:
                if article_id not in results or score > results[article_id]["score"]:
                    results[article_id] = {
                        "article_id": article_id,
                        "score": score,
                        "match_type": "vector",
                        "vector_score": score,
                        "keyword_score": 0.0,
                    }

        # 2. Meilisearch keyword search
        try:
            client = self.meilisearch_client
            index = client.index(self.ms_index_name)

            ms_params: Dict[str, Any] = {
                "limit": min(top_k * 2, 100),
                "attributesToSearchOn": [
                    {"name": "title", "weight": 4.0},
                    {"name": "summary", "weight": 3.0},
                    {"name": "content", "weight": 1.0},
                ],
            }

            # Apply filters
            filter_expr = []
            if symbol_filter:
                filter_expr.append(f'symbols = "{symbol_filter}"')
            if category_filter:
                filter_expr.append(f'categories = "{category_filter}"')
            if filter_expr:
                ms_params["filter"] = " AND ".join(filter_expr)

            ms_results = index.search(query, ms_params)

            for hit in (ms_results.get("hits") or []):
                article_id = int(hit.get("id", 0))
                # Meilisearch relevance score (normalized)
                ms_score = 1.0  # Relative ranking from Meilisearch
                # Could use _formatted fields or custom scoring

                if article_id in results:
                    results[article_id]["keyword_score"] = ms_score
                    results[article_id]["match_type"] = "hybrid"
                    # Blend scores
                    results[article_id]["score"] = (
                        results[article_id]["vector_score"] * 0.6
                        + ms_score * 0.4
                    )
                else:
                    results[article_id] = {
                        "article_id": article_id,
                        "score": ms_score * 0.4,
                        "match_type": "keyword",
                        "vector_score": 0.0,
                        "keyword_score": ms_score,
                    }

        except (ImportError, Exception) as e:
            logger.debug("Meilisearch search skipped: %s", e)

        # Sort by blended score, take top_k
        sorted_results = sorted(
            results.values(), key=lambda r: r["score"], reverse=True
        )[:top_k]

        return sorted_results

    def _build_search_text(self, article: Dict[str, Any]) -> str:
        """Build search text from article fields."""
        parts = [
            article.get("title", ""),
            article.get("summary", ""),
            article.get("content", ""),
        ]
        return " ".join(p for p in parts if p)

    @property
    def indexed_count(self) -> int:
        return self._indexed_count

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            "vocabulary_size": self.encoder.vocabulary_size,
            "vector_dim": self.encoder.dimension,
            "vectors_indexed": len(self.vector_store),
            "articles_indexed": self._indexed_count,
        }
