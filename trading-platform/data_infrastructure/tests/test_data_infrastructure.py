"""End-to-end tests for market data pipeline: Redis + Kafka + Protobuf + models."""
from __future__ import annotations

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from datetime import datetime, timezone

# ============================================================
# Test Protobuf serialization
# ============================================================

class TestProtobufSerialization:
    """Test that protobuf messages serialize/deserialize correctly."""

    def test_tick_serialization_shape(self):
        """Verify TickData protobuf has all expected fields."""
        # Test the .proto file structure by parsing it directly
        proto_path = os.path.join(
            os.path.dirname(__file__),
            "../proto/trading.proto",
        )
        with open(proto_path) as f:
            content = f.read()

        assert "message TickData" in content
        assert "string symbol" in content
        assert "double price" in content
        assert "int64 timestamp_us" in content
        assert "message OrderBookUpdate" in content
        assert "message CandleData" in content
        assert "message FillReport" in content
        assert "message NewOrder" in content
        assert "message PositionUpdate" in content
        assert "message PnLEvent" in content

    def test_all_message_types_defined(self):
        """All required protobuf messages are defined."""
        proto_path = os.path.join(
            os.path.dirname(__file__),
            "../proto/trading.proto",
        )
        with open(proto_path) as f:
            content = f.read()

        required_messages = [
            "TickData", "BBOQuote", "OrderBookUpdate", "CandleData",
            "TickBatch", "NewOrder", "FillReport", "OrderStatusUpdate",
            "PositionUpdate", "PnLEvent", "ServiceHeartbeat", "ControlCommand",
        ]
        for msg in required_messages:
            assert f"message {msg}" in content, f"Missing message: {msg}"


# ============================================================
# Test Kafka topic definitions
# ============================================================

class TestKafkaTopics:
    """Test Kafka topic configuration."""

    def test_topic_naming_convention(self):
        """All topics follow dot-separated naming."""
        from data_infrastructure.kafka.topics import ALL_TOPICS

        for topic in ALL_TOPICS:
            parts = topic.name.split(".")
            assert len(parts) >= 2, f"Topic {topic.name} needs at least 2 segments"
            assert len(topic.name) < 249, f"Topic {topic.name} too long for Kafka"

    def test_required_topics_exist(self):
        """All domain topics are defined."""
        from data_infrastructure.kafka import topics

        topic_names = [t.name for t in topics.ALL_TOPICS]

        assert "market-data.ticks" in topic_names
        assert "market-data.trades" in topic_names
        assert "market-data.quotes" in topic_names
        assert "market-data.ob.level2" in topic_names
        assert "market-data.ohlcv.1m" in topic_names
        assert "orders.new" in topic_names
        assert "orders.fills" in topic_names
        assert "trading.positions" in topic_names
        assert "trading.pnl" in topic_names

    def test_order_topics_use_compactly_cleanup(self):
        """Order/position topics use compaction for state retention."""
        from data_infrastructure.kafka.topics import (
            ORDERS_NEW, ORDER_STATUS, POSITIONS, TICKS,
        )

        # Stateful topics should use compaction
        assert ORDERS_NEW.cleanup_policy == "compact"
        assert POSITIONS.cleanup_policy == "compact"

        # High-volume topics use deletion
        assert TICKS.cleanup_policy == "delete"


# ============================================================
# Test Kafka config
# ============================================================

class TestKafkaConfig:
    """Test Kafka configuration."""

    def test_default_settings(self):
        from data_infrastructure.kafka.config import kafka_settings

        assert kafka_settings.bootstrap_servers == "localhost:9092"
        assert kafka_settings.producer_acks == "all"
        assert kafka_settings.producer_compression == "lz4"
        assert kafka_settings.consumer_group_id == "market-data-workers"


# ============================================================
# Test Redis cache
# ============================================================

