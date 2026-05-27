"""Reasoning service — FastAPI entry point."""
from fastapi import FastAPI

app = FastAPI(title="reasoning-service", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}
