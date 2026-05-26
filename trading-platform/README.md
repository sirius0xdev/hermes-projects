# Trading Platform

Microservice-based trading platform running on GKE.

## Services

| Service | Port | Dir | Description |
|---------|------|-----|-------------|
| Dashboard | 3000 | dashboard/ | Next.js trading dashboard |
| Data Service | 8000 | data-service/ | Data pipeline, Postgres + Redis + Kafka consumers |
| Execute Service | 8002 | execute-service/ | Trading engine with Hyperliquid + Solana integration |
| News Service | 8000 | news-service/ | CryptoPanic/GNews connector, Kafka producer |
| Embedding Service | 8001 | embedding-service/ | Vector embedding generation |

## Directory Structure

```
trading-platform/
├── execute-service/         # Python FastAPI, uv-managed
├── news-service/            # Python FastAPI
├── data-service/            # Python FastAPI + data_infrastructure lib
├── dashboard/               # Next.js frontend
├── embedding-service/       # Python embedding inference
├── data_infrastructure/     # Shared Python lib (models, kafka, redis, proto)
├── docs/                    # Security review etc.
└── .github/workflows/
    ├── build-test.yml       # Build + unit tests on PR
    └── build-push.yml       # Build + push to container registry on merge
```

Each service has its own Dockerfile. K8s manifests live in the gcloud-lab repo.

## CI/CD

- **PR opened** -> build-test.yml runs unit tests + Docker build validation
- **Merged to master** -> build-push.yml builds images and pushes to container registry
