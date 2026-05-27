# Architecture Plan — Trading Platform AI Upgrades

**Date:** 2026-05-27
**Author:** researcher (Kanban t_19872b62)
**Scope:** 8 feature proposals for the trading platform (Next.js + FastAPI on GKE)

---

## Current Architecture Snapshot

| Component | Technology | Port | Notes |
|-----------|-----------|------|-------|
| Dashboard | Next.js 14, Tailwind, lightweight-charts | 3000 | App router, pages: /, /auth, /bot, /market, /news, /portfolio, /settings, /trade, /trades |
| Data Service | FastAPI, SQLAlchemy (asyncpg), Redis, Kafka | 8000 | Market data pipeline, Postgres + Redis + Kafka consumers |
| Execute Service | FastAPI, mTLS, SIWE/SIWS auth | 8002 | Hyperliquid + Solana execution, order management |
| News Service | FastAPI, TextBlob NLP | 8000 | CryptoPanic/GNews connector, sentiment/signal analysis |
| Embedding Service | FastAPI, nomic-embed-text-v1.5 (768d) | 8001 | OpenAI-compatible /v1/embeddings endpoint, CPU inference |
| Data Infrastructure | Shared Python lib | — | Models (trades, fills, positions, PnL, market_data), Kafka/Redis config, protobuf schemas |
| Kafka (Strimzi) | v1 API | — | Topics: trading-platform.market.prices.v1, .orderbook.v1, .trades.v1, .news.feed.v1, .news.analysis.v1, .signals.trading.v1 |
| PostgreSQL (CNPG) | customer1 namespace | — | Tables: orders, fills, positions, position_history, market_data, fills, pnl |
| Redis | Caching + vector search capable | — | Rate limiting, sliding window cache |

**Existing models:** Order, Fill, Position, PositionHistory, MarketData, PnL, Fill models with proper indexing, JSONB metadata, and GiST indexes for time-range queries.

**Security baseline:** mTLS inter-service, SOPS-encrypted K8s secrets, SIWE wallet auth, NetworkPolicy default-deny. Open issues: no circuit breakers, no position size limits, JWT default secret (Critical).

---

## Feature 1: RAG-Powered "Market Memory" + Semantic Trade Search

### Services Affected
- **Extend:** embedding-service — add /semantic-search endpoint + vector storage layer
- **Extend:** data-service — background indexer that embeds trades, news articles, and market events
- **Extend:** dashboard — search bar component with real-time results

### Data Flow
1. data-service watches orders, fills, positions, position_history tables via DB triggers or polling
2. On new/closed trade: serialize trade context (symbol, side, entry/exit, PnL, market conditions, news sentiment at time) → send to embedding-service for vectorization
3. Vectors stored in Redis (vector search via RediSearch) — no new DB dependency
4. News articles: news-service publishes to trading-platform.news.feed.v1 → data-service consumer embeds article text + analysis results
5. /semantic-search accepts natural language query → embeds query → Redis ANN search → returns matching trades/articles with similarity scores

### New Kafka Topics
- trading-platform.embeddings.index.v1 — events to index (trade_closed, article_published, signal_generated)

### New Database Tables
- embeddings (id, entity_type, entity_id, embedding_vector, metadata JSONB, created_at)
- Index: vector similarity index in Redis (FLAT/HNSW)

### Tech Stack
- **Vector storage:** Redis with RediSearch (already running, no new infra) — fallback: Qdrant if Redis vector search insufficient
- **Embedding model:** Keep nomic-embed-text-v1.5 (768d) — already proven, CPU-compatible
- **Dashboard:** Server-side API route app/api/search/route.ts streaming results via fetch polling or SSE

### Dependencies
- Requires embedding-service to be GPU-capable or accept CPU latency (currently CPU-only, fine for search at <100ms)

### Security
- No wallet signing needed — reads from existing data store
- Semantic search results are read-only, no execution risk

---

## Feature 2: Conversational AI Co-Pilot (Chat + Voice)

### Services Affected
- **New:** reasoning-service — FastAPI microservice for LLM-based reasoning
- **Extend:** execute-service — receive one-click execution commands from co-pilot
- **Extend:** dashboard — chat interface page (/copilot), voice input component

