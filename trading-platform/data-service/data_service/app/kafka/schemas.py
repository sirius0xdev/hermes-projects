from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# --- Market Price Event --- #

class PriceSource(str, Enum):
    YFINANCE = "yfinance"
    COINBASE = "coinbase"
    BINANCE = "binance"
    HYPERLIQUID = "hyperliquid"
    AGGREGATED = "aggregated"


class MarketPriceEvent(BaseModel):
    """Snapshot or tick of market price data."""
    symbol: str = Field(..., description="Ticker symbol (e.g. BTC-USD, ETH-USD)")
    price: Decimal = Field(..., decimal_places=18)
    bid: Optional[Decimal] = Field(None, decimal_places=18)
    ask: Optional[Decimal] = Field(None, decimal_places=18)
    volume_24h: Optional[Decimal] = Field(None, decimal_places=18)
    change_24h: Optional[Decimal] = Field(None, decimal_places=18)
    high_24h: Optional[Decimal] = Field(None, decimal_places=18)
    low_24h: Optional[Decimal] = Field(None, decimal_places=18)
    source: PriceSource
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.upper()


# --- Orderbook Event --- #

class OrderbookLevel(BaseModel):
    price: Decimal = Field(..., decimal_places=18)
    quantity: Decimal = Field(..., decimal_places=18)


class OrderbookEvent(BaseModel):
    """Full or partial orderbook snapshot."""
    symbol: str = Field(..., description="Ticker symbol")
    bids: list[OrderbookLevel] = Field(..., min_length=0)
    asks: list[OrderbookLevel] = Field(..., min_length=0)
    source: PriceSource
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sequence: Optional[int] = None  # monotonic sequence for ordering
    metadata: Optional[dict[str, Any]] = None

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.upper()


# --- Trade Event --- #

class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeEvent(BaseModel):
    """Individual trade execution."""
    trade_id: str = Field(..., description="Exchange-specific trade ID")
    symbol: str = Field(..., description="Ticker symbol")
    price: Decimal = Field(..., decimal_places=18)
    quantity: Decimal = Field(..., decimal_places=18)
    side: TradeSide
    source: PriceSource
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.upper()


# --- News Event --- #

class NewsArticle(BaseModel):
    """News article or announcement."""
    article_id: str = Field(..., description="Article identifier")
    title: str
    summary: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    source: str = Field(..., description="News source name")
    author: Optional[str] = None
    published_at: datetime
    tickers: list[str] = Field(default_factory=list, description="Mentioned ticker symbols")
    categories: list[str] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("tickers")
    @classmethod
    def tickers_upper(cls, v: list[str]) -> list[str]:
        return [t.upper() for t in v]


