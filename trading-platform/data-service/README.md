# Data Service

PostgreSQL schema, async database configuration, Alembic migrations, and Kafka event streaming for the trading platform.

## Infrastructure

This service runs on **Google Kubernetes Engine (GKE)**. Kubernetes manifests are in `kubernetes/`.

### Deploy to GKE

```bash
# 1. Deploy all infrastructure (namespace, Postgres, Redis, Kafka)
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/

# 2. Verify services are running
kubectl -n customer1 get pods
kubectl -n customer1 get svc

# 3. Port-forward for local access (optional)
kubectl -n customer1 port-forward svc/postgres 5432:5432 &
kubectl -n customer1 port-forward svc/redis 6379:6379 &
kubectl -n customer1 port-forward svc/kafka 9092:9092 &
```

### Teardown

```bash
kubectl delete -f kubernetes/
kubectl delete -f kubernetes/namespace.yaml
```

### Local Development

For local dev without a cluster, use the Docker Compose file:

```bash
docker compose -f data-service/docker-compose.yml up -d
```

## Quick Start

```bash
# 1. Start infrastructure (K8s or Docker Compose)
#    See Infrastructure section above

# 2. Install dependencies
cd data-service
pip install -e ".[dev]"

# 3. Run migrations
DATABASE_URL=postgresql+asyncpg://trading:trading@localhost:5432/trading_db \
  alembic -c alembic.ini upgrade head

# 4. (Optional) Verify schema
psql -h localhost -U trading -d trading_db -c "\dt"
```

## Directory Structure

```
data-service/
├── alembic/
│   ├── env.py                  # Alembic environment config
│   └── versions/
│       └── 001_initial_schema.py  # First migration
├── alembic.ini                  # Alembic configuration
├── app/
│   ├── __init__.py
│   ├── db/
│   │   ├── __init__.py          # Async engine, session factory, connection pooling
│   │   └── base.py              # SQLAlchemy declarative base
│   ├── models/
│   │   └── __init__.py          # Order, Position, Fill models
│   ├── cache/
│   │   ├── __init__.py          # Redis cache layer
│   │   ├── client.py            # Redis client setup
│   │   └── service.py           # Cache operations (prices, orderbook, candles)
│   └── kafka/
│       ├── __init__.py          # Public exports
│       ├── topics.py            # Topic name constants
│       ├── config.py            # Topic partition/retention config
│       ├── schemas.py           # Pydantic event schemas (price, orderbook, trade, news, signal)
│       ├── producer.py          # Kafka producer for all data types
│       ├── consumer.py          # Kafka consumer with handler registration
│       ├── ingester.py          # Market data ingester (yfinance -> Kafka)
│       └── setup_topics.py      # CLI tool to create all topics
├── kubernetes/                  # GKE deployment manifests
│   ├── README.md               # K8s deployment guide
│   ├── namespace.yaml          # customer1 namespace
│   ├── configmap.yaml          # Shared config values
│   ├── secrets.yaml            # Database credentials
│   ├── postgres/               # PostgreSQL StatefulSet + Service + PVC
│   ├── redis/                  # Redis StatefulSet + Service + PVC
│   └── kafka/                  # Kafka KRaft StatefulSet + Services + PVC
├── docker-compose.yml          # Local dev (Postgres, Redis, Kafka)
├── tests/                      # Unit tests
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_data_service.py    # DB schema, CRUD, migration tests
│   └── test_kafka.py           # Kafka producer/consumer/schema tests
└── pyproject.toml
```

## Schema

### Tables

- **orders** — Customer order lifecycle (PENDING → SUBMITTED → FILLED/CANCELLED/REJECTED)
- **positions** — Current and historical positions per wallet/symbol
- **fills** — Individual execution records (trade history with fees)

### Key Design Decisions

- UUID primary keys on orders/fills for distributed systems compatibility
- Numeric(32,18) for all price/quantity fields — exact decimal arithmetic
- PostgreSQL ENUM types for order side, type, status, and time-in-force
- Partial indexes on open orders for fast query performance
- JSONB columns for flexible metadata storage

## Kafka Event Streaming

### Topic Design

