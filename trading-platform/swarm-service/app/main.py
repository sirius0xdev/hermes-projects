"""Swarm service — FastAPI entry point."""
from fastapi import FastAPI

app = FastAPI(title="swarm-service", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}