### Data Flow
1. User types/ speaks query → dashboard → reasoning-service (REST)
2. reasoning-service fetches context from:
   - embedding-service — semantic search of relevant trades/news (Feature 1)
   - data-service — current portfolio, positions, market data
   - execute-service — open orders, recent fills
3. LLM reasons over RAG context → structured response with optional trade recommendation
4. Response streamed to dashboard via Server-Sent Events (SSE)
5. User clicks "Execute" → dashboard → execute-service (standard trade flow with wallet signing)

### New Kafka Topics
- trading-platform.copilot.queries.v1 — query history for audit
- trading-platform.copilot.responses.v1 — responses for audit

### New Database Tables
- copilot_conversations (id, wallet_address, messages JSONB, created_at, updated_at)

### Tech Stack
- **LLM:** vLLM on RTX 6000 (already available) — serve Qwen2.5-7B-Instruct or Llama-3.1-8B-Instruct for low-latency reasoning. For complex queries, route to larger model.
- **Streaming:** SSE from reasoning-service to dashboard (already have Kafka real-time plumbing)
- **Voice:** Web Speech API (client-side, no backend cost) for browser-based voice input
- **Structured output:** LLM returns JSON with reasoning, recommendation, trade_action (optional) fields

### Dependencies
- **Blocks on Feature 1** (needs semantic search for RAG context)
- Requires vLLM deployment on RTX 6000

### Security
- **Wallet signing remains client-side** — reasoning-service NEVER handles private keys
- Trade execution always goes through execute-service with SIWE auth
- LLM prompt never contains raw private keys — only public wallet address and portfolio state
- PII: conversation history contains strategy language — encrypt at rest

---

## Feature 3: Multi-Agent Swarm with Visible "Debate" Log

### Services Affected
- **New:** swarm-service — orchestrates agent pods
- **New pods:** scout-agent, risk-guardian-agent, historian-agent (specialized microservices, scaled from reasoning-service base)
- **Extend:** execute-service — becomes the "Executor" agent in the swarm
- **Extend:** dashboard — "Agent Hub" page showing live debate transcript + confidence scores

### Data Flow
1. Market event (e.g., price spike, funding rate change) → data-service publishes to trading-platform.market.prices.v1
2. swarm-service detects event → dispatches to all agents
3. Each agent publishes analysis to its own Kafka topic:
   - trading-platform.agents.scout.v1 — opportunity scan results
   - trading-platform.agents.risk.v1 — risk assessment (liquidation distance, funding, exposure)
   - trading-platform.agents.historian.v1 — historical similarity matches
   - trading-platform.agents.executor.v1 — execution plan
4. swarm-service aggregates → consensus or dissent → final recommendation
5. Debate log streamed to dashboard via SSE

### New Kafka Topics
- trading-platform.agents.scout.v1
- trading-platform.agents.risk.v1
- trading-platform.agents.historian.v1
- trading-platform.agents.executor.v1
- trading-platform.agents.consensus.v1 — final aggregated decision

### New Database Tables
- agent_debates (id, trigger_event, agent_responses JSONB, consensus JSONB, created_at)

### Tech Stack
- **Agent framework:** Custom lightweight FastAPI agents — no heavy framework needed; each agent is a Kafka consumer with LLM reasoning layer
- **LLM:** Same vLLM instance — different system prompts per agent
- **Dashboard:** Live debate transcript using lightweight-charts for confidence visualization + Tailwind chat-style UI

### Dependencies
- Blocks on Feature 2 (needs reasoning-service infrastructure)
- Blocks on Feature 1 (historian agent needs semantic search)

### Security
- Agent recommendations are advisory only — execution still requires human approval or pre-configured risk parameters
- Risk Guardian agent can veto based on hard limits (position size, daily loss, liquidation distance)

---

## Feature 4: Explainable AI "Why This Trade?" Replay Cards

### Services Affected
- **Extend:** data-service — capture reasoning metadata on every trade event
- **Extend:** execute-service — attach reasoning_trace to order metadata JSONB
- **Extend:** dashboard — trade detail cards with explanation, heatmap, replay button

### Data Flow
1. When trade is submitted (by swarm or manual), execute-service enriches metadata JSONB with:
   - reasoning_trace: {trigger, signals_used, agent_confidence, embedding_matches[], risk_score}
