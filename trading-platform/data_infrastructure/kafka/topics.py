"""Kafka topic definitions for the trading platform.

Follows the dot-separated naming convention from architecture-reference.md.
All topics are symbol-keyed for partition affinity.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TopicDef:
    name: str
    description: str
    partitions: int = 6
    retention_hours: int = 168  # 7 days default
    cleanup_policy: str = "delete"  # delete or compact
    replication_factor: int = 1   # 3 for production
    config: dict = field(default_factory=dict)
    key_field: Optional[str] = None  # field name for partition key

    def to_admin_config(self) -> dict:
        """Build kafka topic configuration dict.

        Returns configs like {"num_partitions": N, "replication_factor": 3,
        "topic_configs": {"retention.ms": "...", ...}}.
        """
        topic_configs = {"cleanup.policy": self.cleanup_policy}
        if self.retention_hours:
            topic_configs["retention.ms"] = str(self.retention_hours * 3600 * 1000)
        topic_configs.update(self.config)
        return {
            "num_partitions": self.partitions,
            "replication_factor": self.replication_factor,
            "topic_configs": topic_configs,
        }


# ── Market data topics ─────────────────────────────────────────────

TICKS = TopicDef(
    name="market-data.ticks",
    description="Raw tick-by-tick price data",
    partitions=12,
    retention_hours=24,  # 1 day — high volume
    config={"compression.type": "lz4"},
    key_field="symbol",
)

TRADES = TopicDef(
    name="market-data.trades",
    description="Executed market trades",
    partitions=6,
    retention_hours=168,  # 7 days
    key_field="symbol",
)

QUOTES = TopicDef(
    name="market-data.quotes",
    description="Best-bid-offer (BBO) quotes",
    partitions=6,
    retention_hours=48,
    config={"compression.type": "lz4"},
    key_field="symbol",
)

ORDERBOOK_L2 = TopicDef(
    name="market-data.ob.level2",
    description="L2 order book snapshots and deltas",
    partitions=6,
    retention_hours=24,
    key_field="symbol",
)

OHLCV_1M = TopicDef(
    name="market-data.ohlcv.1m",
    description="1-minute OHLCV candles",
    partitions=3,
    retention_hours=720,  # 30 days
    key_field="symbol",
)

OHLCV_5M = TopicDef(
    name="market-data.ohlcv.5m",
    description="5-minute OHLCV candles",
    partitions=3,
    retention_hours=2160,  # 90 days
    key_field="symbol",
)

OHLCV_1H = TopicDef(
    name="market-data.ohlcv.1h",
    description="1-hour OHLCV candles",
    partitions=3,
    retention_hours=8760,  # 1 year
    key_field="symbol",
)

# ── Reference data ─────────────────────────────────────────────────

SECURITIES = TopicDef(
    name="reference-data.securities",
    description="Security master / instrument definitions",
    partitions=4,
    cleanup_policy="compact",
    key_field="isin",
)

# ── Order management topics ────────────────────────────────────────

ORDERS_NEW = TopicDef(
    name="orders.new",
    description="New order submissions",
    partitions=6,
    cleanup_policy="compact",
    key_field="client_order_id",
)

ORDER_STATUS = TopicDef(
    name="orders.status",
    description="Order status updates (filled, cancelled, etc.)",
    partitions=6,
    cleanup_policy="compact",
    retention_hours=72,
    key_field="client_order_id",
)

FILLS = TopicDef(
    name="orders.fills",
    description="Execution/fill notifications",
    partitions=6,
    retention_hours=2160,  # 90 days
    key_field="symbol",
)

# ── Position & PnL topics ──────────────────────────────────────────

POSITIONS = TopicDef(
    name="trading.positions",
    description="Position state updates",
    partitions=3,
    cleanup_policy="compact",
    key_field="wallet_address",
)

PNL = TopicDef(
    name="trading.pnl",
    description="PnL events (realized and mark-to-market)",
    partitions=3,
    retention_hours=8760,
    key_field="wallet_address",
)

# ── News / Sentiment ───────────────────────────────────────────────

NEWS_EVENTS = TopicDef(
    name="news.events",
    description="News articles / press releases",
    partitions=3,
    retention_hours=720,
)

NEWS_SENTIMENT = TopicDef(
    name="news.sentiment",
    description="NLP-derived sentiment scores",
    partitions=3,
    retention_hours=720,
)

# ── System ─────────────────────────────────────────────────────────

SYSTEM_HEALTH = TopicDef(
    name="system.health",
    description="Heartbeat / health-check events",
    partitions=1,
    retention_hours=24,
)

SYSTEM_ERRORS = TopicDef(
    name="system.errors",
    description="Error events from pipeline",
    partitions=2,
    retention_hours=168,
)

# ── All topics for initialization ──────────────────────────────────

ALL_TOPICS = [
    TICKS, TRADES, QUOTES, ORDERBOOK_L2,
    OHLCV_1M, OHLCV_5M, OHLCV_1H,
    SECURITIES,
    ORDERS_NEW, ORDER_STATUS, FILLS,
    POSITIONS, PNL,
    NEWS_EVENTS, NEWS_SENTIMENT,
    SYSTEM_HEALTH, SYSTEM_ERRORS,
]
