# Runbook: embedding-service

## Startup
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Required Env Vars
| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_REDIS_URL` | `redis://redis-master:6379/0` | Redis connection URL |
| `EMBEDDING_VECTOR_INDEX_NAME` | `embedding_index` | RediSearch index name |
| `EMBEDDING_VECTOR_INDEX_DIMENSIONS` | `768` | Embedding vector dimensions |
| `EMBEDDING_MODEL_PATH` | `nomic-ai/nomic-embed-text-v1.5` | HuggingFace model path |

## Health
```bash
curl http://localhost:8000/health
# {"status":"healthy","model":"nomic-ai/nomic-embed-text-v1.5","dimensions":768,"ready":true,"vector_store":"connected"}
```

## Smoke Test
1. `curl http://localhost:8000/health` — should return `"ready":true`
2. `curl http://localhost:8000/v1/models` — should list nomic-embed-text-v1.5
3. `curl http://localhost:8000/v1/index/stats` — should return index name and doc_count
4. Index a document:
   ```bash
   curl -X POST http://localhost:8000/v1/index \
     -H 'Content-Type: application/json' \
     -d '{"entity_type":"news","entity_id":"n1","embedding":[0.1]*768,"text":"Bitcoin rallies"}'
   ```
5. Semantic search:
   ```bash
   curl -X POST http://localhost:8000/v1/search \
     -H 'Content-Type: application/json' \
     -d '{"query_embedding":[0.1]*768,"top_k":5}'
   ```

## API Endpoints
| Method | Path | Description |
|---|---|---|
| POST | `/v1/embeddings` | Create embeddings (OpenAI-compatible) |
| GET | `/v1/models` | List models (OpenAI-compatible) |
| POST | `/v1/search` | Semantic search with filters |
| POST | `/v1/index` | Index a single document |
| POST | `/v1/index/batch` | Batch index (max 500 docs) |
| DELETE | `/v1/index/{type}/{id}` | Remove a document |
| GET | `/v1/index/stats` | Index statistics |
| GET | `/health` | Health check |

## Common Failures
- `"vector_store":"unavailable"` in health: Redis not reachable at `EMBEDDING_REDIS_URL`. Service still serves embeddings but search is disabled.
- `RuntimeError: VectorStore not initialized`: Index creation failed on startup. Check Redis logs for RediSearch module availability.
- 503 on search/index endpoints: Vector store init failed gracefully; restart service once Redis is healthy.

## What Was Tried
- **Approach A:** `from redisvl import Redis, VectorIndex` — failed with `ModuleNotFoundError`. Root cause: `redisvl` restructured in v0.3.6; imports are `redisvl.index`, `redisvl.query`, `redisvl.schema`.
- **Approach B (chosen):** Direct imports from submodules (`redisvl.index.VectorIndex`, etc.) — works with `redisvl==0.3.6`.
- **Dockerfile COPY:** Initial Dockerfile only copied `app.py` — the `app/` package (config, vector_store, routes) and tests were missing from the image. Fixed by adding explicit COPY for `app/` and `tests/` directories.
