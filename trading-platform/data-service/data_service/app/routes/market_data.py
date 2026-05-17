"""Market data API — FastAPI routes backed by Redis cache + PostgreSQL.

Endpoints:
- GET  /api/v1/marketdata/price/{exchange}/{symbol}
- POST /api/v1/marketdata/price/batch
- GET  /api/v1/marketdata/orderbook/{exchange}/{symbol}
- GET  /api/v1/marketdata/candles/{exchange}/{symbol}/{interval}
- GET  /api/v1/marketdata/meta/{exchange}/{symbol}
- GET  /api/v1/marketdata/stats
- POST /api/v1/marketdata/invalidate/{exchange}/{symbol}
- POST /api/v1/marketdata/flush/{exchange}
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from data_service.app.cache.client import get_redis_client, shutdown_redis
from data_service.app.cache.service import CacheService
from data_service.app.schemas.market_data import (
    CacheStatsDTO,
    CandlesResponseDTO,
    OrderBookDTO,
    OrderBookEntryDTO,
    PriceDTO,
    PriceUpdateDTO,
    SymbolMetaDTO,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/marketdata", tags=["marketdata"])


def get_cache_service() -> CacheService:
    """Factory that builds a CacheService from the shared Redis client.

    In prod the shared client is initialized at startup.
    For testing, override with a mock Redis instance.
    """
    # Lazy lookup: if the singleton isn't connected, get_redis_client
    # will connect it. In tests, inject a different client at the
    # app dependency-override level.
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop yet (e.g. import-time), return None
        return None  # type: ignore[return-value]

    client_future = asyncio.ensure_future(get_redis_client())
    # This works because get_redis_client is idempotent and quick
    # if already connected.  In real usage the lifespan hook ensures
    # connect() was called before any request arrives.
    import asyncio

    return CacheService(None)  # placeholder — overridden in lifespan


# ── Helper: cache service from request ─────────────────────────────

CACHE_SVC: CacheService | None = None


async def _get_cache() -> CacheService:
    if CACHE_SVC is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis cache not initialized",
        )
    return CACHE_SVC


def set_cache_service(svc: CacheService) -> None:
    """Called by the lifespan hook after Redis connects."""
    global CACHE_SVC
    CACHE_SVC = svc


# ── Price endpoints ────────────────────────────────────────────────


@router.get("/price/{exchange}/{symbol}", response_model=PriceDTO)
async def get_price(exchange: str, symbol: str, cache: CacheService = Depends(_get_cache)):
    """Get current price for a symbol. Checks Redis cache first."""
    data = await cache.get_price(exchange, symbol)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cached price for {exchange}:{symbol}",
        )
    return PriceDTO(**data)


@router.post("/price/batch", status_code=status.HTTP_204_NO_CONTENT)
async def set_price_batch(updates: list[PriceUpdateDTO], cache: CacheService = Depends(_get_cache)):
    """Batch-update prices in cache (e.g. from a WebSocket feed)."""
    await cache.set_price_batch([u.model_dump(exclude_none=False) for u in updates])


# ── Order book endpoints ───────────────────────────────────────────


@router.get("/orderbook/{exchange}/{symbol}", response_model=OrderBookDTO)
async def get_orderbook(
    exchange: str,
    symbol: str,
    depth: int = 20,
    cache: CacheService = Depends(_get_cache),
):
    """Get cached order book snapshot."""
    data = await cache.get_orderbook(exchange, symbol, depth)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cached orderbook for {exchange}:{symbol}",
        )
    # Reconstruct nested DTOs
    bids = [OrderBookEntryDTO(price=b[0], quantity=b[1]) for b in data["bids"]]
    asks = [OrderBookEntryDTO(price=a[0], quantity=a[1]) for a in data["asks"]]
    return OrderBookDTO(
        exchange=data["exchange"],
        symbol=data["symbol"],
        depth=data["depth"],
        bids=bids,
        asks=asks,
        ts=data["ts"],
    )


# ── Candle / OHLC endpoints ────────────────────────────────────────


@router.get("/candles/{exchange}/{symbol}/{interval}", response_model=CandlesResponseDTO)
async def get_candles(
    exchange: str,
    symbol: str,
    interval: str,
    cache: CacheService = Depends(_get_cache),
):
    """Get cached OHLC candles for a symbol and interval."""
    candles = await cache.get_candles(exchange, symbol, interval)
    if candles is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cached candles for {exchange}:{symbol}:{interval}",
        )
    # Reconstruct response with full envelope
    raw = await cache.redis.get(f"candle:{exchange}:{symbol}:{interval}")
    from data_service.app.cache.service import _deserialize

    full = _deserialize(raw)
    return CandlesResponseDTO(
        exchange=full["exchange"],
        symbol=full["symbol"],
        interval=full["interval"],
        count=full["count"],
        candles=candles,
        ts=full["ts"],
    )


# ── Metadata endpoints ─────────────────────────────────────────────


@router.get("/meta/{exchange}/{symbol}", response_model=SymbolMetaDTO)
async def get_meta(exchange: str, symbol: str, cache: CacheService = Depends(_get_cache)):
    """Get cached exchange metadata for a symbol."""
    data = await cache.get_meta(exchange, symbol)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cached metadata for {exchange}:{symbol}",
        )
    return SymbolMetaDTO(
        exchange=data["exchange"],
        symbol=data["symbol"],
        meta={k: v for k, v in data.items() if k not in ("exchange", "symbol")},
    )


# ── Cache management endpoints ─────────────────────────────────────


@router.get("/stats", response_model=CacheStatsDTO)
async def get_stats(cache: CacheService = Depends(_get_cache)):
    """Return cache statistics."""
    stats = await cache.stats()
    return CacheStatsDTO(**stats)


@router.post("/invalidate/{exchange}/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def invalidate_cache(
    exchange: str,
    symbol: str,
    price: bool = True,
    orderbook: bool = True,
    candles: bool = True,
    cache: CacheService = Depends(_get_cache),
):
    """Invalidate cached data for a symbol (on price update, exchange maintenance, etc.)."""
    await cache.invalidate_on_update(exchange, symbol, price, orderbook, candles)


@router.post("/flush/{exchange}", response_model=int)
async def flush_exchange(exchange: str, cache: CacheService = Depends(_get_cache)):
    """Flush ALL cached data for an exchange. Admin-only operation."""
    return await cache.flush_exchange(exchange)
