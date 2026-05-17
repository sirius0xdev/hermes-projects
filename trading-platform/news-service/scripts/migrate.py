#!/usr/bin/env python
"""Database migration script.

Creates the signal_analysis table (our contribution).
Reads and validates the existing scraper tables already exist.

Usage:
    python scripts/migrate.py
    python scripts/migrate.py --db-url postgresql+asyncpg://user:pass@host:5432/news
"""

import asyncio
import sys
import argparse
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CREATE_SIGNAL_ANALYSIS_SQL = """
CREATE TABLE IF NOT EXISTS signal_analysis (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    article_id INTEGER NOT NULL UNIQUE REFERENCES articles(id) ON DELETE CASCADE,
    sentiment_score FLOAT NOT NULL,
    sentiment_label VARCHAR(20) NOT NULL,
    sentiment_confidence FLOAT,
    market_signals VARCHAR(512),
    market_impact_score FLOAT,
    mentioned_tickers VARCHAR(512),
    key_phrases TEXT,
    named_entities TEXT,
    model_version VARCHAR(50) NOT NULL DEFAULT 'v1',
    analyzed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_sentiment_score ON signal_analysis(sentiment_score);
CREATE INDEX IF NOT EXISTS idx_analysis_market_signals ON signal_analysis(market_signals);
"""

VERIFY_SCRAPER_TABLES_SQL = """
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('articles', 'article_sources')
ORDER BY table_name;
"""

ADD_PROCESSED_COLUMN_SQL = """
ALTER TABLE articles 
ADD COLUMN IF NOT EXISTS processed BOOLEAN NOT NULL DEFAULT FALSE;
"""


async def run_migration(db_url: str):
    """Run database migrations."""
    logger.info(f"Connecting to {db_url.split('@')[-1] if '@' in db_url else db_url}")
    
    engine = create_async_engine(db_url)
    
    try:
        async with engine.connect() as conn:
            # Step 1: Verify scraper tables exist
            logger.info("Step 1: Verifying existing scraper tables...")
            result = await conn.execute(text(VERIFY_SCRAPER_TABLES_SQL))
            existing = [row[0] for row in result.fetchall()]
            
            if "articles" not in existing or "article_sources" not in existing:
                logger.error(
                    f"Missing scraper tables! Found: {existing}. "
                    "Expected: articles, article_sources. "
                    "Run the news scraper first."
                )
                sys.exit(1)
            logger.info(f"Found scraper tables: {existing}")
            
            # Step 2: Add processed column to articles if missing
            logger.info("Step 2: Adding processed column to articles...")
            await conn.execute(text(ADD_PROCESSED_COLUMN_SQL))
            await conn.commit()
            logger.info("Processed column added")
            
            # Step 3: Create signal_analysis table
            logger.info("Step 3: Creating signal_analysis table...")
            await conn.execute(text(CREATE_SIGNAL_ANALYSIS_SQL))
            await conn.commit()
            logger.info("signal_analysis table created")
            
            logger.info("Migration complete!")
            
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--db-url",
        help="Database URL (default: from env vars)",
    )
    args = parser.parse_args()
    
    if args.db_url:
        db_url = args.db_url
    else:
        import os
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "news")
        if password:
            db_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
        else:
            db_url = f"postgresql+asyncpg://{user}@{host}:{port}/{name}"
    
    asyncio.run(run_migration(db_url))


if __name__ == "__main__":
    main()
