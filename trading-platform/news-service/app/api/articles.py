"""API routes for article CRUD and listing, and analyst summaries."""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import db, news_db
from app.models.news_article import ScrapedArticle
from app.models.article import ArticleSummary
from app.schemas.article import (
    ArticleCreate,
    ArticleResponse,
    ArticleListItem,
    ArticleListResponse,
    ScrapedArticleItem,
    ScrapedArticleListResponse,
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


async def _get_news_db() -> AsyncSession:
    """FastAPI dependency to get a session for the secondary news_app_db."""
    async for session in news_db.get_session():
        yield session


@router.get("/scraped", response_model=ScrapedArticleListResponse)
async def list_scraped_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    domain: Optional[str] = Query(None, description="Filter by domain (e.g. reuters.com)"),
    since: Optional[datetime] = Query(None, description="Filter articles after this timestamp"),
    until: Optional[datetime] = Query(None, description="Filter articles before this timestamp"),
    session: AsyncSession = Depends(_get_news_db),
):
    """List articles scraped by the news_bot pipeline.

    These are raw articles from the secondary news_app_db — not yet
    processed by the NLP pipeline. Read-only endpoint.
    """
    conditions = [ScrapedArticle.timestamp.isnot(None)]
    if domain:
        conditions.append(ScrapedArticle.domain == domain)
    if since:
        conditions.append(ScrapedArticle.timestamp >= since)
    if until:
        conditions.append(ScrapedArticle.timestamp <= until)

    # Count total
    count_q = select(func.count()).select_from(ScrapedArticle).where(*conditions)
    total = (await session.execute(count_q)).scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    q = (
        select(ScrapedArticle)
        .where(*conditions)
        .order_by(ScrapedArticle.timestamp.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await session.execute(q)).scalars().all()

    has_next = (page * page_size) < total
    has_prev = page > 1

    return ScrapedArticleListResponse(
        items=[
            ScrapedArticleItem(
                id=a.id,
                title=a.title,
                url=a.url,
                content=a.content,
                domain=a.domain,
                timestamp=a.timestamp,
            )
            for a in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
        has_prev=has_prev,
    )


# ── Pydantic response models for summaries ─────────────────────────

def _summary_dict(s) -> dict:
    """ORM row → plain dict."""
    return {
        "id": s.id,
        "summary_text": s.summary_text,
        "is_master_summary": s.is_master_summary,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _summary_list_dict(s) -> dict:
    """ORM row → list-view dict (no full text)."""
    return {
        "id": s.id,
        "is_master_summary": s.is_master_summary,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "preview": s.summary_text[:200] if s.summary_text else "",
    }


# ── Summary endpoints ──────────────────────────────────────────────

@router.get("/summaries/latest", response_model=dict)
async def get_latest_summary(
    session: AsyncSession = Depends(_get_db),
):
    """Return the most recent analyst summary."""
    stmt = (
        select(ArticleSummary)
        .order_by(ArticleSummary.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=404, detail="No summaries found")
    return _summary_dict(summary)


@router.get("/summaries", response_model=dict)
async def list_summaries(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    since: Optional[datetime] = Query(None, description="Only summaries created after this timestamp"),
    session: AsyncSession = Depends(_get_db),
):
    """List analyst summaries with pagination (newest first)."""
    stmt = select(ArticleSummary).order_by(ArticleSummary.created_at.desc())
    count_stmt = select(func.count(ArticleSummary.id)).select_from(ArticleSummary)

    if since:
        stmt = stmt.where(ArticleSummary.created_at >= since)
        count_stmt = count_stmt.where(ArticleSummary.created_at >= since)

    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    stmt = stmt.offset(offset).limit(per_page)
    result = await session.execute(stmt)
    items = result.scalars().all()

    return {
        "items": [_summary_list_dict(s) for s in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "has_next": (page * per_page) < total,
        "has_prev": page > 1,
    }


@router.get("/summaries/{summary_id}", response_model=dict)
async def get_summary(
    summary_id: int,
    session: AsyncSession = Depends(_get_db),
):
    """Return a specific analyst summary by ID."""
    stmt = select(ArticleSummary).where(ArticleSummary.id == summary_id)
    result = await session.execute(stmt)
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(
            status_code=404,
            detail=f"Summary with id {summary_id} not found"
        )
    return _summary_dict(summary)
