# Runbook: execute-service

## Overview
Trading execution microservice for Hyperliquid futures/spot, Solana on-chain execution, wallet auth (SIWE), order management. Uses Postgres (CNPG), mTLS between services.

**Fixed:** SQLite fallback regression in K8s (was using `sqlite+aiosqlite:////tmp/execute.db` instead of PG due to env var name mismatch between `trading-secrets` and pydantic `Settings`). Added `@model_validator(mode='before')` to map `POSTGRES_PASSWORD`/`EXECUTE_JWT_SECRET_KEY`/etc. Now correctly uses `postgresql+asyncpg://...`.

## Startup (Docker / K8s)
The service is deployed via Helm from gcloud-lab (source of truth). Image built from hermes-projects main via CI → ghcr.io/sirius0xdev/trading-execute-service:latest

**Local dev:**
```bash
cd trading-platform/execute-service
# Set dev env (SQLite fallback)
export DB_PASSWORD=""  # or omit
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**In K8s (after fix):**
- Env provided via ConfigMap + envFrom: trading-secrets
- /tmp mounted as emptyDir for any temp files
- readOnlyRootFilesystem: true + non-root user 1000

## Health Checks
- **Liveness:** `GET /health` → `{"status": "ok"}`
- **Readiness:** `GET /health/ready` → `{"status": "ready"}` (after executors init)
- **Live:** `GET /health/live`

```bash
# From inside pod
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/ready
```

## Smoke Test
1. Check pod: `kubectl get pods -n customer1 -l app=execute-service`
2. Logs: `kubectl logs -n customer1 -l app=execute-service --tail=30 | grep -E "(ERROR|database|postgres|startup)"`
   - Should see "Starting execution service...", no SQLite errors, successful PG connection.
3. Test auth/health from API gateway or directly.

Expected in logs: no "unable to open database file", uses postgresql+asyncpg.

## Common Failures & Fixes
- **"unable to open database file" / aiosqlite OperationalError:** Was caused by SQLite fallback due to missing DB_PASSWORD in env mapping. **Fixed** in config.py with model_validator. Verify with above test.
- **JWT_SECRET_KEY validation error:** Same root cause (EXECUTE_JWT_SECRET_KEY not mapped). Now handled.
- **Connection to "itself" / localhost:** Ensure DB_HOST is set to postgres-primary... via ConfigMap.
- **mTLS cert issues:** Check volumeMount for /etc/mtls from execute-service-mtls secret.
- **Startup fails on init_db():** Check CNPG status, user "execute" exists with privileges (DB init jobs in gcloud-lab).

**What was tried before this fix:**
- Updating only Helm deployment to inject DB_PASSWORD explicitly: avoided because gcloud-lab is source of truth for manifests; changes should be in app code when possible.
- Removing SQLite fallback entirely: rejected because local dev needs it (no DB required).
- Fixing only _ensure_sqlite_dir: addressed symptoms but not root cause (wrong DB mode in prod).

## Restart Procedure
```bash
kubectl rollout restart deployment execute-service -n customer1
kubectl rollout status deployment execute-service -n customer1
kubectl logs -f -n customer1 -l app=execute-service --tail=50
```

Verify no startup errors and database_url uses postgres (check logs for sqlalchemy or add debug log if needed).

Last updated: 2026-05-25 (Hermes Agent fix for env mapping)
