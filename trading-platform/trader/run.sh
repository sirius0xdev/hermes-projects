#!/usr/bin/env bash
set -euo pipefail
cd /app
exec uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
