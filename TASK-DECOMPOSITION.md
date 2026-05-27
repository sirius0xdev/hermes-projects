# Task Decomposition — Trading Platform AI Upgrades

**Date:** 2026-05-27
**Author:** researcher (Kanban t_19872b62)
**Parent task:** t_19872b62

---

## Implementation Profile Mapping

| Profile | Responsibility |
|---------|---------------|
| backend-dev | FastAPI microservices, Kafka consumers/producers, Postgres models, shared libraries |
| frontend-dev | Next.js dashboard pages, components, API routes, SSE integration, widget renderer |
| devops | K8s manifests (gcloud-lab repo), Dockerfiles, CI/CD, vLLM GPU deployment, RediSearch enablement |
| sec-ops | Security hardening, mTLS config, encryption at rest, rate limiting, wallet auth review |
| quant | Simulation engine, Monte Carlo, strategy backtesting, risk parameters |

---

## Phase 1: Quick Wins (Highest Priority)

### Feature 1: RAG Semantic Search + Market Memory

#### Task 1.1 — Embedding Service Extension: Vector Storage + Semantic Search Endpoint
- **Profile:** backend-dev
- **Complexity:** M
- **Dependencies:** None
- **Description:**
  - Add Redis vector index (RediSearch HNSW, 768 dimensions) to embedding-service
  - Implement POST /semantic-search endpoint: accepts query text + filters (entity_type, date_range, min_similarity)
  - Implement POST /v1/index endpoint: stores embeddings by (entity_type, entity_id) with metadata
  - Add batch indexing endpoint for bulk operations
  - Update embedding-service/requirements.txt with redis RediSearch client
  - Write unit tests for search accuracy and indexing
- **Deliverables:**
  - embedding-service/app/vector_store.py — Redis vector index management
  - embedding-service/app/routes/search.py — semantic search + indexing endpoints
  - Updated embedding-service/requirements.txt
  - Tests in embedding-service/tests/test_vector_search.py
- **K8s:** No manifest changes needed initially (same container)

#### Task 1.2 — Data Service: Trade/News Indexer
- **Profile:** backend-dev
- **Complexity:** M
- **Dependencies:** Task 1.1
- **Description:**
  - Add background indexer in data-service that watches for new/closed trades and publishes to trading-platform.embeddings.index.v1
  - Trade context serialization: symbol, side, entry/exit, PnL, leverage, duration, market conditions (price, volume), news sentiment at time
  - News indexer: consume trading-platform.news.feed.v1, serialize article + analysis, publish to index topic
  - Add embedding-service client to data_infrastructure shared lib
  - Update Kafka topic definitions in data-service/data_service/app/kafka/topics.py
- **Deliverables:**
  - data-service/data_service/app/indexers/ — trade indexer, news indexer
  - data_infrastructure/embedding/ — shared embedding service client
  - Updated topics.py with trading-platform.embeddings.index.v1
  - Alembic migration for embeddings table (if using Postgres as backup store)
- **Kafka topics:** trading-platform.embeddings.index.v1

#### Task 1.3 — Dashboard: Semantic Search UI Component
- **Profile:** frontend-dev
- **Complexity:** M
- **Dependencies:** Task 1.1
- **Description:**
  - Add global search bar component in AppShell.tsx navigation
  - API route app/api/semantic-search/route.ts proxying to embedding-service
  - Results page app/search/page.tsx showing matched trades, news articles, with similarity scores
  - Real-time results using debounced input (300ms)
  - Tailwind styling matching existing dashboard theme
- **Deliverables:**
  - dashboard/components/SearchBar.tsx — reusable search input
  - dashboard/components/SearchResults.tsx — results card list
  - dashboard/app/search/page.tsx — dedicated search results page
  - dashboard/app/api/semantic-search/route.ts — API proxy
- **Testing:** Ensure search works with empty state, loading state, and error state

---

### Feature 2: Conversational AI Co-Pilot

#### Task 2.1 — Reasoning Service: Core LLM Service
- **Profile:** backend-dev
- **Complexity:** L
- **Dependencies:** Task 1.1
- **Description:**
  - Create reasoning-service/ FastAPI microservice
  - Implement POST /chat endpoint: accepts query + conversation history, returns streamed response (SSE)
  - Implement POST /recommend endpoint: structured trade recommendation output
  - Integrate with embedding-service for RAG context retrieval (semantic search on relevant trades/news)
  - Integrate with data-service for current portfolio/position data
  - LLM client: OpenAI-compatible interface pointing to vLLM on RTX 6000
  - Configurable system prompts per conversation type (general Q&A, trade analysis, portfolio review)
