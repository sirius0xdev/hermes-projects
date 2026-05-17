"""Tests for the article service layer."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_get_articles_basic(mock_session):
    with patch("app.services.article_service.select") as mock_select:
        mock_result = MagicMock()
        mock_result.scalars.return_value.unique.return_value.all.return_value = []
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_execute = AsyncMock()
        mock_execute.side_effect = [mock_count_result, mock_result]
        mock_session.execute = mock_execute

        from app.services.article_service import get_articles
        items, total = await get_articles(mock_session, page=1, page_size=20)

        assert total == 0
        assert items == []


def test_signal_aggregation_empty():
    """Test that signal summary works with no data."""
    from app.schemas.article import SignalSummary

    summary = SignalSummary(
        total_articles=0,
        positive_count=0,
        negative_count=0,
        neutral_count=0,
        avg_sentiment=0.0,
        high_impact_articles=0,
        top_tickers=[],
        top_signals=[],
        timeframe="last 24h",
    )
    assert summary.total_articles == 0
    assert summary.avg_sentiment == 0.0


def test_article_list_response_pagination():
    """Test pagination metadata."""
    from app.schemas.article import ArticleListResponse, ArticleListItem
    from datetime import datetime

    now = datetime.utcnow()
    items = [
        ArticleListItem(
            id=1, title="Test", url="http://test.com", source_id=1,
            published_at=now, scraped_at=now, processed=True,
        )
    ]
    response = ArticleListResponse(
        items=items, total=1, page=1, page_size=20,
        has_next=False, has_prev=False,
    )
    assert response.has_next is False
    assert response.has_prev is False
