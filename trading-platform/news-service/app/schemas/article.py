"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ----- Articles -----

class ArticleBase(BaseModel):
    title: str = Field(..., max_length=1024)
    url: str = Field(..., max_length=2048)
    content: Optional[str] = None
    summary: Optional[str] = None
    author: Optional[str] = None
    source_id: Optional[int] = None
    language: str = "en"
    tags: Optional[str] = None
    tickers: Optional[str] = None
    published_at: Optional[datetime] = None


class ArticleCreate(ArticleBase):
    """Schema for creating a new article (ingest endpoint)."""
    raw_text: Optional[str] = None


class ArticleResponse(ArticleBase):
    id: int
    scraped_at: datetime
    processed: bool
    analysis: Optional["AnalysisResponse"] = None

    model_config = {"from_attributes": True}


class ArticleListItem(BaseModel):
    """Compact article info for list endpoints."""
    id: int
    title: str
    url: str
    source_id: Optional[int]
    published_at: Optional[datetime]
    scraped_at: datetime
    processed: bool
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    mentioned_tickers: Optional[str] = None
    market_impact_score: Optional[float] = None

    model_config = {"from_attributes": True}


# ----- Analysis -----

class SignalAnalysisCreate(BaseModel):
    article_id: int
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)
    sentiment_label: str
    sentiment_confidence: Optional[float] = None
    market_signals: Optional[str] = None
    market_impact_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    mentioned_tickers: Optional[str] = None
    key_phrases: Optional[str] = None
    named_entities: Optional[str] = None
    model_version: str = "v1"


class AnalysisResponse(BaseModel):
    id: int
    article_id: int
    sentiment_score: float
    sentiment_label: str
    sentiment_confidence: Optional[float]
    market_signals: Optional[str]
    market_impact_score: Optional[float]
    mentioned_tickers: Optional[str]
    key_phrases: Optional[str]
    named_entities: Optional[str]
    model_version: str
    analyzed_at: datetime

    model_config = {"from_attributes": True}


# ----- Sources -----

class SourceResponse(BaseModel):
    id: int
    name: str
    url: str
    category: Optional[str]
    language: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Trading Signals -----

class SignalSummary(BaseModel):
    """Aggregated market signal summary for dashboard."""
    total_articles: int
    positive_count: int
    negative_count: int
    neutral_count: int
    avg_sentiment: float
    high_impact_articles: int  # market_impact_score >= threshold
    top_tickers: list[dict]  # [{ticker: "AAPL", mention_count: 5, avg_sentiment: 0.3}]
    top_signals: list[dict]  # [{signal: "bull_run", count: 10}]
    timeframe: str  # human-readable like "last 24h"


# ----- Pagination -----

class ArticleListResponse(BaseModel):
    """Paginated list of articles."""
    items: list[ArticleListItem]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class AnalysisListResponse(BaseModel):
    """Paginated list of analysis results."""
    items: list[AnalysisResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


# ----- Scraped Articles (from news_bot / news_app_db) -----

class ScrapedArticleItem(BaseModel):
    """Compact scraped article from the news_bot scraper table."""
    id: int
    title: str
    url: str
    content: Optional[str] = None
    domain: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class ScrapedArticleListResponse(BaseModel):
    """Paginated list of scraped articles."""
    items: list[ScrapedArticleItem]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool
