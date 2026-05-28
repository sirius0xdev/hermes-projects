# GCloud Lab — Complete System Design

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             GKE Cluster                                      │
│                         customer1 namespace                                  │
│                                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Gateway   │───>│ Trading   │───>│ Trading   │───>│ Trading   │              │
│  │ API       │    │ Data Svc  │───>│ Execute   │───>│ News Svc  │              │
│  │ (HTTP)    │    │ :8000     │    │ :8002     │    │ :8003     │              │
│  └────┬───── ┘    └────┬─────┘    └────┬─────┘    └────┬─────┘              │
│       │                │               │                │                      │
│       │         ┌──────┴───────────────┴────────────┐  │                      │
│       │         │       Shared Infrastructure        │  │                      │
│       │         │  ┌─────────┐  ┌────────┐ ┌───────┐│  │                      │
│       │         │  │ Postgres│  │ Redis  │ │Kafka  ││  │                      │
│       │         │  │  (CNPG) │  │Stack   │ │(Strimzi)││  │                      │
│       │         │  └─────────┘  └────────┘ └───────┘│  │                      │
│       │         └────────────────────────────────────┘  │                      │
│       │                                                  │                      │
│  ┌────┴─────┐    ┌──────────┐    ┌──────────┐    ┌──────┴─────┐              │
│  │ Dashboard│    │Hermes    │    │OpenClaw  │    │Embedding   │              │
│  │ :3000    │    │Agent     │    │Gateway   │    │Service     │              │
│  │          │    │:8642     │    │:18789    │    │:8000       │              │
│  └──────────┘    └──────────┘    └──────────┘    └────────────┘               │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐        │
│  │                    CronJobs (News Pipeline)                       │        │
│  │  Scraper (:50) ──> Analyst (:15) ──> Telegram Messenger (:30)    │        │
│  └──────────────────────────────────────────────────────────────────┘        │
│                                                                              │
│  Other: n8n · waitlist-api · paaas-landing · uncensored-bot · vLLM GPUs     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Infrastructure Foundation

### 1.1 GKE Cluster
- **Project:** `customer1-gke` on Google Cloud
- **Region:** `us-central1`
- **Node Pools:** CPU nodes + GPU nodes (RTX 6000, A100, L4)
- **IaC:** Terraform modules in `gcloud-lab/modules/` (GKE, VPC, nodepools)

### 1.2 GitOps — Flux CD
All manifests deployed via Flux CD, no manual `kubectl apply`:

```
gcloud-lab repo (GitHub)
    │
    ▼
Flux GitRepository (clusters/devops-lab/)
    │
    ├── customer1-strimzi.yaml  ──→ Strimzi Kafka operator (dependency)
    ├── customer1.yaml          ──→ apps/staging/customer1/
    ├── infra-controllers.yaml  ──→ CNPG, Cert-Manager, KEDA
    ├── infra-gatewayapi.yaml   ──→ Gateway API controller
    ├── infra-gpus.yaml         ──→ GPU device plugins
    └── infra-monitoring.yaml   ──→ Grafana/Prometheus stack
    │
    ▼
apps/staging/customer1/kustomization.yaml  (Kustomize overlay)
    │
    └── pulls from apps/base/customer1/
            ├── namespace.yaml
            ├── trading-platform/
            ├── hermes-agent/
            ├── hermes-db/
            ├── siriusdevops-db/
            ├── news_bot/
            ├── openclaw/
            ├── embedding-service/
            ├── uncensored-bot/
            ├── paaas-landing/
            └── ...
```

- **Sync interval:** 1 minute
- **Decryption:** sops + age (key: `sops-age` secret in flux-system)
- **Prune:** enabled (auto-cleans removed resources)
- **Force:** enabled

### 1.3 Secret Management
- All secrets encrypted with **sops + age**
- Recipient key: `age1uuxf066x...`
- Decrypted at deploy time by Flux's built-in sops decryption
- Key secret groups:
  - `trading-platform-secrets` — API keys, service auth tokens
  - `solana-api-keys` — Helius + Jupiter RPC keys
  - `execute-service-jwt-secret` — JWT signing
  - `hermes-config` — full Hermes Agent configuration

### 1.4 Networking
- **Gateway API** (not classic Ingress) for HTTP routing
- **Tailscale** zero-trust networking — services exposed with `tailscale.com` annotations
- **NetworkPolicies** on trading platform — strict ingress/egress:
  - Allowed: DNS, DB (5432), Redis (6379), Kafka (9092), inter-service, external HTTPS (Helius/Solana/Jupiter)

---

## 2. Application Repositories (Two-Repo Model)

### 2.1 `hermes-projects` — App Code + CI
- **Repo:** `github.com/sirius0xdev/hermes-projects`
- **Contains:** All application source code, Dockerfiles, GitHub Actions workflows
- **Push `main`:** triggers CI → builds → pushes to container registries
- **Structure:**
  ```
  hermes-projects/
  ├── .github/workflows/           # Repo-level CI/CD → GHCR
  │   ├── build-and-push.yml       # Push to main → build + push GHCR
  │   └── build-test.yml           # PR → build only (validation)
  ├── trading-platform/            # 9 microservices
  │   ├── .github/workflows/       # Trading-specific CI/CD → GCP AR
  │   ├── dashboard/               # Next.js frontend
  │   ├── data-service/            # Python FastAPI — market data
  │   ├── execute-service/         # Python FastAPI — trading engine
  │   ├── news-service/            # Python FastAPI — news connector
  │   ├── embedding-service/       # Python — vector embeddings
  │   ├── reasoning-service/       # Python — LLM client + RAG
  │   ├── swarm-service/           # Python — multi-agent orchestration
  │   ├── simulation-service/      # Python — Monte Carlo + replay
  │   └── reporting-service/       # Python — weekly reports
  ├── data_infrastructure/         # Shared Python lib (models, Kafka, Redis, proto)
  ├── waitlist-api/                # Python API + Telegram bot
  ├── paaas/                       # Landing page
  └── siriusdevops/                # Nginx static site
  ```

### 2.2 `gcloud-lab` — K8s Manifests (Source of Truth)
- **Repo:** `github.com/sirius0xdev/gcloud-lab`
- **Contains:** ONLY Kubernetes manifests, ConfigMaps, Terraform modules
- **No build artifacts** — references images from GHCR
- **Master branch:** source of truth for live cluster state
- **Structure:**
  ```
  gcloud-lab/
  ├── clusters/devops-lab/         # Flux Kustomizations (GitOps entry)
  ├── apps/
  │   ├── base/customer1/          # ALL customer1 manifests
  │   └── staging/customer1/       # Kustomize overlay (composes base)
  ├── infrastructure/              # Controllers, GPUs, Tailscale
  ├── modules/                     # Terraform (GKE, VPC, nodepools)
  ├── trading-platform/            # Separate Helm + K8s
  └── trading-scripts/             # Python market data scripts
  ```

### 2.3 Critical Rule
> **Code changes:** push `main` on `hermes-projects` → CI builds → images pushed to GHCR.
> **Manifest changes:** PR to `gcloud-lab/master` → Flux syncs → live cluster updated.
> **Never** change manifests in `hermes-projects/k8s/` — they diverge and are reference only.

---

## 3. CI/CD Pipeline (Dual Registry)

### 3.1 GitHub Container Registry (GHCR) — Primary

```
Push to main on hermes-projects
    │
    ▼
.github/workflows/build-and-push.yml
    │
    ├── Matrix: 11 services
    ├── Auth: GITHUB_TOKEN (packages: write)
    ├── Registry: ghcr.io/sirius0xdev/
    └── Tags: :latest + :$SHORT_SHA (7-char)
    │
    ▼
Images pushed to GHCR
    │
    ├── ghcr.io/sirius0xdev/trading-data-service:latest
    ├── ghcr.io/sirius0xdev/trading-execute-service:latest
    ├── ghcr.io/sirius0xdev/trading-news-service:latest
    ├── ghcr.io/sirius0xdev/trading-dashboard:latest
    ├── ghcr.io/sirius0xdev/trading-embedding-service:latest
    ├── ghcr.io/sirius0xdev/trading-reasoning-service:latest
    ├── ghcr.io/sirius0xdev/trading-swarm-service:latest
    ├── ghcr.io/sirius0xdev/trading-simulation-service:latest
    ├── ghcr.io/sirius0xdev/trading-reporting-service:latest
    ├── ghcr.io/sirius0xdev/waitlist-api:latest
    └── ghcr.io/sirius0xdev/paaas:latest
```

- **Build context:** repo root (`.`)
- **Dockerfiles use:** `COPY trading-platform/*/app/ ./app/` paths
- **Multi-stage builds:** builder installs deps, runner copies as non-root `appuser`
- **All images include HEALTHCHECK** hitting `/health`

### 3.2 GCP Artifact Registry — Secondary

```
Push to main/develop (path: trading-platform/**)
    │
    ▼
trading-platform/.github/workflows/build-push.yml
    │
    ├── Auth: GCP Workload Identity Federation (no SA keys)
    ├── Registry: us-central1-docker.pkg.dev/customer1-gke/trading/
    └── Tags: :$SHA8 + :$BRANCH_NAME
```

- **Build context:** service directory
- **Dockerfiles use:** `COPY ./app/ ./app/` paths
- **Docker Buildx cache:** `type=gha, mode=max`
- **Not used by current gcloud-lab manifests** — GHCR is the active registry

### 3.3 Deploy Flow (End-to-End)

```
1. Developer pushes code to hermes-projects/main
2. GitHub Actions builds + pushes images to GHCR
3. gcloud-lab manifests already point to :latest tags
4. Developer manually deletes pods in GKE
5. imagePullPolicy: Always pulls fresh images
6. (Optional) Manifest changes → PR to gcloud-lab/master → Flux syncs
```

---

## 4. Databases — 3 CNPG PostgreSQL Clusters

All managed by CloudNative PG operator, all back up to GCS.

### 4.1 siriusdevops-pgdb (Primary App DB)

- **Image:** `cloudnative-pg/postgresql:15.2`
- **Storage:** 20Gi PVC
- **Databases:**
  - `waitlist` — waitlist signups
  - `trading_data` — market data, candlesticks, order book
  - `trading_dashboard` — dashboard state, user preferences
  - `news_app_db` — scraped articles + analyst summaries
- **Users:** waitlist, trading, trading_dashboard, news_app
- **Backup:** GCS `gs://customer1_db_backup/`, gzip, 30-day retention, daily 03:00–04:00 UTC

### 4.2 hermes-pgdb (Agent Memory + RAG)

- **Image:** `postgres-pgvector:15.2-0.8.0` (custom, pgvector extension)
- **Storage:** 20Gi PVC
- **Databases:**
  - `hermes_memory` — Hermes Agent cross-session memory
  - `agent_memory` — RAG vector store
- **Users:** hermes, trading, memory
- **RAG Schema:** `init-rag-schema` Job creates pgvector tables with HNSW indexes
  - 768-dim vectors, cosine distance, full-text search
- **Backup:** GCS `gs://customer1_db_backup/`, daily 03:00 UTC

### 4.3 customer1-pgdb (n8n)

- **Image:** `cloudnative-pg/postgresql:15.2`
- **Storage:** 10Gi PVC
- **Database:** `n8n`
- **Users:** customer1, news_app
- **Backup:** GCS `gs://customer1_db_backup/`, daily 04:00 UTC

### 4.4 Connection Pattern
All services connect via CNPG service endpoints:
- Read-write: `-rw` suffix (e.g., `siriusdevops-pgdb-rw`)
- Port: 5432

---

## 5. Trading Platform

### 5.1 Services (Deployed on GKE)

**Note:** 9 services exist in code, 4 are currently deployed on GKE.

| Service | Image | Port | Status | Description |
|---------|-------|------|--------|-------------|
| **data-service** | `ghcr.io/sirius0xdev/trading-data-service:latest` | 8000 | ✅ Deployed | Market data ingestion, Postgres + Redis + Kafka consumers |
| **execute-service** | `ghcr.io/sirius0xdev/trading-execute-service:latest` | 8002 | ✅ Deployed | Hyperliquid + Solana trading engine |
| **news-service** | `ghcr.io/sirius0xdev/trading-news-service:latest` | 8003 | ✅ Deployed | CryptoPanic/GNews connector, Kafka producer |
| **dashboard** | `ghcr.io/sirius0xdev/trading-dashboard:latest` | 3000 | ✅ Deployed | Next.js frontend (React) |
| **embedding-service** | `ghcr.io/sirius0xdev/trading-embedding-service:latest` | 8000 | ✅ Deployed | Vector embeddings (nomic-embed-text-v1.5, 768-dim) |
| **reasoning-service** | `ghcr.io/sirius0xdev/trading-reasoning-service:latest` | 8004 | 🔲 In code | vLLM/OpenAI LLM client + RAG |
| **swarm-service** | `ghcr.io/sirius0xdev/trading-swarm-service:latest` | 8005 | 🔲 In code | Multi-agent orchestration + consensus |
| **simulation-service** | `ghcr.io/sirius0xdev/trading-simulation-service:latest` | 8006 | 🔲 In code | Monte Carlo + historical replay |
| **reporting-service** | `ghcr.io/sirius0xdev/trading-reporting-service:latest` | 8007 | 🔲 In code | Weekly reports + custom widgets |

