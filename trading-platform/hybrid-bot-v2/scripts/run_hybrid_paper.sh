#!/usr/bin/env bash
set -euo pipefail
cd /home/hermes/workspace/hermes-projects/trading-platform/hybrid-bot-v2
# Prefer project venv if present
if [ -f /home/hermes/workspace/.venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source /home/hermes/workspace/.venv/bin/activate
fi

ENV_FILE="data/hybrid.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

mkdir -p data
LOCKFILE="data/hybrid_paper.lock"
PIDFILE="data/hybrid.pid"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  holder=""
  if [ -f "$PIDFILE" ]; then
    holder=" pid=$(cat "$PIDFILE" 2>/dev/null || true)"
  fi
  echo "[run_hybrid_paper] another hybrid instance holds $LOCKFILE$holder — exit"
  exit 0
fi

# Refuse if other hybrid_bot.py already running outside this lock (orphans)
mapfile -t ORPHANS < <(pgrep -f '[p]ython.*hybrid_bot\.py' || true)
if [ "${#ORPHANS[@]}" -gt 0 ]; then
  echo "[run_hybrid_paper] orphan hybrid_bot.py PIDs: ${ORPHANS[*]} — kill them first"
  exit 1
fi

export HYB_DRY_RUN="${HYB_DRY_RUN:-true}"
export HYB_ALLOW_LIVE="${HYB_ALLOW_LIVE:-0}"
export HYB_COINS="${HYB_COINS:-BTC,xyz:GOLD}"
export HYB_SESSION="${HYB_SESSION:-hybrid-paper-p1-$(date +%Y%m%d)}"
export HYB_LOG_LEVEL="${HYB_LOG_LEVEL:-INFO}"

echo "[run_hybrid_v2] session=$HYB_SESSION coins=$HYB_COINS dry=$HYB_DRY_RUN log=/tmp/hybrid_vwap_orderflow_v2.log"
# Truncate log on clean start so multi-instance double-lines don't confuse ops
: > /tmp/hybrid_vwap_orderflow_v2.log
exec stdbuf -oL -eL python3 -u hybrid_bot.py 2>&1 | tee -a /tmp/hybrid_vwap_orderflow_v2.log