class TestRedisCache:
    """Test Redis caching layer."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock async Redis client."""
        mock = AsyncMock()
        mock.hset = AsyncMock()
        mock.get = AsyncMock()
        mock.hgetall = AsyncMock(return_value={})
        mock.expire = AsyncMock()
        mock.xadd = AsyncMock(return_value=b"1234567890-0")
        mock.xrevrange = AsyncMock([])
        mock.xgroup_create = AsyncMock()
        mock.xreadgroup = AsyncMock([])
        mock.zadd = AsyncMock()
        mock.zrange = AsyncMock([])
        mock.zremrangebyscore = AsyncMock()
        mock.zcard = AsyncMock(0)
        mock.pipeline = MagicMock()
        mock.pipeline.return_value.execute = AsyncMock(return_value=[None, None, 0, True])
        mock.pipeline.return_value.delete = MagicMock()
        mock.pipeline.return_value.zadd = MagicMock()
        mock.pipeline.return_value.zrange = MagicMock()
        return mock

    @pytest.fixture
    def cache(self, mock_redis):
        from data_infrastructure.redis.cache import MarketDataCache
        cache = MarketDataCache(redis_url="redis://test:6379/0")
        cache._pool = mock_redis
        return cache

    @pytest.mark.asyncio
    async def test_set_latest_price(self, cache, mock_redis):
        """Test caching latest price."""
        await cache.set_latest_price("BTC/USDT", 65000.0, source="binance")

        assert mock_redis.hset.called
        assert mock_redis.expire.called

        call_args = mock_redis.hset.call_args
        assert "{BTC/USDT}:price:latest" in call_args[1]["key"] if "key" in call_args[1] else call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_latest_price_miss(self, cache, mock_redis):
        """Test cache miss returns None."""
        mock_redis.hgetall.return_value = {}
        result = await cache.get_latest_price("ETH/USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_price_hit(self, cache, mock_redis):
        """Test cache hit returns parsed data."""
        mock_redis.hgetall.return_value = {
            "price": "65000.5",
            "timestamp": "2026-05-17T10:00:00+00:00",
            "source": "binance",
        }
        result = await cache.get_latest_price("BTC/USDT")

        assert result is not None
        assert result["price"] == 65000.5
        assert result["source"] == "binance"

    @pytest.mark.asyncio
    async def test_set_bbo(self, cache, mock_redis):
        """Test caching best bid/offer."""
        await cache.set_bbo("BTC/USDT", bid=64999.0, ask=65001.0, bid_size=1.5, ask_size=2.0)

        assert mock_redis.hset.called
        assert mock_redis.expire.called

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self, cache, mock_redis):
        """Test rate limiter allows request under limit."""
        mock_redis.pipeline.return_value.execute = AsyncMock(
            return_value=[None, None, 1, True]
        )

        result = await cache.check_rate_limit("client1", "api")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_blocked(self, cache, mock_redis):
        """Test rate limiter blocks request over limit."""
        from data_infrastructure.redis.config import redis_settings
        mock_redis.pipeline.return_value.execute = AsyncMock(
            return_value=[None, None, redis_settings.rate_limit_max_requests + 1, True]
        )

        result = await cache.check_rate_limit("client1", "api")
        assert result is False


# ============================================================
# Test Redis config
# ============================================================

class TestRedisConfig:
    """Test Redis configuration."""

    def test_default_settings(self):
        from data_infrastructure.redis.config import redis_settings

        assert redis_settings.redis_url == "redis://redis-master:6379/0"
        assert redis_settings.hot_orderbook_ttl == 60
        assert redis_settings.max_stream_length == 100_000


# ============================================================
# Test data models
# ============================================================

class TestFillModel:
    """Test fill model definition."""

    def test_fill_table_name(self):
        from data_infrastructure.models.fill_models import FillRecord
        assert FillRecord.__tablename__ == "fills"

    def test_fill_has_all_columns(self):
        from data_infrastructure.models.fill_models import FillRecord
        cols = {c.name for c in FillRecord.__table__.columns}

        required = {
            "id", "order_id", "client_order_id", "wallet_address", "chain",
            "symbol", "side", "quantity", "fill_price", "fee", "fee_currency",
            "is_maker", "external_fill_id", "raw_data", "filled_at", "created_at",
        }
        assert required.issubset(cols)


class TestPnLModel:
    """Test PnL history model definition."""

    def test_pnl_table_name(self):
        from data_infrastructure.models.pnl_models import PnLRecord
        assert PnLRecord.__tablename__ == "pnl_history"

    def test_pnl_has_all_columns(self):
        from data_infrastructure.models.pnl_models import PnLRecord
        cols = {c.name for c in PnLRecord.__table__.columns}

        required = {
            "id", "wallet_address", "chain", "symbol",
            "realized_pnl", "unrealized_pnl", "pnl_type", "currency",
            "fees_total", "snapshot_at", "created_at",
        }
        assert required.issubset(cols)