### 5.2 Gateway API Routing (HTTP)

Routes on `sirius-sec.com` / `www.sirius-sec.com`:

```
sirius-sec.com
├── /trade              → trading-dashboard-svc:80 (port 3000)
├── /api/data           → trading-data-service:80 (port 8000)
├── /api/execute        → trading-execute-service:80 (port 8002)
├── /api/news           → trading-news-service:80 (port 8003)
├── /api/waitlist       → waitlist-api:8080
└── n8n.sirius-sec.com  → n8n-service:5678
```

### 5.3 Trading Dependencies

- **Redis Stack** (`redis/redis-stack:7.4.0-v8`)
  - RediSearch for vector similarity (HNSW, 768-dim)
  - 10Gi PVC, 1Gi memory limit
  - Service: `trading-redis`

- **Strimzi Kafka** (`trading-kafka`)
  - Kafka 4.1.0, 1 broker, 10Gi storage
  - Bootstrap: `trading-kafka-kafka-bootstrap:9092`
  - Auto-create topics enabled

- **ConfigMaps:**
  - DB URLs pointing to `siriusdevops-pgdb-rw`
  - Redis: `trading-redis:6379`
  - Kafka: `trading-kafka-kafka-bootstrap:9092`
  - Helius RPC + Jupiter API endpoints (Solana)

- **Shared Data Infrastructure** (`data_infrastructure/` in hermes-projects):
  - Shared Python library with models, Kafka producers/consumers, Redis clients, protobuf definitions
  - Used across all trading services

### 5.4 Security Hardening
All trading containers:
- Run as non-root (`appuser`)
- Read-only root filesystem
- Dropped ALL capabilities
- NetworkPolicies restrict to only required egress

---

## 6. Hermes Agent

### 6.1 Deployment
- **Agent:** `nousresearch/hermes-agent:latest` (port 8642)
- **WebUI:** `ghcr.io/nesquena/hermes-webui:latest` sidecar (port 8787)
- **Storage:** 25Gi PVC (`hermes-agent-pvc`) — persists config, skills, memory
- **Init container:** fixes volume permissions before agent starts

### 6.2 Model Providers
- **Primary:** xAI `grok-4.20-0309-reasoning` via `grok-4.3` (xAI OAuth)
- **Local fallbacks:**
  - `rtx6000-brain` — vLLM on RTX 6000 GPU (`rtx6000-brain-service:8000`)
  - `qwen-vllm` — Qwen model on GPU
- **Profiles:** 8 specialist profiles (backend-dev, frontend-dev, researcher, sec-ops, outreach, quant, repo-keeper, devops) all via grok-4.3

### 6.3 Integrated Features
- **Telegram:** webhook (`ws.siriusdevops.com`) + polling fallback
- **Kanban:** on-demand dispatch (`hermes kanban dispatch --max 4`), 5-min watchdog cron
- **Skills:** 100+ skills across categories (devops, creative, data-science, mlops, etc.)
- **Memory:** persistent user + system memory (SQLite FTS5)
- **Session search:** local session DB for cross-session recall
- **Browser automation:** built-in browser for web interaction
- **TTS/STT:** text-to-speech, speech-to-text
- **Delegation:** sub-agent spawning (max 4 concurrent)

### 6.4 RAG Pipeline
```
User query → embedding-service (nomic-embed-text) → 768-dim vector
    → pgvector (HNSW index, cosine distance) in hermes-pgdb/agent_memory
    → context injected into Hermes Agent prompt
```

---

## 7. News Pipeline (CronJobs)

All hourly, all write to `news_app_db` on `siriusdevops-pgdb`.

```
:50                         :15                         :30
│                           │                           │
▼                           ▼                           ▼
┌──────────────┐    ┌────────────────┐    ┌──────────────────┐
│  Scraper     │───>│  Analyst       │───>│  Telegram        │
│  (:50 min)   │    │  (:15 min)     │    │  Messenger       │
│              │    │                │    │  (:30 min)       │
│ Image:       │    │ Image:         │    │ Image:           │
│ newsscraper: │    │ (DeepSeek via  │    │ news-messenger   │
│ latest       │    │  vLLM at       │    │                  │
│              │    │  rtx6000-brain │    │                  │
└──────────────┘    └────────────────┘    └──────────────────┘
```

