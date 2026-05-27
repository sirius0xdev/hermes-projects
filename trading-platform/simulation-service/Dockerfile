# Multi-stage build for simulation-service (Monte Carlo + historical replay)
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*
COPY trading-platform/simulation-service/pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 liblapack3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m --system appuser

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=appuser:appuser trading-platform/simulation-service/app/ ./app/
COPY --chown=appuser:appuser trading-platform/simulation-service/pyproject.toml ./

USER appuser

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8006/health')" || exit 1

EXPOSE 8006

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