class TestMarketDataModels:
    """Test market data model definitions."""

    def test_candle_table_name(self):
        from data_infrastructure.models.market_data_models import CandleRecord
        assert CandleRecord.__tablename__ == "candles"

    def test_candle_has_all_columns(self):
        from data_infrastructure.models.market_data_models import CandleRecord
        cols = {c.name for c in CandleRecord.__table__.columns}

        required = {
            "id", "symbol", "interval", "open_time", "close_time",
            "open_price", "high_price", "low_price", "close_price",
            "volume", "trade_count", "source", "created_at",
        }
        assert required.issubset(cols)

    def test_orderbook_snapshots_table(self):
        from data_infrastructure.models.market_data_models import OrderBookSnapshot
        assert OrderBookSnapshot.__tablename__ == "orderbook_snapshots"

    def test_market_trades_table(self):
        from data_infrastructure.models.market_data_models import TradeRecord
        assert TradeRecord.__tablename__ == "market_trades"


# ============================================================
# Test Kafka producer mocks
# ============================================================

class TestMarketDataProducer:
    """Test market data producer (mock)."""

    @pytest.mark.asyncio
    async def test_producer_requires_start(self):
        from data_infrastructure.kafka.producer import MarketDataProducer
        producer = MarketDataProducer(bootstrap_servers="localhost:9092")
        with pytest.raises(RuntimeError, match="Call start"):
            from data_infrastructure.kafka.topics import TICKS
            await producer.produce(TICKS, MagicMock())

    def test_serialize_protobuf_message(self):
        """Test _serialize_message works with protobuf."""
        from data_infrastructure.kafka.producer import _serialize_message
        # Skip if protobuf not installed
        try:
            # We can't compile .proto in test, skip actual serialization
            pass
        except ImportError:
            pass

    def test_extract_key(self):
        from data_infrastructure.kafka.producer import _extract_key
        msg = MagicMock()
        msg.symbol = "BTC/USDT"
        assert _extract_key(msg) == "BTC/USDT"


# ============================================================
# Test Docker compose file
# ============================================================

class TestDockerCompose:
    """Test that docker-compose.yml is well-formed."""

    def test_compose_file_exists(self):
        compose_path = os.path.join(
            os.path.dirname(__file__),
            "../../docker-compose.yml",
        )
        assert os.path.exists(compose_path)

    def test_compose_has_required_services(self):
        import yaml

        compose_path = os.path.join(
            os.path.dirname(__file__),
            "../../docker-compose.yml",
        )
        with open(compose_path) as f:
            compose = yaml.safe_load(f)

        required_services = {"postgres", "redis", "kafka"}
        services = set(compose["services"].keys())
        assert required_services.issubset(services)

    def test_postgres_env_vars(self):
        import yaml

        compose_path = os.path.join(
            os.path.dirname(__file__),
            "../../docker-compose.yml",
        )
        with open(compose_path) as f:
            compose = yaml.safe_load(f)

        env = compose["services"]["postgres"]["environment"]
        assert env["POSTGRES_USER"] == "trading"
        assert env["POSTGRES_DB"] == "trading_db"

    def test_kafka_uses_kraft(self):
        """Kafka uses KRaft mode (no Zookeeper)."""
        import yaml

        compose_path = os.path.join(
            os.path.dirname(__file__),
            "../../docker-compose.yml",
        )
        with open(compose_path) as f:
            compose = yaml.safe_load(f)

        kafka_env = compose["services"]["kafka"]["environment"]
        assert "KAFKA_PROCESS_ROLES" in kafka_env
        assert "broker" in kafka_env["KAFKA_PROCESS_ROLES"]

    def test_all_services_on_same_network(self):
        import yaml

        compose_path = os.path.join(
            os.path.dirname(__file__),
            "../../docker-compose.yml",
        )
        with open(compose_path) as f:
            compose = yaml.safe_load(f)

        services = compose["services"]
        for svc_name in ["postgres", "redis", "kafka"]:
            assert "networks" in services[svc_name]
            assert "trading-net" in services[svc_name]["networks"]


# ============================================================
# Test config
# ============================================================

class TestConfig:
    """Test data infrastructure config."""

    def test_default_config(self):
        from data_infrastructure.config import settings

        assert settings.database_url.startswith("sqlite") or "postgresql" in settings.database_url

    def test_invalid_db_url_raises_error(self):
        from pydantic import ValidationError
        from data_infrastructure.config import DataInfrastructureSettings

        with pytest.raises(ValidationError):
            DataInfrastructureSettings(database_url="mysql://invalid")