| Topic | Partitions | Retention | Compression | Purpose |
|---|---|---|---|---|
| `trading-platform.market.prices.v1` | 6 | 24h | lz4 | Real-time price ticks |
| `trading-platform.market.orderbook.v1` | 3 | 1h | lz4 | Order book snapshots |
| `trading-platform.market.trades.v1` | 6 | 7d | zstd | Trade executions |
| `trading-platform.news.feed.v1` | 3 | 30d | lz4 | Raw news articles |
| `trading-platform.news.analysis.v1` | 3 | 30d | lz4 | NLP-analyzed news |
| `trading-platform.signals.trading.v1` | 3 | 24h | lz4 | Trading signals |

All topics follow the `trading-platform.<domain>.<data-type>.<version>` naming convention.

### Producer

```python
from data_service.app.kafka.producer import DataProducer
from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource
from decimal import Decimal

producer = DataProducer(bootstrap_servers="kafka:9092")
producer.start()

event = MarketPriceEvent(
    symbol="BTC-USD",
    price=Decimal("50000.00"),
    source=PriceSource.YFINANCE,
)
producer.send_price(event)

producer.stop()
```

### Consumer

```python
from data_service.app.kafka.consumer import DataConsumer
from data_service.app.kafka.topics import KafkaTopics

consumer = DataConsumer(
    bootstrap_servers="kafka:9092",
    group_id="trading-engine",
    topics=[KafkaTopics.MARKET_PRICES, KafkaTopics.MARKET_TRADES],
)
consumer.start()

def handle_price(msg):
    print(f"Price update: {msg['value']['symbol']} = {msg['value']['price']}")

consumer.register_handler(KafkaTopics.MARKET_PRICES, handle_price)
consumer.consume_loop()
```

### Market Data Ingester (yfinance)

```python
from data_service.app.kafka.ingester import MarketDataIngester

ingester = MarketDataIngester(
    symbols=["BTC-USD", "ETH-USD", "SPY", "AAPL"],
    kafka_bootstrap_servers="kafka:9092",
    price_interval_seconds=60,
)
ingester.start()
ingester.run()  # blocking loop
ingester.stop()
```

### Setup Topics

```bash
# CLI
python -m data_service.app.kafka.setup_topics

# Programmatic
from data_service.app.kafka.setup_topics import setup_topics
results = setup_topics("kafka:9092")
for topic, created in results.items():
    print(f"  {topic}: {'CREATED' if created else 'ALREADY EXISTS'}")
```

## Connection Pooling

The `DatabaseConfig` class provides pre-tuned connection pooling:

- **PostgreSQL**: `AsyncAdaptedQueuePool` with pool_size=20, max_overflow=10
- **SQLite (dev)**: `StaticPool` for single-process development

Override pool settings via constructor parameters for production tuning.

## Kubernetes Architecture

```
customer1 namespace
├── postgres (StatefulSet, 1 replica)
│   ├── Service (ClusterIP :5432)
│   └── PVC (50Gi)
├── redis (StatefulSet, 1 replica)
│   ├── Service (ClusterIP :6379)
│   └── PVC (10Gi)
└── kafka (StatefulSet, 1 replica, KRaft mode)
    ├── kafka Service (ClusterIP :9092 — client)
    ├── kafka-headless Service (StatefulSet DNS)
    └── PVC (50Gi)
```

### Service Endpoints (internal cluster DNS)

- PostgreSQL: `postgres.customer1.svc.cluster.local:5432`
- Redis: `redis.customer1.svc.cluster.local:6379`
- Kafka: `kafka.customer1.svc.cluster.local:9092`

## Alembic Migrations

### Running in GKE

For production, run Alembic as a Kubernetes Job or init container:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: alembic-migrate
  namespace: customer1
spec:
  template:
    spec:
      containers:
        - name: alembic
          image: data-service:latest
          command: ["alembic", "-c", "alembic.ini", "upgrade", "head"]
          env:
            - name: DATABASE_URL
              value: "postgresql://trading:***@postgres:5432/trading_db"
      restartPolicy: Never
```

### Adding Migrations

```bash
# Auto-generate from model changes
alembic -c alembic.ini revision --autogenerate -m "describe changes"

# Apply all pending migrations
alembic -c alembic.ini upgrade head

# Rollback one step
alembic -c alembic.ini downgrade -1
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# Kafka-specific tests only
pytest tests/test_kafka.py -v

# With coverage
pytest tests/ --cov=data_service --cov-report=term-missing
```
