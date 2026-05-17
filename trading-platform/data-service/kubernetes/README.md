# Kubernetes manifests for data infrastructure (GKE)
#
## Deployment Order

Apply in this order to respect dependencies:

```bash
# 1. Create namespace first
kubectl apply -f kubernetes/namespace.yaml

# 2. Apply infrastructure (database, cache, message broker)
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml
kubectl apply -f kubernetes/postgres/
kubectl apply -f kubernetes/redis/
kubectl apply -f kubernetes/kafka/

# 3. Wait for infrastructure to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n customer1 --timeout=120s
kubectl wait --for=condition=ready pod -l app=redis -n customer1 --timeout=60s
kubectl wait --for=condition=ready pod -l app=kafka -n customer1 --timeout=180s

# 4. Apply data-service application
kubectl apply -f kubernetes/data-service/
```

Or apply recursively (namespace first):

```bash
kubectl apply -f kubernetes/namespace.yaml && kubectl apply -f kubernetes/
```

## Directory Structure

```
kubernetes/
├── namespace.yaml              # customer1 namespace
├── configmap.yaml              # shared configuration values
├── secrets.yaml                # database passwords, credentials
├── postgres/                   # PostgreSQL StatefulSet, Service, PVC
├── redis/                      # Redis StatefulSet, Service, PVC
├── kafka/                      # Kafka KRaft StatefulSet, headless Service, client Service, PVC
└── data-service/               # Data service application
    ├── deployment.yaml          # Ingester and Consumer deployments
    └── service.yaml             # ClusterIP services (ingester:8000, consumer:8001)
```

## Data Service Architecture

The data service consists of two separate deployments:

- **Ingester** (port 8000): Collects market data from external sources (yfinance, exchange APIs) and publishes to Kafka.
- **Consumer** (port 8001): Subscribes to Kafka topics and processes events for downstream systems.

They are split into separate deployments for independent horizontal scaling and resource management.

### Environment Variables

The data service is configured via ConfigMap and Secret references:

| Variable | Source | Description |
|---|---|---|
| `DATABASE_URL` | Secret | PostgreSQL connection string |
| `REDIS_URL` | Secret | Redis connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | ConfigMap | Kafka broker addresses |
| `KAFKA_GROUP_ID` | ConfigMap | Consumer group ID |
| `KAFKA_AUTO_OFFSET_RESET` | ConfigMap | Offset reset strategy |
| `CONSUME_TOPICS` | ConfigMap | Comma-separated topics to subscribe |
| `INGEST_SYMBOLS` | ConfigMap | Comma-separated tickers to ingest |
| `INGEST_INTERVAL_SECONDS` | ConfigMap | Seconds between ingestion cycles |
| `INGEST_MAX_RETRIES` | ConfigMap | Retry attempts for failed fetches |
| `LOG_LEVEL` | ConfigMap | Logging level (INFO, DEBUG, etc.) |

### Kafka Topics

The data service subscribes to these topics:
- `trading-platform.market.prices.v1`
- `trading-platform.market.orderbook.v1`
- `trading-platform.market.trades.v1`
- `trading-platform.news.feed.v1`
- `trading-platform.news.analysis.v1`

### Health Probes

- **Ingester**: Kubernetes readiness/liveness via TCP port 8000
- **Consumer**: FastAPI `/health` endpoint on port 8001 (HTTP GET returns 200 OK when healthy)

### Init Container

The ingester deployment uses an init container (`bitnami/kafka:3.7.0`) that polls Kafka broker
readiness before starting the main container, preventing connection loops during startup.

```bash
kubectl logs -n customer1 deployment/data-service-ingester -c wait-for-kafka
```

## Docker Build

```bash
# Build the image
docker build -t data-service:latest .

# Push to registry (example)
docker tag data-service:latest gcr.io/PROJECT_ID/data-service:latest
docker push gcr.io/PROJECT_ID/data-service:latest
```

## Teardown

```bash
# Delete in reverse order
kubectl delete -f kubernetes/data-service/
kubectl delete -f kubernetes/
kubectl delete -f kubernetes/namespace.yaml
```

## Debugging

Port forward for local debugging:

```bash
# Ingester (market data ingestion)
kubectl port-forward -n customer1 deployment/data-service-ingester 8000:8000

# Consumer (event processing)
kubectl port-forward -n customer1 deployment/data-service-consumer 8001:8001

# Kafka (for local client access)
kubectl port-forward -n customer1 deployment/kafka 9092:9092
```

Check logs:

```bash
kubectl logs -n customer1 deployment/data-service-ingester -f
kubectl logs -n customer1 deployment/data-service-consumer -f
```

## Notes

- Secrets are base64-encoded inline for convenience. In production,
  use GCP Secret Manager CSI driver or External Secrets Operator.
- Storage uses standard GKE persistent disks. For higher throughput,
  consider SSD (storageClassName: premium-rwo in GKE).
- PostgreSQL uses liveness/readiness probes with `pg_isready`.
- Kafka runs in KRaft mode (no Zookeeper).
- Node ports are NOT exposed — services are ClusterIP only.
  Use `kubectl port-forward` for local debugging.
- Multi-document YAML files use `---` separators (valid for `kubectl apply`).
