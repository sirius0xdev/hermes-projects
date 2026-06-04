# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

# Prevent Python from writing pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies (minimal for hyperliquid/np compatibility if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser

WORKDIR /app

# Copy requirements first for better layer caching
COPY --chown=appuser:appuser requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (only what's needed at runtime)
COPY --chown=appuser:appuser main.py \
    scanners.py \
    quant.py \
    executor.py \
    risk.py \
    planner.py \
    wallet_tracker.py \
    db.py \
    run.sh \
    .env.example \
    ./
COPY --chown=appuser:appuser dashboard ./dashboard/

# Create directory for SQLite database and logs (persisted via volume)
RUN mkdir -p /app/data /app/logs && chown -R appuser:appuser /app/data /app/logs

# Use non-root user
USER appuser

# Expose dashboard port
EXPOSE 8000

# Set PYTHONPATH so internal imports work when submodule is run as script
ENV PYTHONPATH=/app

# Default environment (override via docker run -e)
ENV DRY_RUN=true \
    STARTING_EQUITY_USD=20 \
    RISK_PCT_MIN=0.05 \
    RISK_PCT_MAX=0.15 \
    MAX_DAILY_LOSS_PCT=0.25 \
    LEVERAGE=5 \
    MAX_CONCURRENT_POSITIONS=1 \
    SCAN_INTERVAL_SECONDS=30 \
    BASE_DIR=/app \
    DB_PATH=/app/data/bot.sqlite \
    PID_PATH=/app/data/bot.pid \
    LOG_PATH=/app/logs/bot.log

# Health check for dashboard
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/status', timeout=3)" || exit 1

# Run the dashboard (which can start/stop the bot via API)
CMD ["bash", "run.sh"]