class NewsAnalysisEvent(BaseModel):
    """NLP-analyzed news article with sentiment and signals."""
    article_id: str
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)
    sentiment_label: str = Field(..., description="positive, negative, neutral")
    relevance: float = Field(..., ge=0.0, le=1.0, description="How relevant to trading")
    tickers: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    key_phrases: list[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = None


# --- Trading Signal --- #

class SignalType(str, Enum):
    SENTIMENT = "sentiment"
    PRICE_BREAKOUT = "price_breakout"
    VOLUME_SPIKE = "volume_spike"
    TECHNICAL = "technical"


class SignalDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class TradingSignal(BaseModel):
    """Generated trading signal from analysis or technical indicators."""
    signal_id: str = Field(..., description="Unique signal identifier")
    signal_type: SignalType
    direction: SignalDirection
    symbol: Optional[str] = None
    source: str = Field(..., description="Generator (e.g. 'news-analyzer', 'technical-engine')")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    data_ref: Optional[str] = None  # ref to source article/event
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = None


# --- Opportunity Events --- #

class OpportunityType(str, Enum):
    DELTA_NEUTRAL_ARB = "delta_neutral_arb"
    YIELD_SPREAD = "yield_spread"
    PRICE_DIFFERENTIAL = "price_differential"
    FUNDING_ARBITRAGE = "funding_arbitrage"


class OpportunityEvent(BaseModel):
    """Cross-chain trading opportunity detected by the scanner."""
    opportunity_id: str = Field(..., description="Unique opportunity identifier")
    opportunity_type: OpportunityType
    symbol: str = Field(..., description="Base asset (e.g. BTC, ETH)")
    title: str = Field(..., description="Human-readable summary")
    description: Optional[str] = None

    # Platform A
    platform_a: str = Field(..., description="e.g. Hyperliquid, Aave, Solend")
    platform_a_value: float = Field(..., description="Rate, yield, or price on platform A (as percentage)")
    platform_a_url: Optional[str] = None

    # Platform B
    platform_b: str = Field(..., description="e.g. Solana, Hyperliquid")
    platform_b_value: float = Field(..., description="Rate, yield, or price on platform B (as percentage)")
    platform_b_url: Optional[str] = None

    # Spread / arb potential
    spread_pct: float = Field(..., description="Spread between platforms as percentage")
    estimated_apr: float = Field(..., description="Estimated annualized return from the opportunity")
    risk_level: str = Field(..., description="low, medium, high")

    detected_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.upper()


# ── Solana Blockchain Events ─────────────────────────────────────────────

class SolanaTokenTransfer(BaseModel):
    """SPL token transfer event from Solana mainnet (via Helius WS)."""
    signature: str = Field(..., description="Solana transaction signature")
    slot: int = Field(..., description="Slot number")
    mint: str = Field(..., description="Token mint address")
    token_symbol: str = Field(..., description="Token symbol (e.g. USDC, SOL)")
    amount: Decimal = Field(..., description="Token amount (uiAmount)")
    decimals: int = Field(..., description="Token decimals")
    from_address: str = Field(..., description="Sender wallet/token account")
    to_address: str = Field(..., description="Recipient wallet/token account")
    tx_type: str = Field(..., description="Transfer type: transfer, transferChecked, mintTo, burn")
    block_time: datetime = Field(..., description="Transaction block time")
    source: str = "helius"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("block_time")
    @classmethod
    def block_time_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=None)
        return v


class SolanaPoolEvent(BaseModel):
    """Pool LP event (liquidity added/removed) from Solana mainnet."""
    signature: str = Field(..., description="Solana transaction signature")
    slot: int = Field(..., description="Slot number")
    pool_address: str = Field(..., description="Pool contract address")
    pool_name: Optional[str] = None
    token_a_mint: str = Field(..., description="Token A mint address")
    token_b_mint: str = Field(..., description="Token B mint address")
    token_a_amount: Decimal = Field(..., description="Token A amount")
    token_b_amount: Decimal = Field(..., description="Token B amount")
    lp_amount: Decimal = Field(..., description="LP tokens minted/burned (negative for removal)")
    action: str = Field(..., description="add or remove")
    actor: str = Field(..., description="Wallet that performed the action")
    block_time: datetime = Field(..., description="Transaction block time")
    source: str = "helius"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SolanaBlockEvent(BaseModel):
    """New Solana block event."""
    slot: int = Field(..., description="Slot number")
    block_height: int = Field(..., description="Block height")
    blockhash: str = Field(..., description="Block hash")
    parent_slot: int = Field(..., description="Parent slot number")
    block_time: datetime = Field(..., description="Block timestamp")
    transactions_count: Optional[int] = None
    source: str = "helius"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class JupiterSwapEvent(BaseModel):
    """Jupiter DEX swap event from Jupiter WebSocket feed."""
    signature: str = Field(..., description="Solana transaction signature")
    slot: int = Field(..., description="Slot number")
    in_mint: str = Field(..., description="Input token mint")
    in_amount: Decimal = Field(..., description="Input token amount (raw)")
    in_token_amount: Decimal = Field(..., description="Input token UI amount")
    out_mint: str = Field(..., description="Output token mint")
    out_amount: Decimal = Field(..., description="Output token amount (raw)")
    out_token_amount: Decimal = Field(..., description="Output token UI amount")
    platform_fee: Optional[Decimal] = None
    referrer_fee: Optional[Decimal] = None
    fee_amount: Decimal = Field(default=Decimal("0"), description="Total fee")
    fee_mint: Optional[str] = None
    swap_source: Optional[str] = Field(default=None, description="AMM/DEX used (e.g. Raydium, Orca)")
    user: str = Field(..., description="Swapper wallet address")
    block_time: datetime = Field(..., description="Transaction block time")
    source: str = "jupiter"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