- **Deliverables:**
  - trading-platform/reasoning-service/app.py — FastAPI entry point
  - trading-platform/reasoning-service/app/llm_client.py — vLLM/OpenAI-compatible client
  - trading-platform/reasoning-service/app/routes/chat.py — chat + recommendation endpoints
  - trading-platform/reasoning-service/app/prompts.py — system prompt templates
  - trading-platform/reasoning-service/Dockerfile
  - trading-platform/reasoning-service/requirements.txt
  - Alembic migration for copilot_conversations table
- **Kafka topics:** trading-platform.copilot.queries.v1, trading-platform.copilot.responses.v1

#### Task 2.2 — vLLM GPU Deployment on GKE
- **Profile:** devops
- **Complexity:** M
- **Dependencies:** None (can run in parallel)
- **Description:**
  - Deploy vLLM as K8s StatefulSet with GPU node selector on RTX 6000
  - Model: Qwen2.5-7B-Instruct (FP8 quantization for 16GB VRAM)
  - OpenAI-compatible endpoint /v1/chat/completions + /v1/embeddings (fallback)
  - Health checks: /health and /health/ready
  - Resource limits: nvidia.com/gpu: 1, memory 20Gi
  - HPA not needed (single GPU) — configure readiness/liveness probes
  - K8s manifests go to gcloud-lab repo as PR to master
- **Deliverables:**
  - gcloud-lab/k8s/customer1/vllm-statefulset.yaml
  - gcloud-lab/k8s/customer1/vllm-service.yaml
  - gcloud-lab/k8s/customer1/vllm-configmap.yaml
  - PR to gcloud-lab master branch

#### Task 2.3 — Dashboard: Co-Pilot Chat Interface
- **Profile:** frontend-dev
- **Complexity:** L
- **Dependencies:** Task 2.1
- **Description:**
  - New page app/copilot/page.tsx — full-width chat interface
  - SSE integration for streaming responses from reasoning-service
  - Voice input using Web Speech API (client-side, no server cost)
  - Message history persisted in copilot_conversations table
  - "Execute" button on trade recommendations, navigates to /trade with pre-filled form
  - Conversation context sidebar with recent queries
  - Tailwind styling matching existing dashboard
- **Deliverables:**
  - dashboard/components/CopilotChat.tsx — chat interface
  - dashboard/components/CopilotMessage.tsx — individual message cards
  - dashboard/components/VoiceInput.tsx — voice input widget
  - dashboard/app/copilot/page.tsx — co-pilot page
  - dashboard/app/api/copilot/chat/route.ts — SSE proxy
  - dashboard/app/api/copilot/history/route.ts — conversation history

---

## Phase 2: Core AI

### Feature 3: Multi-Agent Swarm

#### Task 3.1 — Swarm Orchestrator Service
- **Profile:** backend-dev
- **Complexity:** L
- **Dependencies:** Task 2.1
- **Description:**
  - Create swarm-service/ FastAPI microservice
  - Implement agent orchestration: dispatch market events to all agents, collect responses, compute consensus
  - Kafka consumer for trading-platform.market.prices.v1 (triggers swarm)
  - Kafka producer for trading-platform.agents.consensus.v1
  - Each agent runs as separate K8s pod consuming from its own topic and publishing analysis
  - Agent types: Scout (opportunity scan), Risk Guardian (risk assessment), Historian (historical matches), Executor (trade plan)
  - Consensus algorithm: weighted voting with configurable agent weights
  - Live debate log: stream agent responses to dashboard via SSE
- **Deliverables:**
  - trading-platform/swarm-service/app.py — orchestrator entry point
  - trading-platform/swarm-service/app/orchestrator.py — dispatch + consensus logic
  - trading-platform/swarm-service/app/agents/ — agent base class + implementations
  - trading-platform/swarm-service/Dockerfile
  - Alembic migration for agent_debates table
- **Kafka topics:** trading-platform.agents.{scout,risk,historian,executor,consensus}.v1