| CronJob | Image | Schedule | Active? |
|---------|-------|----------|---------|
| news-scraper | `ghcr.io/sirius0xdev/newsscraper:latest` | `50 * * * *` | ✅ |
| deepseek-analyst | `ghcr.io/sirius0xdev/news-analyst:latest` | `15 * * * *` | ✅ (via OpenAI SDK → vLLM) |
| news-messenger | `siriussec/news-messenger` | `30 * * * *` | ✅ |

- **Analyst model:** DeepSeek via OpenAI-compatible SDK pointing to vLLM at `rtx6000-brain-service:8000`
- **ConfigMap:** `deepseek-config` with DARPA-style analyst summary prompt
- **Telegram delivery:** pushes to Telegram channel

---

## 8. Other Services

### 8.1 OpenClaw Gateway
- **Image:** `ghcr.io/openclaw/openclaw:slim`
- **Port:** 18789
- **Providers:** Anthropic, Gemini, OpenRouter, xAI (optional via secrets)
- **Storage:** PVC + emptyDir tmp (memory-backed)

### 8.2 n8n Workflow Automation
- **Image:** `docker.n8n.io/n8nio/n8n:2.1.4`
- **Port:** 5678
- **Route:** `n8n.sirius-sec.com`
- **DB:** `n8n` on `customer1-pgdb`

### 8.3 Waitlist API
- **Image:** `ghcr.io/sirius0xdev/waitlist-api:latest`
- **Port:** 8080
- **Routes:** `/api/waitlist` on `sirius-sec.com` + `agentforge.ai`
- **DB:** `waitlist` on `siriusdevops-pgdb`
- **Telegram bot:** notifications on new signups

### 8.4 PaaS Landing Page
- **Image:** `ghcr.io/sirius0xdev/paaas:latest`
- **Port:** 8080
- **Lightweight:** static page server with GKE healthcheck

### 8.5 Uncensored Proxy Bot
- Python 3.12 slim container
- ConfigMap-mounted scripts
- Telegram bot proxying to LLM backends

---

## 9. GPU Infrastructure

### 9.1 vLLM Serving
- **RTX 6000 nodepool:** primary inference GPU
- **A100 nodepool:** high-throughput workloads
- **L4 nodepool:** cost-effective inference
- **KEDA autoscaling:** scales vLLM pods based on queue depth

### 9.2 GPU Services
```
rtx6000-brain-service:8000  → OpenAI-compatible API
    ├── Hermes Agent local provider fallback
    ├── News analyst (DeepSeek)
    └── Trading reasoning-service
```

---

## 10. Monitoring & Observability

- **Prometheus + Grafana** stack (Flux-managed via `infra-monitoring.yaml`)
- **KEDA metrics** for event-driven autoscaling
- **CNPG Barman** for PostgreSQL backup monitoring
- **Healthchecks** on all trading services (`/health` endpoint)

---

## 11. Deployment Checklist

### Code Change (hermes-projects)
1. Push to `main` on `hermes-projects`
2. GitHub Actions builds + pushes to GHCR (`:latest` + `:sha`)
3. gcloud-lab manifests reference `:latest`
4. Delete pods manually to force pull (`imagePullPolicy: Always`)
5. Verify pods are running with new image

### Manifest Change (gcloud-lab)
1. Edit manifests in `gcloud-lab`
2. PR to `master` branch
3. Merge → Flux syncs within 1 minute
4. Verify resources updated on cluster

### Full Redeploy
1. Code push to `hermes-projects/main`
2. Manifest update PR to `gcloud-lab/master`
3. Flux syncs → new pods with new images

---

## 12. Key Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **Two-repo model** | Separates code from infra — prevents accidental manifest changes with code pushes |
| **GHCR primary** | GitHub-native auth, no service account keys needed, free for public/repos |
| **:latest tags** | Simplicity for solo dev — no tag versioning overhead |
| **sops + age** | Git-commitable encrypted secrets, no external vault dependency |
| **CNPG over plain Postgres** | Native K8s operator, automated backups, connection pooling |
| **Gateway API over Inress** | Modern standard, better multi-tenant routing, HTTPRoute resources |
| **Flux CD** | GitOps-native, declarative, auto-sync from git |
| **pgvector + Redis hybrid** | pgvector for persistence, Redis for fast in-memory vector search |
| **KEDA for GPU autoscaling** | Scale GPUs based on actual queue depth, not just CPU/memory |

---

*Generated from live repo state: `gcloud-lab` + `hermes-projects`*
