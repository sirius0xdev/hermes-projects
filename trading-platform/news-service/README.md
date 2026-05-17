# News Analyst Service

Microservice for the trading platform that ingests news articles from the customer1 CNPG (CloudNativePostgres) cluster, performs NLP analysis to extract market-moving signals, and exposes REST API endpoints for the dashboard.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ CNPG News   │     │ FastAPI      │     │ Dashboard   │
│ Database    │────▶│ News Service │────▶│ Frontend    │
│ (scraper    │     │ - REST API   │     │             │
│  writes)    │     │ - NLP        │     │             │
└─────────────┘     │ - Signals    │     └─────────────┘
       │            └──────────────┘
       │ Kafka              │
       ▼                    ▼
┌─────────────┐     ┌─────────────┐
│ articles    │────▶│ analysis    │
│ (raw)       │     │ (NLP done)  │
└─────────────┘     └─────────────┘
```

## Project Structure

```
news-service/
├── app/
│   ├── api/              # FastAPI route handlers
│   │   ├── articles.py   # CRUD + listing + ingest
│   │   ├── analysis.py   # Analysis results endpoints
│   │   └── signals.py    # Market signal summaries
│   ├── core/
│   │   ├── config.py     # Pydantic settings from env
│   │   └── database.py   # Async SQLAlchemy session
│   ├── kafka/
│   │   └── consumer.py   # Kafka article consumer
│   ├── models/
│   │   └── article.py    # SQLAlchemy ORM models
│   ├── schemas/
│   │   └── article.py    # Pydantic request/response
│   ├── services/
│   │   ├── nlp/
│   │   │   └── analyzer.py  # NLP pipeline
│   │   └── article_service.py  # Business logic
│   └── main.py           # FastAPI app factory
├── scripts/
│   ├── migrate.py        # DB migration (creates signal_analysis table)
│   └── seed_data.py      # Sample data for local development
├── tests/
│   ├── test_nlp_analyzer.py
│   └── test_service.py
├── Dockerfile
├── requirements.txt
└── README.md
```

## API Endpoints (base: /api/v1)

### Articles
- `GET /articles/` — List articles with pagination and filters
  - Query params: `page`, `page_size`, `sentiment_filter`, `ticker`, `source_id`, `processed`, `since`, `until`
- `GET /articles/{id}` — Get single article with full detail and analysis
- `POST /articles/` — Create article (auto-triggers NLP analysis)
- `POST /articles/analyze-unprocessed` — Batch analyze unprocessed articles

### Analysis
- `GET /analysis/` — List all analysis results with pagination and filters
  - Query params: `page`, `page_size`, `sentiment_filter`, `min_impact`
- `GET /analysis/{article_id}` — Get analysis for a specific article

### Signals
- `GET /signals/summary` — Aggregated market signal summary for dashboard
  - Query params: `hours` (timeframe, default 24)

### Health
- `GET /health` — Service health check
- `GET /health/db` — Database connectivity check

## NLP Analysis Pipeline

For each article, the service extracts:

| Field | Description |
|---|---|
| `sentiment_score` | -1.0 (very negative) to +1.0 (very positive) |
| `sentiment_label` | positive / negative / neutral |
| `sentiment_confidence` | Model confidence (0.0 to 1.0) |
| `market_signals` | Signal categories: bull_run, crash_risk, regulation, earnings, macro, defi, partnership, security |
| `market_impact_score` | 0.0 (noise) to 1.0 (high impact) |
| `mentioned_tickers` | Comma-separated tickers (stocks + crypto) |
| `key_phrases` | Noun phrases extracted from text |
| `named_entities` | Companies, organizations, people mentioned |

## Database Schema

### Read from scraper (CNPG news DB)
- `article_sources` — Source metadata (id, name, url, category, language)
- `articles` — Scraped articles (id, title, content, url, published_at, etc.)

### Written by news service
- `signal_analysis` — NLP results (id, article_id FK, sentiment fields, market signals, tickers)

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | customer1-cnpg | CNPG cluster hostname |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | news | Database name |
| `DB_USER` | postgres | DB user |
| `DB_PASSWORD` | (empty) | DB password |
| `DB_POOL_SIZE` | 5 | Connection pool size |
| `KAFKA_BOOTSTRAP_SERVERS` | localhost:9092 | Kafka brokers |
| `KAFKA_GROUP_ID` | news-analyzer | Consumer group |
| `KAFKA_TOPIC_ARTICLES` | news.articles | Input topic |
| `KAFKA_TOPIC_ANALYSIS` | news.analysis | Output topic |

## Running

### Docker Compose
```bash
cd trading-platform
docker compose -f docker-compose.news.yml up -d
```

### Local development
```bash
cd news-service
pip install -r requirements.txt
python -m textblob.download_corpora  # NLTK data
uvicorn app.main:app --reload
```

### Migration + Seed
```bash
python scripts/migrate.py --db-url postgresql+asyncpg://user:pass@host:5432/news
python scripts/seed_data.py --db-url postgresql+asyncpg://user:pass@host:5432/news
```

### Tests
```bash
cd news-service
pip install pytest pytest-asyncio
pytest tests/ -v
```

## Integration Points

- **CNPG Cluster**: Read-only access to scraper tables, write to signal_analysis
- **Kafka**: Consumes `news.articles`, produces `news.analysis`
- **Dashboard**: Frontend consumes /api/v1/signals/summary for the news feed widget