#### Task 3.2 — Dashboard: Agent Hub Page
- **Profile:** frontend-dev
- **Complexity:** M
- **Dependencies:** Task 3.1
- **Description:**
  - New page app/agents/page.tsx — live debate transcript
  - Each agent has a profile card with confidence scores, analysis summary, and voting status
  - Real-time updates via SSE from swarm-service
  - Historical debate archive with search
  - Visual consensus indicator (e.g., radial gauge or color-coded votes)
- **Deliverables:**
  - dashboard/components/AgentHub.tsx — main hub component
  - dashboard/components/AgentCard.tsx — individual agent display
  - dashboard/components/DebateTranscript.tsx — live debate log
  - dashboard/app/agents/page.tsx — agent hub page
  - dashboard/app/api/agents/debate/route.ts — SSE proxy

#### Task 3.3 — Swarm K8s Deployment
- **Profile:** devops
- **Complexity:** M
- **Dependencies:** Task 3.1
- **Description:**
  - Deploy swarm-service + 4 agent pods (scout, risk, historian, executor)
  - Each agent as separate Deployment for independent scaling
  - NetworkPolicy: agents only communicate via Kafka (no direct inter-pod HTTP)
  - Resource limits: moderate CPU/memory per agent (LLM calls are async to vLLM)
  - K8s manifests in gcloud-lab PR to master
- **Deliverables:**
  - gcloud-lab/k8s/customer1/swarm-service-{deployment,service}.yaml
  - gcloud-lab/k8s/customer1/swarm-agent-{scout,risk,historian,executor}-deployment.yaml
  - gcloud-lab/k8s/customer1/swarm-networkpolicy.yaml
  - PR to gcloud-lab master

---

### Feature 5: Simulator + Auto-Rebalancer

#### Task 5.1 — Simulation Engine Service
- **Profile:** quant
- **Complexity:** L
- **Dependencies:** Task 1.2 (historical data available)
- **Description:**
  - Create simulation-service/ FastAPI microservice
  - Monte Carlo engine: configurable scenarios (N simulations, time horizon, seed)
  - Historical replay: consume trading-platform.market.prices.v1 at configurable offset/speed
  - "What-if" scenarios: modify single variables (funding rates, price shocks, volatility)
  - Results: distribution of outcomes (PnL, max drawdown, Sharpe ratio) as JSON
  - Integration with data-service for current portfolio state
  - Integration with execute-service for auto-rebalancer trade submission
- **Deliverables:**
  - trading-platform/simulation-service/app.py — entry point
  - trading-platform/simulation-service/app/monte_carlo.py — Monte Carlo engine
  - trading-platform/simulation-service/app/replay.py — historical replay engine
  - trading-platform/simulation-service/app/routes/simulate.py — simulation endpoints
  - trading-platform/simulation-service/Dockerfile
  - Alembic migrations for user_goals, simulation_runs tables
- **Kafka topics:** trading-platform.simulation.{requests,results}.v1

#### Task 5.2 — Dashboard: Simulator UI + Goal Setting
- **Profile:** frontend-dev
- **Complexity:** M
- **Dependencies:** Task 5.1
- **Description:**
  - Interactive simulator page app/simulator/page.tsx with sliders for parameters
  - Results visualization: distribution chart using lightweight-charts or Recharts
  - Goal setting form: target value, target date, max drawdown, strategy parameters
  - Auto-rebalancer status display with toggle on/off
  - Tailwind styling matching dashboard theme
- **Deliverables:**
  - dashboard/components/SimulatorForm.tsx — parameter input
  - dashboard/components/SimulationResults.tsx — results visualization
  - dashboard/components/GoalSetter.tsx — goal configuration
  - dashboard/app/simulator/page.tsx — simulator page
  - dashboard/app/api/simulator/route.ts — API proxy

---

### Feature 7: Cross-Chain Opportunity Engine

#### Task 7.1 — Opportunity Scanner
- **Profile:** backend-dev
- **Complexity:** M
- **Dependencies:** Task 1.2
- **Description:**
  - Add cross-chain opportunity scanner to data-service
  - Monitor Solana lending yields (API calls to Aave/Solend)
  - Monitor Hyperliquid funding rates (WebSocket or REST)
  - Calculate delta-neutral arb, yield spread arb, and price differential opportunities
  - When threshold met (>configurable edge%): publish to trading-platform.opportunities.v1
  - Embed opportunity context via embedding-service for historical similarity
  - Configurable alert thresholds per opportunity type