2. data-service stores enriched metadata in orders.metadata (already JSONB)
3. Dashboard renders "Why This Trade?" card:
   - Embedding similarity to past trades (from Feature 1)
   - News sentiment at time of trade (from Feature 5/news-service)
   - Risk score and agent confidence
   - "Replay" button → calls simulation-service (Feature 5) for counterfactual

### New Database Tables
- No new tables — extends existing orders.metadata JSONB and fills.metadata JSONB
- New index: orders.metadata @> '{"reasoning_trace": true}' for fast filtering

### Tech Stack
- **Visualization:** lightweight-charts (already installed) + Recharts for decision trees/confidence bars
- **Replay:** Integration with simulation-service (Feature 5) for "what would have happened" analysis

### Dependencies
- Blocks on Feature 1 (needs embedding matches)
- Blocks on Feature 3 (needs agent reasoning traces)
- Partial dependency on Feature 5 (replay button)

### Security
- Read-only feature — no execution risk
- Reasoning traces may contain strategy logic — consider encrypting at rest for competitive sensitivity

---

## Feature 5: Goal-Based "What-If" Simulator + Auto-Rebalancer

### Services Affected
- **New:** simulation-service — FastAPI service for Monte Carlo + historical replay
- **Extend:** dashboard — interactive simulator cards, goal-setting UI
- **Extend:** data-service — provide historical Kafka replay data

### Data Flow
1. User sets goal (e.g., "$50K by EOY, <15% max drawdown") → stored in user_goals table
2. Simulator pulls historical data from:
   - data-service — market history from trading-platform.market.prices.v1 Kafka replay + Postgres
   - execute-service — current positions, PnL history
3. Monte Carlo engine runs N scenarios → returns distribution of outcomes
4. "What-if" scenarios: modify one variable (e.g., "if SOL funding flips") → re-run
5. Auto-rebalancer: when simulation shows goal deviation, generate rebalancing trades → submit via execute-service

### New Kafka Topics
- trading-platform.simulation.requests.v1
- trading-platform.simulation.results.v1

### New Database Tables
- user_goals (id, wallet_address, target_value, target_date, max_drawdown_pct, strategy_params JSONB, created_at)
- simulation_runs (id, goal_id, scenario JSONB, results JSONB, created_at)

### Tech Stack
- **Simulation engine:** Python with numpy for Monte Carlo, historical replay from Kafka topic offsets
- **Kafka replay:** Use Kafka's seek_to_offset API to replay historical market data streams
- **Dashboard:** Interactive sliders + lightweight-charts for distribution visualization

### Dependencies
- Requires Feature 1 (historical data indexed/available)
- No dependency on Feature 2 or 3 (can run standalone)

### Security
- Auto-rebalancer trades go through execute-service with existing risk controls (circuit breakers, position limits from security review)
- Goals are wallet-scoped — no cross-user data leakage

---

## Feature 6: Hyper-Personal AI Twin + Strategy Lab

### Services Affected
- **Extend:** embedding-service — user-specific embedding space
- **Extend:** reasoning-service — twin model storage + inference
- **Extend:** dashboard — "My Twin" tab with promptable experiments
- **New:** simulation-service — backtesting engine (shared with Feature 5)

### Data Flow
1. Build phase: embedding-service ingests all user trades, risk preferences, PnL outcomes → creates user-specific embedding profile
2. Twin model: reasoning-service trains a lightweight classifier (or fine-tunes small model) on user's trade patterns → produces "twin" that predicts user's likely action for any market condition
3. Strategy Lab: User describes strategy → reasoning-service formalizes it → simulation-service backtests against historical data → LLM suggests improvements based on twin analysis
4. Results stored in strategy_lab table

### New Kafka Topics
- trading-platform.twin.updates.v1 — twin model update events

### New Database Tables
- user_twin_profiles (id, wallet_address, embedding_vector, strategy_params JSONB, accuracy_score, updated_at)
- strategy_experiments (id, wallet_address, strategy_definition JSONB, backtest_results JSONB, ai_suggestions JSONB, created_at)

