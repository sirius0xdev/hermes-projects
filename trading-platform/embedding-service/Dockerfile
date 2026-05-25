# Multi-stage build for embedding-service (nomic-embed-text-v1.5)
FROM python:3.12-slim AS builder
WORKDIR /build
COPY trading-platform/embedding-service/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN useradd -m --uid 1000 --system appuser && mkdir -p /app /tmp && chown appuser:appuser /app /tmp

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=appuser:appuser trading-platform/embedding-service/app.py .

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
