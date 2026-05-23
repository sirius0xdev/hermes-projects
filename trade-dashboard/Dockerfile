FROM python:3.13-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY trade-dashboard/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY trade-dashboard/app/ ./app/
COPY trade-dashboard/alembic.ini .
COPY trade-dashboard/alembic/ ./alembic/

EXPOSE 8000
ENV PYTHONPATH=/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
