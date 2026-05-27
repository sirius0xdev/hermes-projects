"""Read-only model for scraper articles in news_app_db.

This model maps the simplified articles table written by the news_bot
Scrapy pipeline. It lives on a separate database (news_app_db) and is
accessed via the secondary DB connection (news_db).

Schema:
    articles (
      id SERIAL PRIMARY KEY,
      title TEXT,
      url TEXT UNIQUE,
      content TEXT,
      domain TEXT,
      timestamp TIMESTAMPTZ
    )
"""

from datetime import datetime
from sqlalchemy import Column, Integer, Text, String, DateTime
from sqlalchemy.orm import declarative_base

NewsBase = declarative_base()


class ScrapedArticle(NewsBase):
    """Read-only model for articles scraped by news_bot."""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    url = Column(Text, unique=True, nullable=False)
    content = Column(Text, nullable=True)
    domain = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
