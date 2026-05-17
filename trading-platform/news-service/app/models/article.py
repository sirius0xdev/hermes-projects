"""Database models for the news service.

This mirrors the expected CNPG news database schema from the existing news scraper.
The scraper writes articles; we read them and add our own analysis.

Expected scraper tables (read-only from our perspective):
- articles: scraped news articles
- article_sources: metadata about sources

We also add:
- signal_analysis: our NLP analysis results per article
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, Boolean,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# ----- Scraper tables (read-only) -----

class ArticleSource(Base):
    """Source of scraped articles (managed by the scraper service)."""
    __tablename__ = "article_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)
    category = Column(String(100), nullable=True)
    language = Column(String(5), default="en")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    articles = relationship("Article", back_populates="source")


class Article(Base):
    """Scraped news articles from the CNPG news database."""
    __tablename__ = "articles"
    __table_args__ = (
        Index("idx_articles_published_at", "published_at"),
        Index("idx_articles_tickers", "tickers"),
        Index("idx_articles_source_id", "source_id"),
        Index("idx_articles_processed", "processed"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(1024), nullable=False)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    url = Column(String(2048), unique=True, nullable=False)
    author = Column(String(255), nullable=True)
    source_id = Column(Integer, ForeignKey("article_sources.id"), nullable=True)
    language = Column(String(5), default="en")
    
    # Raw scraped content
    raw_text = Column(Text, nullable=True, comment="Full raw scraped text")
    tags = Column(String(512), nullable=True, comment="Comma-separated tags from scraper")
    tickers = Column(String(512), nullable=True, comment="Comma-separated tickers extracted by scraper")
    
    # Timestamps
    published_at = Column(DateTime, nullable=True, comment="Article publish date")
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Processing state
    processed = Column(Boolean, default=False, nullable=False,
                       comment="Whether this article has been sent through NLP pipeline")
    
    analysis = relationship("SignalAnalysis", back_populates="article", uselist=False)
    source = relationship("ArticleSource", back_populates="articles")


# ----- Our analysis tables -----

class SignalAnalysis(Base):
    """NLP analysis results for articles. Written by the news analyzer."""
    __tablename__ = "signal_analysis"
    __table_args__ = (
        Index("idx_analysis_article_id", "article_id", unique=True),
        Index("idx_analysis_sentiment_score", "sentiment_score"),
        Index("idx_analysis_market_signals", "market_signals"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"), unique=True, nullable=False)
    
    # Sentiment
    sentiment_score = Column(Float, nullable=False,
                              comment="Combined sentiment score: -1.0 (very negative) to +1.0 (very positive)")
    sentiment_label = Column(String(20), nullable=False,
                              comment="positive / negative / neutral")
    sentiment_confidence = Column(Float, nullable=True,
                                   comment="Model confidence in sentiment prediction")
    
    # Market signals
    market_signals = Column(String(512), nullable=True,
                             comment="Comma-separated signal types: e.g., bull_run, crash_risk, regulation, earnings")
    market_impact_score = Column(Float, nullable=True,
                                  comment="Estimated market impact: 0.0 (noise) to 1.0 (high impact)")
    
    # Extracted entities
    mentioned_tickers = Column(String(512), nullable=True,
                                comment="Comma-separated tickers extracted by NLP")
    key_phrases = Column(Text, nullable=True,
                          comment="JSON array of key phrases extracted from article")
    named_entities = Column(Text, nullable=True,
                             comment="JSON array of named entities: companies, people, orgs")
    
    # Metadata
    model_version = Column(String(50), default="v1", nullable=False)
    analyzed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    article = relationship("Article", back_populates="analysis")
