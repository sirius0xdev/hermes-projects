"""Tests for Kafka streaming components: topics, schemas, producer, consumer, ingester."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

BASE = "data_service.app.kafka"


# ── Topic & Config Tests ─────────────────────────────────────────────

class TestKafkaTopics:
    """Verify topic naming conventions and constants."""

    def test_topic_naming_convention(self):
        from data_service.app.kafka.topics import KafkaTopics

        prefix = "trading-platform."
        for attr_name in dir(KafkaTopics):
            if attr_name.startswith("_"):
                continue
            value = getattr(KafkaTopics, attr_name)
            assert value.startswith(prefix), f"Topic {attr_name} doesn't start with {prefix}: {value}"

    def test_all_expected_topics_exist(self):
        from data_service.app.kafka.topics import KafkaTopics

        expected = [
            "MARKET_PRICES", "MARKET_ORDERBOOK", "MARKET_TRADES",
            "NEWS_FEED", "NEWS_ANALYSIS", "TRADING_SIGNALS",
        ]
        for name in expected:
            assert hasattr(KafkaTopics, name), f"Missing topic: {name}"
            value = getattr(KafkaTopics, name)
            assert isinstance(value, str)

    def test_topic_values_are_unique(self):
        from data_service.app.kafka.topics import KafkaTopics

        values = []
        for name in dir(KafkaTopics):
            if name.startswith("_"):
                continue
            values.append(getattr(KafkaTopics, name))
        assert len(values) == len(set(values)), "Duplicate topic names found"


class TestTopicConfig:
    """Test topic configuration lookup."""

    def test_config_has_all_topics(self):
        from data_service.app.kafka.config import TOPIC_CONFIG
        from data_service.app.kafka.topics import KafkaTopics

        for name in dir(KafkaTopics):
            if name.startswith("_"):
                continue
            value = getattr(KafkaTopics, name)
            assert value in TOPIC_CONFIG, f"No config for topic: {value}"

    def test_config_has_required_fields(self):
        from data_service.app.kafka.config import TOPIC_CONFIG

        for topic, cfg in TOPIC_CONFIG.items():
            assert "partitions" in cfg, f"Missing partitions for {topic}"
            assert "replication_factor" in cfg, f"Missing replication_factor for {topic}"
            assert "config" in cfg, f"Missing config for {topic}"
            assert isinstance(cfg["partitions"], int)
            assert isinstance(cfg["replication_factor"], int)

    def test_get_topic_config_known(self):
        from data_service.app.kafka.config import get_topic_config, TOPIC_CONFIG

        for topic in TOPIC_CONFIG:
            cfg = get_topic_config(topic)
            assert cfg == TOPIC_CONFIG[topic]

    def test_get_topic_config_unknown_returns_defaults(self):
        from data_service.app.kafka.config import get_topic_config

        cfg = get_topic_config("nonexistent-topic")
        assert cfg["partitions"] == 3
        assert cfg["replication_factor"] == 1
        assert "cleanup.policy" in cfg["config"]


# ── Schema Tests ──────────────────────────────────────────────────────

class TestMarketPriceEvent:
    def test_valid_event(self):
        from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource

        event = MarketPriceEvent(
            symbol="btc-usd",
            price=Decimal("50000.00"),
            source=PriceSource.YFINANCE,
        )
        assert event.symbol == "BTC-USD"
        assert event.price == Decimal("50000.00")
        assert event.bid is None

    def test_symbol_uppercase(self):
        from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource

        event = MarketPriceEvent(
            symbol="eth-usd",
            price=Decimal("3000.00"),
            source=PriceSource.BINANCE,
        )
        assert event.symbol == "ETH-USD"

    def test_serialization(self):
        from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource

        event = MarketPriceEvent(
            symbol="BTC-USD",
            price=Decimal("50000.00"),
            source=PriceSource.YFINANCE,
            metadata={"exchange": "test"},
        )
        data = event.model_dump(mode="json")
        assert data["symbol"] == "BTC-USD"
        assert data["price"] == "50000.00"
        assert data["source"] == "yfinance"
        assert data["metadata"]["exchange"] == "test"

    def test_roundtrip_json(self):
        from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource

        event = MarketPriceEvent(
            symbol="BTC-USD",
            price=Decimal("50000.123456789012"),
            source=PriceSource.YFINANCE,
            bid=Decimal("49999.00"),
            ask=Decimal("50001.00"),
        )
        data = json.loads(event.model_dump_json())
        assert data["symbol"] == "BTC-USD"


class TestOrderbookEvent:
    def test_valid_orderbook(self):
        from data_service.app.kafka.schemas import (
            OrderbookEvent, OrderbookLevel, PriceSource,
        )

        event = OrderbookEvent(
            symbol="BTC-USD",
            bids=[OrderbookLevel(price=Decimal("50000"), quantity=Decimal("1.5"))],
            asks=[OrderbookLevel(price=Decimal("50001"), quantity=Decimal("2.0"))],
            source=PriceSource.COINBASE,
            sequence=42,
        )
        assert len(event.bids) == 1
        assert event.bids[0].price == Decimal("50000")
        assert event.sequence == 42

    def test_serialization(self):
        from data_service.app.kafka.schemas import (
            OrderbookEvent, OrderbookLevel, PriceSource,
        )

        event = OrderbookEvent(
            symbol="ETH-USD",
            bids=[OrderbookLevel(price=Decimal("3000"), quantity=Decimal("10"))],
            asks=[],
            source=PriceSource.HYPERLIQUID,
        )
        data = event.model_dump(mode="json")
        assert data["bids"][0]["price"] == "3000"
        assert data["asks"] == []


class TestTradeEvent:
    def test_valid_trade(self):
        from data_service.app.kafka.schemas import TradeEvent, TradeSide, PriceSource

        event = TradeEvent(
            trade_id="trade-001",
            symbol="BTC-USD",
            price=Decimal("50000.00"),
            quantity=Decimal("0.5"),
            side=TradeSide.BUY,
            source=PriceSource.BINANCE,
        )
        assert event.side == TradeSide.BUY
        assert event.quantity == Decimal("0.5")


class TestNewsArticle:
    def test_valid_article(self):
        from data_service.app.kafka.schemas import NewsArticle

        event = NewsArticle(
            article_id="art-001",
            title="Fed Raises Rates",
            source="Reuters",
            published_at=datetime.utcnow(),
            tickers=["spy", "tlT"],
        )
        assert event.tickers == ["SPY", "TLT"]

    def test_article_serialization(self):
        from data_service.app.kafka.schemas import NewsArticle

        event = NewsArticle(
            article_id="art-001",
            title="Test",
            source="Test",
            published_at=datetime.utcnow(),
        )
        data = event.model_dump(mode="json")
        assert data["article_id"] == "art-001"


class TestTradingSignal:
    def test_valid_signal(self):
        from data_service.app.kafka.schemas import (
            TradingSignal, SignalType, SignalDirection,
        )

        signal = TradingSignal(
            signal_id="sig-001",
            signal_type=SignalType.SENTIMENT,
            direction=SignalDirection.BULLISH,
            source="news-analyzer",
            confidence=0.85,
            symbol="BTC-USD",
        )
        assert signal.confidence == 0.85
        assert signal.direction == SignalDirection.BULLISH

    def test_signal_validation_rejects_bad_confidence(self):
        from data_service.app.kafka.schemas import (
            TradingSignal, SignalType, SignalDirection,
        )

        with pytest.raises(Exception):
            TradingSignal(
                signal_id="sig-001",
                signal_type=SignalType.TECHNICAL,
                direction=SignalDirection.NEUTRAL,
                source="test",
                confidence=1.5,  # > 1.0
            )


# ── Producer Tests (mocked) ──────────────────────────────────────────

class TestDataProducer:
    """Test producer with mocked Kafka connection."""

    def _make_producer(self):
        from data_service.app.kafka.producer import DataProducer
        return DataProducer(bootstrap_servers="localhost:9092", acks="all")

    def test_create_producer(self):
        p = self._make_producer()
        assert p._producer is None
        assert not p.is_running

    def test_start_creates_kafka_producer(self):
        with patch(f"{BASE}.producer.KafkaProducer") as mock_cls:
            mock_cls.return_value = MagicMock()
            p = self._make_producer()
            p.start()
            assert p.is_running
            mock_cls.assert_called_once()
            p.stop()

    def test_stop_closes_producer(self):
        with patch(f"{BASE}.producer.KafkaProducer") as mock_cls:
            mock_producer = MagicMock()
            mock_cls.return_value = mock_producer
            p = self._make_producer()
            p.start()
            p.stop()
            mock_producer.flush.assert_called_once()
            mock_producer.close.assert_called_once()
            assert not p.is_running

    def test_send_message_without_start_raises(self):
        p = self._make_producer()
        with pytest.raises(RuntimeError, match="not started"):
            p.send_message("topic", "key", {"value": 1})

    def test_send_price_type_check(self):
        with patch(f"{BASE}.producer.KafkaProducer") as mock_cls:
            mock_future = MagicMock()
            mock_future.get.return_value = MagicMock(topic="t", partition=0, offset=0)
            mock_producer = MagicMock()
            mock_producer.send.return_value = mock_future
            mock_cls.return_value = mock_producer

            p = self._make_producer()
            p.start()

            with pytest.raises(TypeError, match="Expected MarketPriceEvent"):
                p.send_price({"wrong": "type"})

            p.stop()

    def test_send_price_happy_path(self):
        from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource

        with patch(f"{BASE}.producer.KafkaProducer") as mock_cls:
            mock_future = MagicMock()
            mock_future.get.return_value = MagicMock(topic="t", partition=0, offset=0)
            mock_producer = MagicMock()
            mock_producer.send.return_value = mock_future
            mock_cls.return_value = mock_producer

            p = self._make_producer()
            p.start()

            event = MarketPriceEvent(
                symbol="BTC-USD",
                price=Decimal("50000"),
                source=PriceSource.YFINANCE,
            )
            p.send_price(event)

            mock_producer.send.assert_called_once()
            call_kwargs = mock_producer.send.call_args[1]
            assert call_kwargs["key"] == "BTC-USD"
            assert "event_type" in dict(call_kwargs["headers"])

            p.stop()

    def test_json_serializer_handles_types(self):
        from data_service.app.kafka.schemas import MarketPriceEvent, PriceSource
        from data_service.app.kafka.producer import DataProducer

        event = MarketPriceEvent(
            symbol="BTC-USD",
            price=Decimal("50000.00"),
            source=PriceSource.YFINANCE,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )
        result = DataProducer._json_serializer(event)
        assert isinstance(result, dict)
        assert result["price"] == "50000.00"
        assert result["source"] == "yfinance"

    def test_send_trade_happy_path(self):
        from data_service.app.kafka.schemas import TradeEvent, TradeSide, PriceSource

        with patch(f"{BASE}.producer.KafkaProducer") as mock_cls:
            mock_future = MagicMock()
            mock_future.get.return_value = MagicMock(topic="t", partition=0, offset=0)
            mock_producer = MagicMock()
            mock_producer.send.return_value = mock_future
            mock_cls.return_value = mock_producer

            p = self._make_producer()
            p.start()

            event = TradeEvent(
                trade_id="t-001",
                symbol="ETH-USD",
                price=Decimal("3000"),
                quantity=Decimal("1.0"),
                side=TradeSide.SELL,
                source=PriceSource.COINBASE,
            )
            p.send_trade(event)
            mock_producer.send.assert_called_once()
            p.stop()

    def test_send_trading_signal_happy_path(self):
        from data_service.app.kafka.schemas import (
            TradingSignal, SignalType, SignalDirection,
        )

        with patch(f"{BASE}.producer.KafkaProducer") as mock_cls:
            mock_future = MagicMock()
            mock_future.get.return_value = MagicMock(topic="t", partition=0, offset=0)
            mock_producer = MagicMock()
            mock_producer.send.return_value = mock_future
            mock_cls.return_value = mock_producer

            p = self._make_producer()
            p.start()

            signal = TradingSignal(
                signal_id="s-001",
                signal_type=SignalType.TECHNICAL,
                direction=SignalDirection.BULLISH,
                source="engine",
                confidence=0.9,
            )
            p.send_trading_signal(signal)
            call_kwargs = mock_producer.send.call_args[1]
            headers = dict(call_kwargs["headers"])
            assert headers["signal_type"] == b"technical"
            p.stop()


# ── Consumer Tests (mocked) ──────────────────────────────────────────

class TestDataConsumer:
    """Test consumer with mocked Kafka connection."""

    def _make_consumer(self, **kwargs):
        from data_service.app.kafka.consumer import DataConsumer
        return DataConsumer(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            **kwargs,
        )

    def test_create_consumer(self):
        c = self._make_consumer()
        assert c._consumer is None
        assert not c.is_running

    def test_start_creates_kafka_consumer(self):
        from data_service.app.kafka.topics import KafkaTopics
        with patch(f"{BASE}.consumer.KafkaConsumer") as mock_cls:
            mock_consumer = MagicMock()
            mock_cls.return_value = mock_consumer
            c = self._make_consumer(topics=[KafkaTopics.MARKET_PRICES])
            c.start()
            assert c.is_running
            mock_consumer.subscribe.assert_called_once()
            c.stop()

    def test_register_handler(self):
        c = self._make_consumer()
        handler = lambda msg: None
        c.register_handler("test-topic", handler)
        assert c.get_topic_handlers()["test-topic"] is handler

    def test_consume_once_without_start_raises(self):
        c = self._make_consumer()
        with pytest.raises(RuntimeError, match="not started"):
            c.consume_once()

    def test_consume_once_processes_messages(self):
        with patch(f"{BASE}.consumer.KafkaConsumer") as mock_cls:
            mock_consumer = MagicMock()
            mock_consumer.poll.return_value = {}
            mock_cls.return_value = mock_consumer

            c = self._make_consumer(topics=["prices"])
            c.start()

            received = []
            c.register_handler("topic-1", lambda msg: received.append(msg))

            # Simulate a message
            from kafka.structs import TopicPartition
            tp = TopicPartition("topic-1", 0)
            mock_record = MagicMock()
            mock_record.topic = "topic-1"
            mock_record.partition = 0
            mock_record.offset = 1
            mock_record.key = "key1"
            mock_record.value = {"price": "50000"}
            mock_record.timestamp = 1234567890
            mock_record.headers = []

            mock_consumer.poll.return_value = {tp: [mock_record]}
            count = c.consume_once()
            assert count == 1
            assert len(received) == 1
            assert received[0]["value"] == {"price": "50000"}

            c.stop()

    def test_consume_once_skips_unhandled_topics(self):
        with patch(f"{BASE}.consumer.KafkaConsumer") as mock_cls:
            mock_consumer = MagicMock()
            mock_cls.return_value = mock_consumer

            c = self._make_consumer(topics=["prices"])
            c.start()

            from kafka.structs import TopicPartition
            tp = TopicPartition("unhandled-topic", 0)
            mock_record = MagicMock()
            mock_record.topic = "unhandled-topic"
            mock_record.partition = 0
            mock_record.offset = 1
            mock_record.key = None
            mock_record.value = {"data": "test"}
            mock_record.timestamp = 1234567890
            mock_record.headers = []

            mock_consumer.poll.return_value = {tp: [mock_record]}
            count = c.consume_once()
            # Message silently skipped since no handler registered
            assert count == 0

            c.stop()

    def test_consumer_property_raises_when_not_started(self):
        from data_service.app.kafka.consumer import DataConsumer
        c = DataConsumer()
        with pytest.raises(RuntimeError, match="not started"):
            _ = c.consumer


# ── Topic Setup Tests ────────────────────────────────────────────────

class TestTopicSetup:
    """Test topic administration utility."""

    def test_create_topic_success(self):
        from data_service.app.kafka.setup_topics import TopicAdmin

        with patch(f"{BASE}.setup_topics.KafkaAdminClient") as mock_cls:
            mock_admin = MagicMock()
            mock_cls.return_value = mock_admin

            admin = TopicAdmin(bootstrap_servers="localhost:9092")
            admin.connect()
            result = admin.create_topic("test-topic", partitions=3, replication_factor=1)
            assert result is True
            mock_admin.create_topics.assert_called_once()
            admin.close()

    def test_create_topic_already_exists(self):
        from data_service.app.kafka.setup_topics import TopicAdmin
        from kafka.errors import TopicAlreadyExistsError

        with patch(f"{BASE}.setup_topics.KafkaAdminClient") as mock_cls:
            mock_admin = MagicMock()
            mock_admin.create_topics.side_effect = TopicAlreadyExistsError()
            mock_cls.return_value = mock_admin

            admin = TopicAdmin()
            admin.connect()
            result = admin.create_topic("existing-topic")
            assert result is False
            admin.close()

    def test_create_all_topics(self):
        from data_service.app.kafka.setup_topics import TopicAdmin

        with patch(f"{BASE}.setup_topics.KafkaAdminClient") as mock_cls:
            mock_admin = MagicMock()
            mock_cls.return_value = mock_admin

            admin = TopicAdmin()
            admin.connect()
            results = admin.create_all_topics()

            from data_service.app.kafka.config import TOPIC_CONFIG
            for topic in TOPIC_CONFIG:
                assert topic in results

            assert len(results) == len(TOPIC_CONFIG)
            admin.close()
