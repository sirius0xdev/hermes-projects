# Trading Platform — Infrastructure

Kubernetes deployment configuration for the DEFi trading platform on GKE (Google Kubernetes Engine).

## Directory Structure

```
infra/
├── dockerfiles/                    # Container images
│   ├── data-service/
│   │   ├── Dockerfile
│   │   └── .dockerignore
│   ├── execute-service/
│   │   ├── Dockerfile
│   │   └── .dockerignore
│   ├── news-service/
│   │   ├── Dockerfile
│   │   └── .dockerignore
│   └── dashboard/
│       ├── Dockerfile
│       └── .dockerignore
├── helm/trading-platform/          # Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── .sops.yaml                  # SOPS encryption config
│   ├── trading-secrets.yaml        # Secrets template (encrypt before use)
│   └── templates/
│       ├── namespace.yaml
│       ├── configmap.yaml
│       ├── secrets.yaml
│       ├── ingress.yaml
│       ├── _helpers.tpl
│       ├── NOTES.txt
│       ├── execute-service/
│       │   ├── deployment.yaml
│       │   └── service.yaml        # includes SA + HPA
│       ├── news-service/
│       │   ├── deployment.yaml
│       │   └── service.yaml
│       ├── data-service/
│       │   ├── deployment.yaml
│       │   └── service.yaml
│       ├── dashboard/
│       │   ├── deployment.yaml
│       │   └── service.yaml
│       ├── infrastructure/
│       │   ├── postgres.yaml       # StatefulSet + Service
│       │   ├── redis.yaml          # StatefulSet + Service
│       │   └── kafka.yaml          # KRaft StatefulSet + Services
│       ├── cert-manager/
│       │   └── certificates.yaml   # Issuers + mTLS certs
│       └── network-policies/
│           └── network-policies.yaml
└── .github/workflows/
    ├── build-test.yml              # PR: build + test
    ├── build-push.yml              # Push: build + push to Artifact Registry
    └── deploy.yml                  # Deploy to staging/prod via Helm
```

## Architecture

```
                        ┌─────────────────┐
                        │   GCE Ingress   │
                        │   (TLS/HTTPS)   │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
    ┌─────────┴──────┐  ┌──────┴────────┐  ┌──────┴──────────┐
    │   Dashboard    │  │  Execute      │  │    News         │
    │   (Next.js)    │  │  Service      │  │    Service      │
    │   :3000        │  │  :8000        │  │    :8000        │
    └────────────────┘  └──────┬────────┘  └────────┬────────┘
                               │ mTLS               │ mTLS
                               ▼                    │
                    ┌──────────────────┐             │
                    │   PostgreSQL     │             │
                    │   :5432          │◄────────────┘
                    └────────┬─────────┘
                             │
                    ┌────────┴─────────┐
                    │     Redis        │
                    │     :6379        │
                    └────────┬─────────┘
                             │
                    ┌────────┴─────────┐
                    │     Kafka        │
                    │  (KRaft) :9092   │
                    └──────────────────┘
```

## Quick Start

### Prerequisites

- `kubectl` configured for your GKE cluster
- `helm` v3.14+
- `sops` + `age` for secret encryption
- GCP Artifact Registry access

### 1. Generate Secrets

```bash
cd helm/trading-platform/

# Generate random secrets
python3 -c "
import secrets
print('EXECUTE_JWT_SECRET_KEY:', secrets.token_hex(32))
print('POSTGRES_PASSWORD:', secrets.token_urlsafe(24))
print('REDIS_PASSWORD:', secrets.token_urlsafe(24))
"

# Fill in trading-secrets.yaml with generated values
```

### 2. Encrypt Secrets with SOPS

```bash
# Generate Age key (do this once per project)
age-keygen -o age.key

# Update .sops.yaml with your Age public key

# Encrypt secrets
sops -e -i trading-secrets.yaml

# Verify encryption
sops trading-secrets.yaml  # should show ENCRYPTED
```

### 3. Deploy

```bash
# Deploy with defaults
helm upgrade --install trading-platform helm/trading-platform/ \
  --namespace trading --create-namespace --wait --timeout 10m

# Deploy with custom values
helm upgrade --install trading-platform helm/trading-platform/ \
  --namespace trading \
  -f values.staging.yaml \
  --set executeService.image.tag=abc12345 \
  --set newsService.image.tag=abc12345 \
  --wait --timeout 10m

# Apply encrypted secrets
sops -d trading-secrets.yaml | kubectl apply -f -
```

## Services

| Service | Port | Description | Replicas |
|---------|------|-------------|----------|
| execute-service | 8000 | Hyperliquid + Solana trading engine | 2-10 (HPA) |
| news-service | 8000 | CNPG connector + Kafka producer | 2-6 (HPA) |
| data-service | 8000 | PostgreSQL + Redis + Kafka consumers | 2-6 (HPA) |
| dashboard | 3000 | Next.js frontend | 2-8 (HPA) |

## Infrastructure Components

| Component | Version | Storage | Notes |
|-----------|---------|---------|-------|
| PostgreSQL | 17-alpine | 50Gi | Primary only, PVC-backed |
| Redis | 7-alpine | 10Gi | AOF persistence, 3 replicas |
| Kafka | 3.9.0 | 20Gi | KRaft mode (no Zookeeper), 3 brokers |

## mTLS Configuration

Service-to-service mTLS is configured via cert-manager:

1. **Internal CA** (`trading-ca`): Self-signed issuer creates the root CA
2. **CA Issuer** (`trading-ca-issuer`): Signs individual service certificates
3. **Service Certificates**: Each service gets a cert with DNS SANs for internal cluster access

Certificates are mounted at `/etc/mtls/` in each pod and contain:
- `tls.crt` — Service certificate
- `tls.key` — Private key
- `ca.crt` — CA certificate (for verification)

For production, replace the self-signed CA with:
- Google Cloud CA Service
- HashiCorp Vault PKI Secrets Engine
- External ACME provider

## Network Policies

All network policies follow a default-deny-then-allow approach:

1. `default-deny-all-ingress` — Deny all incoming traffic
2. `default-deny-all-egress` — Deny all outgoing traffic
3. `allow-dns-egress` — Allow DNS resolution for all pods
4. Per-service policies — Allow only required communication paths

See `templates/network-policies/network-policies.yaml` for full rules.

## CI/CD Pipeline

### Build & Test (PR)
- Runs on pull requests to `main`/`develop`
- Tests all services (Python pytest + Next.js build/lint)
- Validates Docker builds without pushing

### Build & Push (Push)
- Triggers on pushes to `main`/`develop`
- Authenticates via GCP Workload Identity Federation
- Builds multi-stage images with GHA cache
- Pushes to Artifact Registry with SHA-based tags

### Deploy (Manual/Auto)
- Manual: `workflow_dispatch` with environment + image tag selection
- Automatic: Triggers after successful Build & Push
- Uses `helm upgrade --install` with `--wait --atomic`
- Includes rollback on failure

## Security Notes

- All pods run as non-root with read-only filesystem
- Capabilities dropped (ALL) on all containers
- Secrets encrypted at rest with SOPS + Age
- Network policies enforce least-privilege communication
- mTLS for service-to-service authentication
- Ingress TLS via Let's Encrypt

## Monitoring

All services expose `/health` endpoints for liveness/readiness probes.
Prometheus scrape annotations are included on all deployments.

## Rollback

```bash
# Helm rollback
helm rollback trading-platform -n trading

# Or rollback to specific revision
helm rollback trading-platform 2 -n trading
```
