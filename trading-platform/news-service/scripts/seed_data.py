"""Seed data script for local development.

Creates sample articles, runs NLP analysis, and populates the DB
with realistic trading-related news for testing the API.

Usage:
    python scripts/seed_data.py
    python scripts/seed_data.py --db-url postgresql+asyncpg://...
    python scripts/seed_data.py --count 50
"""

import asyncio
import argparse
import logging
from datetime import datetime, timedelta
import random

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SAMPLE_ARTICLES = [
    {
        "title": "Fed Officials Signal Potential Rate Cut as Inflation Cools",
        "content": (
            "Federal Reserve officials indicated that a rate cut could come as soon as the next meeting, "
            "as inflation data shows consistent cooling. The CPI report came in below expectations at "
            "2.8%, down from 3.2% last quarter. Markets reacted positively, with S&P 500 futures "
            "rising 1.2%. Treasury yields fell across the curve. JPM and Goldman Sachs analysts "
            "raised their targets for rate cut probability to 75% for September."
        ),
        "tags": "fed,interest rates,inflation,macro",
        "source_trust": 1,
    },
    {
        "title": "BTC Surges Past $65K as ETF Inflows Hit Record $2.1 Billion",
        "content": (
            "Bitcoin broke through the $65,000 resistance level as spot BTC ETF inflows reached a "
            "record $2.1 billion in a single week. BlackRock's IBIT led the inflows with $890M. "
            "ETH also gained, rising 4.2% to $3,800. SOL and AVAX both posted double-digit gains. "
            "On-chain data shows whale accumulation accelerating, with addresses holding 10K+ BTC "
            "reaching new all-time highs."
        ),
        "tags": "bitcoin,etf,crypto,bull market",
        "source_trust": 1,
    },
    {
        "title": "SEC Launches Investigation into DeFi Protocol Over Unregistered Securities",
        "content": (
            "The SEC has opened a formal investigation into a major DeFi lending protocol for "
            "potentially offering unregistered securities. The protocol's governance token crashed "
            "25% on the news. Legal experts compare this to the Ripple case, but note that the "
            "decentralized nature could complicate enforcement. UNI and AAVE tokens fell 8% and "
            "6% respectively on regulatory fears."
        ),
        "tags": "sec,regulation,defi,governance",
        "source_trust": 2,
    },
    {
        "title": "AAPL Reports Record Q4 Revenue Driven by AI Features on iPhone 16",
        "content": (
            "Apple reported Q4 revenue of $98.2 billion, beating estimates of $94.5 billion. "
            "iPhone sales surged 12% year-over-year, driven by strong adoption of Apple Intelligence "
            "features on the iPhone 16. Services revenue grew 18%. CEO Tim Cook highlighted "
            "enterprise adoption of AI features. AAPL shares rose 4% in after-hours trading."
        ),
        "tags": "earnings,apple,ai,iphone",
        "source_trust": 1,
    },
    {
        "title": "Major Bank Warns of Recession Risk as Yield Curve Inverts Further",
        "content": (
            "A major Wall Street bank issued a recession warning after the yield curve between "
            "2-year and 10-year Treasuries inverted to -45 basis points, the deepest inversion "
            "in 18 months. The bank cut its GDP forecast from 1.8% to 0.5% for next year. "
            "Stocks declined broadly, with the DJIA down 2.1% and the NASDAQ falling 2.8%."
        ),
        "tags": "recession,yield curve,stocks,bear market",
        "source_trust": 1,
    },
    {
        "title": "NVIDIA Partners with Major Cloud Providers for AI Infrastructure Expansion",
        "content": (
            "NVIDIA announced expanded partnerships with AWS, Google Cloud, and Microsoft Azure "
            "to deploy next-generation H200 GPU clusters. The partnership aims to meet surging "
            "demand for AI training and inference workloads. NVDA is trading at new highs after "
            "analysts raised price targets citing accelerating data center revenue."
        ),
        "tags": "nvidia,ai,cloud,partnership",
        "source_trust": 1,
    },
    {
        "title": "SOL Network Experiences Outage During Peak Trading Volume",
        "content": (
            "The Solana blockchain experienced a 3-hour outage during peak trading volume, "
            "raising concerns about network reliability. SOL dropped 8% before validators "
            "coordinated a restart. DeFi protocols on Solana reported significant disruption. "
            "This is the third outage this year, though validator response time has improved."
        ),
        "tags": "solana,outage,defi,security",
        "source_trust": 2,
    },
    {
        "title": "Global Mining Stocks Rally on Copper Supply Disruption in Chile",
        "content": (
            "Copper prices surged 4.5% after major mining operations in Chile were halted "
            "due to labor strikes at two of the world's largest copper mines. FCX and SCCO "
            "shares rallied on the supply shock. Analysts note that copper is critical for "
            "EV infrastructure and grid expansion, making the disruption particularly impactful."
        ),
        "tags": "mining,copper,commodities,supply chain",
        "source_trust": 1,
    },
    {
        "title": "European Central Bank Announces Digital Euro Pilot Program",
        "content": (
            "The European Central Bank officially launched a pilot program for the digital euro, "
            "selecting 12 financial institutions to participate in the initial testing phase. "
            "The program will run for 12 months, exploring retail and wholesale use cases. "
            "EUR strengthened 0.8% against USD on the news, with markets viewing the digital "
            "euro as a step toward central bank digital currency adoption."
        ),
        "tags": "ecb,cbdc,digital euro,forex",
        "source_trust": 1,
    },
    {
        "title": "Tesla Misses Deliveries Estimate, Production Halted at Berlin Gigafactory",
        "content": (
            "Tesla reported Q3 deliveries of 435,000 vehicles, missing analyst estimates of "
            "454,000. The miss was attributed to supply chain disruptions at the Berlin "
            "Gigafactory, which temporarily halted production for 3 days. TSLA shares fell "
            "5.2% in after-hours trading. Analysts remain divided on whether this is a "
            "temporary setback or a longer-term production concern."
        ),
        "tags": "tesla,deliveries,production,earnings miss",
        "source_trust": 2,
    },
    {
        "title": "DeFi Total Value Locked Surpasses $100 Billion Milestone",
        "content": (
            "Total value locked in DeFi protocols crossed the $100 billion threshold for the "
            "first time since May 2022. Lido leads with $23B in staked ETH, followed by "
            "Aave at $12.8B and MakerDAO at $9.5B. The rally has been driven by yield "
            "opportunities, improved UX, and institutional adoption of liquid staking products. "
            "LDO tokens surged 15% on the milestone."
        ),
        "tags": "defi,TVL,staking,yield",
        "source_trust": 1,
    },
    {
        "title": "Oil Prices Drop 6% on Saudi Production Increase and China Demand Concerns",
        "content": (
            "Crude oil prices plummeted 6% after Saudi Arabia announced an unexpected increase "
            "in production. OPEC+ members are reportedly divided on production quotas. "
            "Compounding the sell-off, China's manufacturing PMI came in at 49.8, below the "
            "50 mark indicating contraction. USO and energy sector stocks declined sharply."
        ),
        "tags": "oil,OPEC,saudi arabia,China,commodities",
        "source_trust": 1,
    },
]


