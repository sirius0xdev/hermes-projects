# Docker Compose Removed
## GKE-Only Deployment

All Docker Compose files have been removed from this repository:
- `trading-platform/docker-compose.yml`
- `trading-platform/docker-compose.news.yml`
- `trading-platform/data-service/docker-compose.yml`
- `trading-platform/deploy/docker-compose/`

This platform is **GKE-only**. Docker Compose was previously used for local development only.
For local development, use the Kubernetes manifests with a local cluster (minikube, kind, k3s).

Container images are built and pushed to GHCR: `ghcr.io/sirius0xdev/trading-<service>:latest`