- **Deliverables:**
  - data-service/data_service/app/scanners/opportunity_scanner.py — scanner logic
  - data-service/data_service/app/scanners/solana_yields.py — Solana yield data
  - data-service/data_service/app/scanners/hyperliquid_funding.py — funding rate data
  - Updated topics.py with trading-platform.opportunities.v1
  - Alembic migration for opportunities table

#### Task 7.2 — Dashboard: Opportunities Widget
- **Profile:** frontend-dev
- **Complexity:** S
- **Dependencies:** Task 7.1
- **Description:**
  - "Opportunities" widget in dashboard sidebar or dedicated page app/opportunities/page.tsx
  - Real-time alerts via SSE: "3.2% edge detected — execute now?"
  - One-click execution, opens trade confirmation modal, calls execute-service
  - Historical opportunity log with profitability tracking
- **Deliverables:**
  - dashboard/components/OpportunityCard.tsx — opportunity alert card
  - dashboard/app/opportunities/page.tsx — opportunities page
  - dashboard/app/api/opportunities/route.ts — API proxy

---

## Phase 3: Advanced Features

### Feature 4: Explainable AI Replay Cards

#### Task 4.1 — Trade Reasoning Metadata Capture
- **Profile:** backend-dev
- **Complexity:** S
- **Dependencies:** Task 1.1, Task 3.1
- **Description:**
  - Extend execute-service to attach reasoning_trace to order metadata JSONB on every trade
  - reasoning_trace structure: {trigger, signals_used, agent_confidence, embedding_matches[], risk_score}
  - Update data-service to store and index reasoning traces
  - Add API endpoint in data-service: GET /api/v1/trades/{id}/explanation
- **Deliverables:**
  - execute-service/app/order/reasoning_trace.py — trace builder
  - data-service/data_service/app/routes/explanations.py — explanation API
  - Updated trade_models.py — reasoning_trace in metadata schema

#### Task 4.2 — Dashboard: Trade Explanation Cards
- **Profile:** frontend-dev
- **Complexity:** M
- **Dependencies:** Task 4.1
- **Description:**
  - Trade detail view with "Why This Trade?" card
  - Components: embedding similarity to past trades, news sentiment heatmap, risk score, agent confidence bars
  - "Replay" button, calls simulation-service for counterfactual analysis
  - Recharts for confidence visualization + lightweight-charts for heatmaps
- **Deliverables:**
  - dashboard/components/TradeExplanationCard.tsx — explanation card
  - dashboard/components/TradeReplay.tsx — replay simulation
  - dashboard/app/trades/[id]/page.tsx — trade detail page (new route)

---

### Feature 6: AI Twin + Strategy Lab

#### Task 6.1 — Twin Profile Builder + Strategy Lab Backend
- **Profile:** quant
- **Complexity:** L
- **Dependencies:** Task 1.1, Task 5.1
- **Description:**
  - Extend embedding-service to build user-specific embedding profiles from trade history + risk preferences
  - Implement twin prediction: given market conditions, predict user's likely action via embedding similarity
  - Strategy Lab: accept natural language strategy descriptions, formalize as backtestable rules, run via simulation-service
  - LLM suggests improvements based on twin analysis
  - Store twin profiles and strategy experiments in Postgres
- **Deliverables:**
  - embedding-service/app/twin.py — twin profile builder
  - trading-platform/reasoning-service/app/strategy_lab.py — strategy formalization + suggestions
  - Alembic migrations for user_twin_profiles, strategy_experiments tables
  - trading-platform/reasoning-service/requirements.txt updates

#### Task 6.2 — Dashboard: AI Twin + Strategy Lab UI
- **Profile:** frontend-dev
- **Complexity:** M
- **Dependencies:** Task 6.1
- **Description:**
  - "My Twin" tab app/twin/page.tsx — twin profile visualization, accuracy score, predicted behavior
  - Strategy Lab: form for strategy description, backtest results visualization, AI suggestions
  - Comparison view: user actual behavior vs. twin predictions
- **Deliverables:**
  - dashboard/components/TwinProfile.tsx — twin visualization
  - dashboard/components/StrategyLab.tsx — strategy definition + results
  - dashboard/app/twin/page.tsx — twin page
  - dashboard/app/api/twin/route.ts — API proxy

---

### Feature 8: Weekly Reports + AI Widgets

