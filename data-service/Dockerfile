FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data_infrastructure must be importable alongside data-service
ENV PYTHONPATH=/app:/app/..

EXPOSE 8004

CMD ["uvicorn", "app.kafka.consumer_service:app", "--host", "0.0.0.0", "--port", "8004"]