### Tech Stack
- **Twin model:** Start with rule-based + embedding similarity approach (no training needed). User's trade patterns encoded as embeddings; new scenarios compared via cosine similarity.
- **Backtesting:** Reuse simulation-service from Feature 5 with strategy-specific replay logic
- **Dashboard:** Form-based strategy definition + results visualization

### Dependencies
- Blocks on Feature 1 (needs embeddings)
- Blocks on Feature 5 (needs simulation-service)
- Partial dependency on Feature 2 (LLM for suggestions)

### Security
- Twin profile is personal data — encrypt at rest
- Strategy experiments are read-only until user executes — no autonomous risk

---

## Feature 7: Proactive Cross-Chain Opportunity Engine (Hyperliquid ↔ Solana)

### Services Affected
- **Extend:** data-service — new Kafka consumers for cross-chain arbitrage/yield detection
- **Extend:** embedding-service — opportunity vector embeddings
- **Extend:** dashboard — "Opportunities" widget with one-click execution
- **Extend:** execute-service — execute cross-chain trades

### Data Flow
1. data-service continuously monitors:
   - Solana lending yields (Aave, Solend, etc.)
   - Hyperliquid funding rates
   - Price differentials across chains
2. When opportunity detected (e.g., 3.2% delta-neutral arb): publish to trading-platform.opportunities.v1
3. Opportunity embedded via embedding-service → similarity search against historical opportunities that were/weren't profitable
4. Alert sent to dashboard widget: "3.2% edge detected — execute now?"
5. One-click → execute-service executes both legs (Solana + Hyperliquid) atomically

### New Kafka Topics
- trading-platform.opportunities.v1 — detected opportunities with edge calculations

### New Database Tables
- opportunities (id, opportunity_type, chain_from, chain_to, edge_pct, conditions JSONB, status, created_at, executed_at)

### Tech Stack
- **Detection:** Rule-based scanners in data-service with configurable thresholds
- **Embedding:** Opportunity vectors for similarity matching (was this type of opportunity profitable before?)
- **Dashboard:** Real-time alert widget using SSE (existing plumbing)

### Dependencies
- Blocks on Feature 1 (needs opportunity embeddings for historical matching)
- No dependency on Feature 2, 3, or 6

### Security
- Cross-chain execution requires dual-chain signatures — wallet signing remains client-side
- Opportunity execution goes through existing execute-service risk controls
- Edge calculations should include slippage and gas estimates before presenting to user

---

## Feature 8: Narrative Weekly Reports + Custom AI Widgets

### Services Affected
- **New:** reporting-service — FastAPI service with cron jobs
- **Extend:** embedding-service — narrative generation context
- **Extend:** dashboard — weekly report view + dynamic widget renderer

### Data Flow
1. Every Sunday, reporting-service runs cron job:
   - Pulls weekly PnL, trades, missed opportunities from Postgres
   - Pulls news sentiment trends from news-service
   - Pulls embedding-based pattern matches from embedding-service
2. LLM generates narrative: "Your portfolio outperformed because..." with data-backed claims
3. Report stored in weekly_reports table, pushed to dashboard
4. Custom AI Widgets: User prompts "Add a live card showing X" → reporting-service generates widget config → dashboard renders dynamic component

### New Kafka Topics
- trading-platform.reports.weekly.v1 — completed reports

### New Database Tables
- weekly_reports (id, wallet_address, week_start, week_end, narrative_text, metrics JSONB, created_at)
- custom_widgets (id, wallet_address, widget_config JSONB, prompt, created_at)

### Tech Stack
- **Narrative generation:** LLM (vLLM) with structured prompt template + data context
- **Widget rendering:** JSON-based widget config → dynamic Next.js component renderer
- **Cron:** K8s CronJob running reporting-service container, or APScheduler in the service itself

### Dependencies
- Blocks on Feature 1 (needs embeddings for pattern context)
- Blocks on Feature 2 (needs LLM infrastructure)
- Partial dependency on Feature 4 (can reference "Why This Trade?" data)

### Security
- Reports may contain strategy insights — encrypt at rest
- Custom widgets are configuration-only — no code injection risk (JSON config, not rendered JS from user input)

---

## Feature Dependency Graph