#### Task 8.1 — Reporting Service + Cron Job
- **Profile:** backend-dev
- **Complexity:** M
- **Dependencies:** Task 2.1, Task 1.1
- **Description:**
  - Create reporting-service/ FastAPI microservice
  - Weekly cron: pull PnL, trades, missed opportunities, news sentiment, generate narrative via LLM
  - Report template system with configurable sections
  - Store reports in weekly_reports table
  - Custom widget endpoint: POST /widgets accepts user prompt, returns widget config JSON
- **Deliverables:**
  - trading-platform/reporting-service/app.py — entry point
  - trading-platform/reporting-service/app/reporter.py — weekly report generator
  - trading-platform/reporting-service/app/widgets.py — custom widget generator
  - trading-platform/reporting-service/cron/weekly_report.py — cron job script
  - trading-platform/reporting-service/Dockerfile
  - Alembic migrations for weekly_reports, custom_widgets tables
- **Kafka topics:** trading-platform.reports.weekly.v1

#### Task 8.2 — Dashboard: Reports + Dynamic Widget Renderer
- **Profile:** frontend-dev
- **Complexity:** M
- **Dependencies:** Task 8.1
- **Description:**
  - Weekly reports page app/reports/page.tsx — narrative display with charts
  - Dynamic widget renderer: accepts JSON widget config, renders appropriate component
  - "Add Widget" prompt: user types natural language request, saves config, renders immediately
  - Widget types: live data cards, exposure comparisons, PnL trackers, opportunity summaries
- **Deliverables:**
  - dashboard/components/WeeklyReport.tsx — report display
  - dashboard/components/WidgetRenderer.tsx — dynamic widget component
  - dashboard/components/WidgetPrompt.tsx — "Add Widget" input
  - dashboard/app/reports/page.tsx — reports page
  - dashboard/app/api/reports/route.ts — API proxy
  - dashboard/app/api/widgets/route.ts — widget API

#### Task 8.3 — Reporting Service K8s CronJob
- **Profile:** devops
- **Complexity:** S
- **Dependencies:** Task 8.1
- **Description:**
  - Deploy reporting-service as K8s Deployment + CronJob (weekly Sunday run)
  - K8s manifests in gcloud-lab PR to master
- **Deliverables:**
  - gcloud-lab/k8s/customer1/reporting-service-{deployment,service}.yaml
  - gcloud-lab/k8s/customer1/reporting-service-cronjob.yaml
  - PR to gcloud-lab master

---

## Security Hardening Tasks (Pre-AI Features)

These should be completed BEFORE enabling autonomous AI features:

#### Task S1 — Execute Service Security Remediation
- **Profile:** sec-ops
- **Complexity:** M
- **Dependencies:** None
- **Description:**
  - Add JWT secret validation (reject default) — [CRITICAL]
  - Add position size limits to config + validation — [HIGH]
  - Add daily loss circuit breaker (Redis-backed) — [HIGH]
  - Add circuit breaker on Solana execution — [HIGH]
  - Add token safety filters — [HIGH]
  - Fix send_sol() from_pubkey — [MEDIUM]
  - Add transaction confirmation polling — [MEDIUM]
  - Add HTTP client connection pooling — [MEDIUM]
  - Reject devnet RPC in production — [MEDIUM]
  - Add API rate limiting middleware — [MEDIUM]
- **Deliverables:**
  - execute-service/app/config.py — updated with risk limits + validators
  - execute-service/app/middleware/rate_limiter.py — rate limiting
  - execute-service/app/risk/ — circuit breaker, daily loss tracker, token safety
  - execute-service/app/executors/solana.py — fixes + pooling
  - Updated tests

#### Task S2 — Encryption At Rest for AI Data
- **Profile:** sec-ops
- **Complexity:** S
- **Dependencies:** None
- **Description:**
  - Enable column-level encryption for: copilot_conversations.messages, weekly_reports.narrative_text, user_twin_profiles.embedding_vector
  - Use existing SOPS/age key infrastructure or Postgres pgcrypto extension
  - Document encryption key rotation procedure
- **Deliverables:**
  - Alembic migrations with encrypted columns
  - data_infrastructure/crypto/ — encryption utility
  - Runbook for key rotation

---

## DevOps: Shared Infrastructure

#### Task D1 — RediSearch Enablement
- **Profile:** devops
- **Complexity:** S
- **Dependencies:** None
- **Description:**
  - Enable RediSearch module on existing Redis deployment
  - Configure HNSW index for 768-dimensional vectors
  - Update K8s manifests in gcloud-lab
