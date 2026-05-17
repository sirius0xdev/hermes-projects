"""API routes for article CRUD and listing."""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db
from app.schemas.article import (
    ArticleCreate,
    ArticleResponse,
    ArticleListItem,
    ArticleListResponse,
)
from app.services.article_service import (
    get_articles as _get_articles,
    get_article as _get_article,
    create_article as _create_article,
    run_analysis_on_unprocessed as _run_analysis,
)

router = APIRouter(prefix="/articles", tags=["articles"])


async def _get_db() -> AsyncSession:
    """FastAPI dependency to get a DB session."""
    async for session in db.get_session():
        yield session


def _build_response(article) -> Optional[ArticleResponse]:
    """ORM -> Pydantic conversion."""
    if article is None:
        return None
    return ArticleResponse(
        id=article.id,
        title=article.title,
        url=article.url,
        content=article.content,
        summary=article.summary,
        author=article.author,
        source_id=article.source_id,
        language=article.language,
        tags=article.tags,
        tickers=article.tickers,
        published_at=article.published_at,
        scraped_at=article.scraped_at,
        processed=article.processed,
        analysis=article.analysis,
    )


def _build_list_item(article) -> ArticleListItem:
    """ORM -> Pydantic list item conversion."""
    analysis = article.analysis
    return ArticleListItem(
        id=article.id,
        title=article.title,
        url=article.url,
        source_id=article.source_id,
        published_at=article.published_at,
        scraped_at=article.scraped_at,
        processed=article.processed,
        sentiment_label=analysis.sentiment_label if analysis else None,
        sentiment_score=analysis.sentiment_score if analysis else None,
        mentioned_tickers=analysis.mentioned_tickers if analysis else None,
        market_impact_score=analysis.market_impact_score if analysis else None,
    )


@router.get("/", response_model=ArticleListResponse)
async def list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sentiment_filter: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    source_id: Optional[int] = Query(None),
    processed: Optional[bool] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    session: AsyncSession = Depends(_get_db),
):
    """List articles with pagination and filters."""
    items, total = await _get_articles(
        db=session,
        page=page, page_size=page_size,
        sentiment_filter=sentiment_filter,
        ticker=ticker, source_id=source_id,
        processed=processed, since=since, until=until,
    )
    has_next = (page * page_size) < total
    has_prev = page > 1
    return ArticleListResponse(
        items=[_build_list_item(a) for a in items],
        total=total,
        page=page, page_size=page_size,
        has_next=has_next, has_prev=has_prev,
    )


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: int,
    session: AsyncSession = Depends(_get_db),
):
    """Get a single article with full detail and analysis."""
    article = await _get_article(session, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return _build_response(article)


@router.post("/", response_model=ArticleResponse, status_code=201)
async def create_article(
    article: ArticleCreate,
    session: AsyncSession = Depends(_get_db),
):
    """Create a new article. Automatically triggers NLP analysis."""
    created = await _create_article(session, article)
    await session.commit()
    return _build_response(created)


@router.post("/analyze-unprocessed", response_model=dict)
async def analyze_unprocessed(
    session: AsyncSession = Depends(_get_db),
):
    """Scan for unprocessed articles and run NLP analysis on them.
    
    Use this as a manual trigger or for backfilling analysis on
    articles that haven't been processed yet.
    """
    count = await _run_analysis(session)
    await session.commit()
    return {"processed_count": count}
