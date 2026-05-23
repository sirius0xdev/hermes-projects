FROM python:3.12-slim AS builder
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"
COPY waitlist-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
RUN groupadd --system --gid 1000 appuser && \
    useradd --system --uid 1000 --gid 1000 --home /home/appuser appuser
WORKDIR /app

COPY --from=builder /venv /venv
COPY waitlist-api/main.py .

ENV PATH="/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

USER 1000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
