"""Pydantic schema / DTOs for market data API.

These models define the request/response contracts for the
market data endpoints. They sit between the Redis cache layer
and the API consumer (trading bot, dashboard, etc.).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Price ──────────────────────────────────────────────────────────────


class PriceDTO(BaseModel):
    """Current price ticker for a symbol on an exchange."""

    exchange: str
    symbol: str
    bid: Optional[str] = None
    ask: Optional[str] = None
    last: Optional[str] = None
    volume_24h: Optional[str] = None
    ts: str


class OrderBookEntryDTO(BaseModel):
    """Single price level in an order book."""

    price: str
    quantity: str


class OrderBookDTO(BaseModel):
    """Order book snapshot for a symbol."""

    exchange: str
    symbol: str
    depth: int
    bids: list[OrderBookEntryDTO]
    asks: list[OrderBookEntryDTO]
    ts: str


# ── Candles / OHLC ────────────────────────────────────────────────────


class CandleDTO(BaseModel):
    """Single OHLC candle."""

    time: str
    open_: str = Field(alias="open")
    high: str
    low: str
    close: str
    volume: str


class CandlesResponseDTO(BaseModel):
    """Response envelope for candle queries."""

    exchange: str
    symbol: str
    interval: str
    count: int
    candles: list[CandleDTO]
    ts: str


# ── Exchange / metadata ───────────────────────────────────────────────


class SymbolMetaDTO(BaseModel):
    """Exchange/metadata for a symbol."""

    exchange: str
    symbol: str
    meta: dict[str, Any] = Field(default_factory=dict)


# ── Batch price update ────────────────────────────────────────────────


class PriceUpdateDTO(BaseModel):
    """Input for batch price cache update."""

    exchange: str
    symbol: str
    bid: Optional[str] = None
    ask: Optional[str] = None
    last: Optional[str] = None
    volume_24h: Optional[str] = None


# ── Cache diagnostics ─────────────────────────────────────────────────


class CacheStatsDTO(BaseModel):
    """Cache statistics response."""

    hot_prices: int = 0
    hot_orderbooks: int = 0
    warm_candles: int = 0
    warm_meta: int = 0
    total: int = 0