async def seed_articles(db_url: str, count: int | None = None):
    """Insert sample articles directly via SQLAlchemy for development."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy import text

    engine = create_async_engine(db_url, pool_pre_ping=True)

    # Sample scrape timestamps and publish dates
    articles_to_insert = SAMPLE_ARTICLES[:count] if count else SAMPLE_ARTICLES
    
    try:
        async with engine.begin() as conn:
            # Check if articles table exists
            result = await conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='article_sources')"
            ))
            has_sources = result.scalar()

            if not has_sources:
                # Create article_sources table for seed data
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS article_sources (
                        id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                        name VARCHAR(255) NOT NULL,
                        url VARCHAR(2048) NOT NULL,
                        category VARCHAR(100),
                        language VARCHAR(5) DEFAULT 'en',
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                # Insert default sources
                sources = [
                    ("Bloomberg", "https://bloomberg.com", "finance"),
                    ("CoinDesk", "https://coindesk.com", "crypto"),
                    ("Reuters", "https://reuters.com", "general"),
                    ("TechCrunch", "https://techcrunch.com", "technology"),
                ]
                for name, url, category in sources:
                    await conn.execute(text(
                        "INSERT INTO article_sources (name, url, category) VALUES (:name, :url, :cat)"
                    ), {"name": name, "url": url, "cat": category})
                logger.info("Created article_sources table with default data")

            # Check articles table
            result = await conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='articles')"
            ))
            has_articles = result.scalar()
            
            if not has_articles:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS articles (
                        id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                        title VARCHAR(1024) NOT NULL,
                        content TEXT,
                        summary TEXT,
                        url VARCHAR(2048) UNIQUE NOT NULL,
                        author VARCHAR(255),
                        source_id INTEGER REFERENCES article_sources(id),
                        language VARCHAR(5) DEFAULT 'en',
                        raw_text TEXT,
                        tags VARCHAR(512),
                        tickers VARCHAR(512),
                        published_at TIMESTAMP,
                        scraped_at TIMESTAMP DEFAULT NOW(),
                        processed BOOLEAN DEFAULT FALSE
                    )
                """))

            # Insert sample articles
            for i, article in enumerate(articles_to_insert):
                source_id = (i % 4) + 1
                published_at = datetime.utcnow() - timedelta(
                    days=random.randint(0, 14),
                    hours=random.randint(0, 23),
                )
                url = f"https://example.com/news/article-{i+1000}"

                await conn.execute(text("""
                    INSERT INTO articles (title, content, url, source_id, tags, published_at, processed)
                    VALUES (:title, :content, :url, :source_id, :tags, :published_at, FALSE)
                    ON CONFLICT (url) DO NOTHING
                """), {
                    "title": article["title"],
                    "content": article["content"],
                    "url": url,
                    "source_id": source_id,
                    "tags": article["tags"],
                    "published_at": published_at,
                    "run_analysis": False,
                })

            logger.info(f"Inserted {len(articles_to_insert)} sample articles")

        # Now run analysis on unprocessed
        async with AsyncSession(engine) as session:
            from app.services.article_service import run_analysis_on_unprocessed
            count_processed = await run_analysis_on_unprocessed(session)
            await session.commit()
            logger.info(f"Analyzed {count_processed} articles with NLP pipeline")

    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Seed DB with sample news articles")
    parser.add_argument("--db-url", help="Database URL")
    parser.add_argument("--count", type=int, default=None, help="Number of articles to insert")
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

    asyncio.run(seed_articles(db_url, args.count))


if __name__ == "__main__":
    main()