- **Deliverables:**
  - Updated Redis StatefulSet/Deployment in gcloud-lab
  - RediSearch configuration

#### Task D2 — New Service Dockerfiles + CI/CD
- **Profile:** devops
- **Complexity:** S
- **Dependencies:** None
- **Description:**
  - Add Dockerfiles for: reasoning-service, swarm-service, simulation-service, reporting-service
  - Update CI/CD workflows in trading-platform/.github/workflows/ to build all services
  - Container registry push configuration
- **Deliverables:**
  - Dockerfiles for all 4 new services
  - Updated build-test.yml and build-push.yml

---

## Dependency Graph (Task-Level)

```
Phase 0 (Prerequisites)
+-- S1: Security Remediation (sec-ops) - parallel
+-- D1: RediSearch Enablement (devops) - parallel
+-- D2: Dockerfiles + CI/CD (devops) - parallel
+-- 2.2: vLLM GPU Deployment (devops) - parallel

Phase 1 (Quick Wins)
+-- 1.1: Embedding Service Extension (backend-dev)
+-- 1.2: Data Service Indexer (backend-dev) ----+ depends on 1.1
+-- 1.3: Dashboard Search UI (frontend-dev) ----+ depends on 1.1
+-- 2.1: Reasoning Service (backend-dev) -------+ depends on 1.1
+-- 2.3: Dashboard Co-Pilot (frontend-dev) -----+ depends on 2.1

Phase 2 (Core AI)
+-- 3.1: Swarm Orchestrator (backend-dev) ------+ depends on 2.1
+-- 3.2: Dashboard Agent Hub (frontend-dev) ----+ depends on 3.1
+-- 3.3: Swarm K8s Deployment (devops) ---------+ depends on 3.1
+-- 5.1: Simulation Engine (quant) -------------+ depends on 1.2
+-- 5.2: Dashboard Simulator (frontend-dev) ----+ depends on 5.1
+-- 7.1: Opportunity Scanner (backend-dev) -----+ depends on 1.2
+-- 7.2: Dashboard Opportunities (frontend-dev) + depends on 7.1

Phase 3 (Advanced)
+-- 4.1: Reasoning Metadata (backend-dev) ------+ depends on 1.1, 3.1
+-- 4.2: Trade Explanation Cards (frontend-dev) + depends on 4.1
+-- 6.1: Twin + Strategy Lab Backend (quant) --+ depends on 1.1, 5.1
+-- 6.2: Dashboard Twin UI (frontend-dev) -----+ depends on 6.1
+-- 8.1: Reporting Service (backend-dev) ------+ depends on 2.1, 1.1
+-- 8.2: Dashboard Reports + Widgets (frontend) + depends on 8.1
+-- 8.3: Reporting CronJob (devops) -----------+ depends on 8.1
```

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Total tasks | 18 |
| New services | 4 (reasoning, swarm, simulation, reporting) |
| Extended services | 4 (embedding, data, execute, news) |
| Dashboard pages | 6 (search, copilot, agents, simulator, twin, reports) + 1 (trade detail) |
| New Kafka topics | ~15 |
| New Postgres tables | ~8 |
| New K8s manifests | ~15 (across gcloud-lab PRs) |

### By Profile
| Profile | Tasks | Total Complexity |
|---------|-------|-----------------|
| backend-dev | 8 | 4L, 3M, 1S |
| frontend-dev | 8 | 2L, 5M, 1S |
| devops | 4 | 2M, 2S |
| quant | 2 | 2L |
| sec-ops | 2 | 1M, 1S |

### Estimated Effort
| Phase | Duration | Team |
|-------|----------|------|
| Phase 0 (Prerequisites) | 1-2 weeks | sec-ops + devops (parallel) |
| Phase 1 (Quick Wins) | 2-3 weeks | backend-dev + frontend-dev |
| Phase 2 (Core AI) | 3-4 weeks | backend-dev + quant + frontend-dev + devops |
| Phase 3 (Advanced) | 2-3 weeks | quant + frontend-dev + backend-dev |

---

## Sources

- Architecture plan: ARCHITECTURE-PLAN.md (same directory)
- Feature proposals: /home/hermes/.hermes/cache/documents/doc_31acea41009a_Defi terminal upgrades.md
- Codebase: trading-platform/ in hermes-projects repo
- Security review: trading-platform/docs/security-review.md
