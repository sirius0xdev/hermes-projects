"""CRUD and analysis service layer."""

from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.article import Article, SignalAnalysis, ArticleSource
from app.schemas.article import ArticleCreate
from app.services.nlp.analyzer import analyze_article as _nlp_analyze


async def get_articles(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    sentiment_filter: Optional[str] = None,
    ticker: Optional[str] = None,
    source_id: Optional[int] = None,
    processed: Optional[bool] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> tuple[list[Article], int]:
    """Fetch paginated articles with optional filters."""
    query = select(Article).options(
        selectinload(Article.analysis),
        selectinload(Article.source),
    )

    if sentiment_filter:
        query = query.join(SignalAnalysis).where(
            SignalAnalysis.sentiment_label == sentiment_filter
        )
    if ticker:
        query = query.where(Article.tickers.ilike(f"%{ticker}%"))
    if source_id:
        query = query.where(Article.source_id == source_id)
    if processed is not None:
        query = query.where(Article.processed == processed)
    if since:
        query = query.where(Article.published_at >= since)
    if until:
        query = query.where(Article.published_at <= until)

    query = query.order_by(Article.published_at.desc())

    # Count total
    count_query = select(func.count()).select_from(Article)
    # Apply same filters to count (without joins)
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    result = await db.execute(
        query.offset(offset).limit(page_size)
    )
    items = list(result.scalars().unique().all())
    return items, total


async def get_article(db: AsyncSession, article_id: int) -> Optional[Article]:
    """Fetch a single article with analysis and source."""
    query = select(Article).options(
        selectinload(Article.analysis),
        selectinload(Article.source),
    ).where(Article.id == article_id)
    result = await db.execute(query)
    return result.scalars().unique().first()


async def create_article(db: AsyncSession, article: ArticleCreate) -> Article:
    """Create a new article and trigger NLP analysis."""
    db_article = Article(
        title=article.title,
        content=article.content,
        summary=article.summary,
        url=article.url,
        author=article.author,
        source_id=article.source_id,
        language=article.language,
        tags=article.tags,
        tickers=article.tickers,
        published_at=article.published_at,
        raw_text=article.raw_text,
        processed=False,
    )
    db.add(db_article)
    await db.flush()

    # Run NLP analysis
    analysis = _nlp_analyze(
        title=article.title,
        content=article.content or "",
        source_trust=1,
    )
    sa = SignalAnalysis(
        article_id=db_article.id,
        **analysis,
    )
    db.add(sa)
    db_article.processed = True

    await db.flush()  # Keep session open for the caller to commit
    return db_article


async def run_analysis_on_unprocessed(db: AsyncSession) -> int:
    """Scan for unprocessed articles and run NLP analysis on them.
    
    Returns the number of articles processed.
    """
    query = select(Article).where(Article.processed == False).limit(500)
    result = await db.execute(query)
    articles = list(result.scalars().all())

    count = 0
    for article in articles:
        analysis = _nlp_analyze(
            title=article.title,
            content=article.content or article.raw_text or "",
            source_trust=1,
        )
        sa = SignalAnalysis(
            article_id=article.id,
            **analysis,
        )
        db.add(sa)
        article.processed = True
        count += 1

    await db.flush()
    return count


async def get_analysis(db: AsyncSession, article_id: int) -> Optional[SignalAnalysis]:
    """Get analysis for a specific article."""
    query = select(SignalAnalysis).where(
        SignalAnalysis.article_id == article_id
    )
    result = await db.execute(query)
    return result.scalars().first()


async def get_all_analysis(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    sentiment_filter: Optional[str] = None,
    min_impact: Optional[float] = None,
) -> tuple[list[SignalAnalysis], int]:
    """Fetch paginated analysis results."""
    query = select(SignalAnalysis).options(
        selectinload(SignalAnalysis.article),
    )
    if sentiment_filter:
        query = query.where(SignalAnalysis.sentiment_label == sentiment_filter)
    if min_impact is not None:
        query = query.where(SignalAnalysis.market_impact_score >= min_impact)
    
    query = query.order_by(SignalAnalysis.market_impact_score.desc())
    
    count_query = select(func.count()).select_from(SignalAnalysis)
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    items = list(result.scalars().unique().all())
    return items, total


async def get_signal_summary(
    db: AsyncSession,
    hours: int = 24,
) -> dict:
    """Generate aggregated market signal summary for the dashboard."""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # All analysis in timeframe
    query = select(SignalAnalysis).join(Article).where(
        Article.published_at >= since
    )
    result = await db.execute(query)
    analyses = list(result.scalars().all())

    total = len(analyses)
    positive = sum(1 for a in analyses if a.sentiment_label == "positive")
    negative = sum(1 for a in analyses if a.sentiment_label == "negative")
    neutral = sum(1 for a in analyses if a.sentiment_label == "neutral")
    
    avg_sentiment = (
        sum(a.sentiment_score for a in analyses) / total if total > 0 else 0.0
    )
    
    # High impact articles
    high_impact = sum(
        1 for a in analyses
        if a.market_impact_score and a.market_impact_score >= 0.5
    )

    # Top tickers
    ticker_counts = {}
    ticker_sentiments = {}
    for a in analyses:
        if a.mentioned_tickers:
            tickers = [t.strip() for t in a.mentioned_tickers.split(",")]
            for t in tickers:
                ticker_counts[t] = ticker_counts.get(t, 0) + 1
                ticker_sentiments.setdefault(t, []).append(a.sentiment_score)
    
    top_tickers = sorted(
        [
            {
                "ticker": t,
                "mention_count": c,
                "avg_sentiment": round(sum(ticker_sentiments[t]) / len(ticker_sentiments[t]), 3),
            }
            for t, c in ticker_counts.items()
        ],
        key=lambda x: x["mention_count"],
        reverse=True,
    )[:15]

    # Top signals
    signal_counts = {}
    for a in analyses:
        if a.market_signals:
            signals = [s.strip() for s in a.market_signals.split(",")]
            for s in signals:
                signal_counts[s] = signal_counts.get(s, 0) + 1
    
    top_signals = sorted(
        [{"signal": s, "count": c} for s, c in signal_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    return {
        "total_articles": total,
        "positive_count": positive,
        "negative_count": negative,
        "neutral_count": neutral,
        "avg_sentiment": round(avg_sentiment, 3),
        "high_impact_articles": high_impact,
        "top_tickers": top_tickers,
        "top_signals": top_signals,
        "timeframe": f"last {hours}h",
    }


async def get_sources(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ArticleSource], int]:
    """Fetch paginated sources."""
    query = select(ArticleSource).order_by(ArticleSource.name)
    count_query = select(func.count()).select_from(ArticleSource)
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    items = list(result.scalars().all())
    return items, total