```
Phase 1 (Quick Wins)
+-- Feature 1: RAG Semantic Search + Market Memory
+-- Feature 2: Conversational AI Co-Pilot
       +-- depends on Feature 1

Phase 2 (Core AI)
+-- Feature 3: Multi-Agent Swarm
|      +-- depends on Feature 1, Feature 2
+-- Feature 5: Simulator + Auto-Rebalancer
|      +-- depends on Feature 1
+-- Feature 7: Cross-Chain Opportunity Engine
       +-- depends on Feature 1

Phase 3 (Advanced)
+-- Feature 4: Explainable AI Replay Cards
|      +-- depends on Feature 1, Feature 3, (partial: Feature 5)
+-- Feature 6: AI Twin + Strategy Lab
|      +-- depends on Feature 1, Feature 5, (partial: Feature 2)
+-- Feature 8: Weekly Reports + AI Widgets
       +-- depends on Feature 1, Feature 2, (partial: Feature 4)
```

---

## New Services Summary

| New Service | Port | Tech | Purpose | Phase |
|------------|------|------|---------|-------|
| reasoning-service | 8003 | FastAPI + vLLM client | LLM reasoning, RAG queries, structured output | Phase 1 |
| swarm-service | 8004 | FastAPI + Kafka | Agent orchestration, consensus | Phase 2 |
| simulation-service | 8005 | FastAPI + numpy | Monte Carlo, historical replay | Phase 2 |
| reporting-service | 8006 | FastAPI + APScheduler | Weekly reports, narrative gen | Phase 3 |

**Agent pods** (scaled from reasoning-service base): scout-agent, risk-guardian-agent, historian-agent — run as separate K8s Deployments, each consuming/writing to its own Kafka topic.

---

## Infrastructure Recommendations

### vLLM Deployment (RTX 6000)
- Deploy vLLM as a K8s StatefulSet with GPU node selector
- Model: Qwen2.5-7B-Instruct (balanced speed/quality for trading domain)
- Quantization: FP8 or INT4 to fit on single RTX 6000 (16GB VRAM)
- Endpoint: OpenAI-compatible /v1/chat/completions
- Serve both reasoning-service and reporting-service from same instance

### Redis Vector Search
- Enable RediSearch module on existing Redis deployment
- Use HNSW index type for ANN search (better recall than FLAT at scale)
- Initial dimension: 768 (matching nomic-embed-text-v1.5)
- Separate Redis DB or index prefix for embeddings vs. caching

### Kafka Topic Naming Convention
- All new topics follow trading-platform.<domain>.<entity>.v1 pattern
- Existing topics use v1 suffix — new topics continue this convention

### Postgres Schema Extensions
- All new tables use wallet_address for user scoping (consistent with existing models)
- JSONB for flexible metadata (follows existing pattern)
- UUID primary keys for public-facing entities, integer for internal tracking

---

## Security Considerations (Cumulative)

1. **Wallet signing always client-side** — no service holds private keys. All execution goes through execute-service with SIWE auth.
2. **LLM prompts never contain PII** — only wallet address, portfolio state, and anonymized trade data.
3. **mTLS between all new services** — follow existing pattern from execute-service.
4. **Rate limiting on LLM endpoints** — prevent runaway token consumption from agent loops.
5. **Conversation/report encryption** — strategy insights are competitive intelligence; encrypt at rest with column-level encryption.
6. **Address pre-existing security findings** before enabling autonomous features: JWT secret validation, circuit breakers, position limits, daily loss limits (from security review).
7. **Agent recommendations are advisory** — even in "auto-execute" mode, Risk Guardian enforces hard limits (max position %, daily loss, liquidation distance).

---

## Sources

- Feature proposals: /home/hermes/.hermes/cache/documents/doc_31acea41009a_Defi terminal upgrades.md
- Codebase: trading-platform/ (embedding-service, execute-service, data-service, news-service, dashboard, data_infrastructure)
- Security review: trading-platform/docs/security-review.md
- Kafka topics: data-service/data_service/app/kafka/topics.py
- Data models: data_infrastructure/models/trade_models.py
- Dashboard deps: dashboard/package.json (lightweight-charts, Next.js 14, Tailwind)
- NLP analyzer: news-service/app/services/nlp/analyzer.py
