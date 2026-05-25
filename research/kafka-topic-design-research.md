# Kafka Topic Design Research: Market Data Ingestion Pipelines

> **Compiled:** 2026-05-17
> **Purpose:** Kafka topic architecture for a trading platform handling tick data, order updates, and news events
> **Sources:** Apache Kafka official docs, Confluent documentation & developer courses, engineering blogs, financial technology firms

---

## Table of Contents

1. [Topic Naming Conventions](#1-topic-naming-conventions)
2. [Partition Strategy](#2-partition-strategy)
3. [Retention Policies](#3-retention-policies)
4. [Consumer Group Patterns](#4-consumer-group-patterns)
5. [Kafka Connect for Market Data Feeds](#5-kafka-connect-for-market-data-feeds)
6. [Schema Registry with Avro/Protobuf](#6-schema-registry-with-avro--protobuf)
7. [Exactly-Once Semantics & Idempotent Producers](#7-exactly-once-semantics--idempotent-producers)
8. [Recommended Topic Topology](#8-recommended-topic-topology)

---

## 1. Topic Naming Conventions

### Confluent Convention: Dot-Separated Hierarchical Names

Confluent and the Kafka ecosystem favor a hierarchy using dot (`.`) separators to organize topics by domain and message type [1].

**Recommended pattern: `<domain>.<subdomain>.<message-type>`**

```
# Market data domain
market-data.ticks          # raw tick-by-tick price data
market-data.quotes         # order book quotes (BBO, top-of-book)
market-data.trades         # executed trades
market-data.ob.level2      # L2 order book snapshots / updates
market-data.ob.level3      # L3 order book (individual order events)
market-data.ohlcv.1m       # 1-minute OHLCV candles
market-data.ohlcv.5m       # 5-minute OHLCV candles
market-data.ohlcv.1h       # 1-hour OHLCV candles
market-data.index          # index values
market-data.fx             # foreign exchange rates
market-data.crypto         # cryptocurrency prices

# Reference data domain
reference-data.securities  # security master / instrument definitions
reference-data.exchanges   # exchange calendars, trading sessions
reference-data.currency    # currency pairs & rates

# Order/trade management domain
orders.new                 # new order submissions
orders.amend               # order amendments
orders.cancel              # order cancellations
orders.fill                # execution / fill notifications
orders.rejection           # order rejections

# News / sentiment domain
news.events                # news articles / press releases
news.sentiment             # NLP-derived sentiment scores

# System domain
system.health              # heartbeat / health-check events
system.errors              # error events from pipeline
```

### Alternative: Path-Separated (Slash)

Kafka natively treats `/` as just another character, but some teams use it to imply a file-system-like hierarchy:

```
md/ticks
md/quotes
md/trades
ref/securities
orders/all
news/feed
```

**Note:** The dot convention is more widely adopted in the financial industry and is the standard recommended by Confluent. See Confluent's naming guidance at:
- https://docs.confluent.io/platform/current/kafka/topics.html

### Best Practices

| Principle | Recommendation |
|---|---|
| Separator | Use `.` for namespace hierarchy |
| Case | Lowercase with hyphens for multi-word segments |
| Length | Keep topic names under 249 characters (hard limit) |
| Special chars | Avoid `/`, `$`, space; stick to `[a-z0-9.-]` |
| Granularity | Separate topics by consumer interest, not by volume alone |
| Wildcard subscription | Name so consumers can use regex (e.g., `market-data.ohlcv.*`) |

### Key Source

- Confluent Kafka Topics course: https://developer.confluent.io/courses/apache-kafka/topics/
- Kafka Topic Operations docs: https://docs.confluent.io/kafka/operations-tools/topic-operations.html

---

## 2. Partition Strategy

### Core Principle (from Confluent docs)

> "Within a single partition, message order is strictly maintained. Across partitions, no global ordering is guaranteed. Messages with the same key always go to the same partition via `hash(key) mod numPartitions`." [2]

**Key source:** https://developer.confluent.io/courses/apache-kafka/partitions/

### Partition Key Selection for Market Data

| Data Type | Recommended Key | Rationale |
|---|---|---|
| **Tick data** | `symbol` (e.g., `AAPL`, `ES`) | All ticks for one symbol stay ordered; enables replay by symbol |
| **Quotes (BBO)** | `symbol` | Same as ticks; best-bid-offer must be in order per symbol |
| **L2 Order Book** | `symbol` | Order book reconstruction requires strict per-symbol ordering |
| **L3 Order Book** | `symbol` + `order_id` composite, OR `symbol` alone | Composite = finer ordering; symbol alone = simpler scaling |
| **Trades** | `symbol` | Execution order per symbol must be preserved |
| **OHLCV** | `symbol` + `interval` (e.g., `AAPL:1m`) | Candle aggregation outputs are per-symbol per-interval |
| **Reference Data** | `id` (e.g., ISIN, FIGI, or internal security ID) | One version per entity; use log compaction |
| **Orders** | `order_id` or `account_id` | Depends on downstream consumer needs |
| **News** | `null` (round-robin) | Independent events; no ordering requirement |

### Partition Count Calculation

**Rule of thumb from Kafka FAQ (3) and Kafka Summit presentations:**

```
target_partitions = max(
    throughput_per_sec / msg_per_partition_per_sec,
    desired_consumer_parallelism
)

# Rule of thumb: each partition can handle ~10K-100K msgs/sec
# depending on payload size and latency requirements.
```

For a typical market data pipeline:

| Topic | Example Partitions | Rationale |
|---|---|---|
| `market-data.ticks` | 512–2048 | High-throughput; symbol-based keying; 8K+ symbols × 1-8 brokers |
| `market-data.quotes` | 512–2048 | Similar to ticks; may be even higher volume |
| `market-data.trades` | 128–512 | Lower volume, but still significant |
| `market-data.ob.level2` | 512–1024 | Large payloads; needs many partitions for throughput |
| `market-data.ohlcv.1m` | 128–256 | Aggregated output; moderate volume |
| `reference-data.securities` | 8–32 | Low volume; small partition count OK |
| `orders.*` | 64–256 | Scales with trading activity |
| `news.events` | 8–16 | Low volume; round-robin distribution |

### Key Sources

- Confluent: "How to Choose the Number of Topics/Partitions" blog: https://www.confluent.io/blog/how-to-choose-the-number-of-topicspartitions-in-a-kafka-cluster/
- Apache Kafka 4.0 supports up to 2 million partitions (KRaft): https://kafka.apache.org/documentation/
- Kafka FAQ: https://kafka.apache.org/faq

### Ordering Guarantees Summary

```
┌──────────────────────────────────────────────────────────────────┐
│  Partition 0  │  AAPL ticks → strictly ordered                  │
│  Partition 1  │  MSFT ticks → strictly ordered                  │
│  Partition 2  │  TSLA ticks → strictly ordered                  │
│  ...          │  ...                                            │
│  Partition N  │  GOOGL ticks → strictly ordered                 │
│                                                                      │
│  hash("AAPL") % 512 = 0   → always partition 0                │
│  hash("MSFT") % 512 = 1   → always partition 1                │
│  hash("TSLA") % 512 = 2   → always partition 2                │
└──────────────────────────────────────────────────────────────────┘
```

**Critical for trading:** If a consumer needs to reconstruct an order book, it MUST consume all messages for a given symbol from a single partition (or merge multiple partition streams with correct ordering logic). Using `symbol` as key guarantees all events for that symbol land in the same partition.

### Hot Symbol Warning

Highly-traded symbols (e.g., SPY, AAPL, ES futures) can produce disproportionate volume. Options:
1. **Sub-partitioning:** Split hot symbols by adding a secondary key (e.g., `symbol:exchange`)
2. **Dedicated topics:** Route the hottest 0.1% of symbols to their own high-partition topics
3. **Custom partitioner:** Override the default hash partitioner to spread hot keys

---

## 3. Retention Policies

### Kafka Retention Configs (4)

Kafka supports two retention mechanisms (applied independently; message is deleted when EITHER threshold is reached):

```
log.retention.hours        — time-based (default: 168 = 7 days)
log.retention.bytes        — size-based (default: unlimited)
log.retention.ms           — time-based in ms (overrides .hours)
```

And log compaction (keeps latest value per key forever):

```
cleanup.policy=compact     — keep latest per key (for reference data)
cleanup.policy=delete      — time/size-based deletion (for market data)
cleanup.policy=compact,delete — hybrid (compact AND delete old records)
```

### Recommended Retention by Market Data Type

| Topic | Cleanup Policy | Retention | Rationale |
|---|---|---|---|
| `market-data.ticks` | `delete` | **1–7 days** | High volume; used for near-real-time consumption; archive to S3/Parquet for history |
| `market-data.quotes` | `delete` | **6–24 hours** | Highest volume (BBO updates every ms); ephemeral; archive to lake |
| `market-data.trades` | `delete` | **7–30 days** | Compliance/regulatory (trade reporting); moderate volume |
| `market-data.ob.level2` | `delete` | **6–12 hours** | Very high volume; order book snapshots reconstructed from archive |
| `market-data.ohlcv.1m` | `delete` | **1–3 years** | Low volume; high analytical value; used by many consumers |
| `market-data.ohlcv.1h` | `delete` | **5–10 years** | Very low volume; historical analysis |
| `market-data.ohlcv.1d` | `delete` | **infinite / 10y+** | Archive-quality data |
| `reference-data.securities` | `compact` | **infinite** | Security master; keep latest state per ISIN/FIGI |
| `reference-data.exchanges` | `compact` | **infinite** | Exchange reference data changes rarely |
| `reference-data.currency` | `compact,delete` | **90 days** (delete) | Latest FX rate always available via compaction; cleanup old deltas |
| `orders.*` | `delete` | **30–90 days** | Audit trail / compliance; use `compact` on `order_id` to keep final state |
| `news.events` | `delete` | **6–12 months** | News articles; used for backtesting |
| `news.sentiment` | `delete` | **6 months** | Derived data; can be re-computed from news |

### Tiered Storage (Confluent Cloud / Kafka 4.0+)

For long-term retention without massive broker disk costs, enable tiered storage [5]:

```properties
# Broker-level: enable tiered storage
remote.log.storage.system.enable=true
remote.log.manager.thread.pool.size=10

# Topic-level: set remote retention > local retention
retention.ms=604800000            # 7 days on local broker disk
remote.log.retention.ms=315360000000  # 10 years in object store (S3/GCS)
```

**Benefits for market data:**
- Keep 7 days of ticks / quotes on fast local SSD brokers for real-time consumption
- Archive 10+ years of all market data to cheap object storage
- Consumers can fetch historical data transparently via the same Kafka API

### Key Sources

- Kafka Log Compaction docs: https://docs.confluent.io/kafka/log-compaction.html
- Kafka Topic Configs: https://kafka.apache.org/documentation/#topicconfigs
- Confluent Tiered Storage: https://docs.confluent.io/cloud/current/clusters/tiered-storage.html

---

## 4. Consumer Group Patterns

### Core Consumer Group Mechanics (6)

> "Each partition is consumed by exactly one consumer within a consumer group. Adding consumers up to the number of partitions increases parallelism. Adding more consumers than partitions creates idle consumers."

**Key source:** https://developer.confluent.io/courses/apache-kafka/consumers/

### Recommended Consumer Group Strategies

#### Strategy A: Dedicated Consumer Group Per Downstream Service

```
Consumer Group: ticks-realtime-processor     → processes ticks for live trading algos
Consumer Group: ticks-archive-sink           → streams ticks to S3/Parquet (Kafka Connect)
Consumer Group: ticks-analytics              → computes real-time stats (volatility, VWAP)
Consumer Group: ticks-risk-monitor           → risk / compliance monitoring
```

Each group reads the full stream independently — this is Kafka's core value proposition over queues.

#### Strategy B: Co-Partitioning for Joins (Kafka Streams / Flink)

When joining multiple market data streams (e.g., ticks + trades + order book), all joined streams must have the **same number of partitions** and use the **same partition key** (typically `symbol`):

```java
// kafka-streams: join ticks with trades on symbol
KStream<String, Tick> ticks = builder.stream("market-data.ticks");
KStream<String, Trade> trades = builder.stream("market-data.trades");

KStream<String, TickTrade> joined = ticks.join(trades,
    (tick, trade) -> new TickTrade(tick, trade),
    JoinWindows.ofTimeDifferenceAndGrace(Duration.ofSeconds(1), Duration.ofMillis(100)),
    StreamJoined.with(Serdes.String(), tickSerde, tradeSerde)
);
```

**Requirement:** Both `market-data.ticks` and `market-data.trades` must have the same partition count and use `symbol` as key.

#### Strategy C: Multi-Group Scaling for Hot Partition Handling

```
# For the hottest symbols (e.g., SPY, AAPL), you may want more parallelism:
ticks-realtime-processor: 256 consumers (handles 256 partitions)
ticks-analytics:          64 consumers  (coarser processing)
ticks-archive-sink:       512 consumers (archival can scale to partition count)
```

### Consumer Configuration for Market Data

| Config | Recommended Value | Rationale |
|---|---|---|
| `fetch.min.bytes` | `1` (low latency) or `1024` (throughput) | Trade latency vs batch efficiency |
| `fetch.max.wait.ms` | `10–50ms` | Low wait for real-time; higher for archival |
| `max.poll.records` | `500–5000` | Depends on processing speed; prevent rebalance timeout |
| `max.poll.interval.ms` | `300000` (5 min) | Time to process a batch before rebalance |
| `session.timeout.ms` | `10000–45000` | Detect dead consumers quickly |
| `heartbeat.interval.ms` | `3000` | ~1/3 of session timeout |
| `auto.offset.reset` | `latest` for real-time, `earliest` for archival | Starting position on new group |
| `enable.auto.commit` | `false` | Manual commit for exactly-once or at-least-once |
| `isolation.level` | `read_committed` | See section 7 |

### Rebalance Considerations

Market data pipelines should use **static group membership** (`group.instance.id`) to prevent unnecessary rebalances during rolling deployments:

```properties
group.instance.id=trading-engine-node-1
session.timeout.ms=45000
heartbeat.interval.ms=15000
```

### Key Sources

- Confluent Kafka Consumer course: https://developer.confluent.io/courses/apache-kafka/consumers/
- Kafka Consumer Configs: https://kafka.apache.org/documentation/#consumerconfigs
- Confluent "View Consumer Group Info": https://docs.confluent.io/kafka/operations-tools/manage-consumer-groups.html

---

## 5. Kafka Connect for Market Data Feeds

### Overview (7)

Kafka Connect is the standard framework for ingesting external market data feeds into Kafka. It provides:
- Scalable, fault-tolerant ingestion
- Automatic schema handling (with Schema Registry)
- Pre-built connectors for common financial data sources

### Connectors for Market Data

| Data Source | Connector | Config Notes |
|---|---|---|
| **WebSocket feeds** (CQS, CTS, NASDAQ ITCH) | Community websocket source connector or custom connector | Connect to exchange WebSocket; parse protocol (ITCH, OUCH, FAST); produce to Kafka |
| **FIX/FAST feeds** | Custom FIX connector (QuickFIX/J based) | Subscribe to market data streams; decode FIX/FAST messages |
| **REST APIs** (polygon, alpha-vantage) | HTTP Source Connector | Poll endpoints; schedule intervals; deduplicate |
| **File drops** (end-of-day files, reference data) | FilePulse Connector / S3 Source Connector | Parse CSV/XML/Parquet; handle incremental loads |
| **Database (security master)** | Debezium (CDC) / JDBC Source | Capture DB changes; produce to `reference-data.securities` |
| **Bloomberg/Reuters** | Custom connector via API | Use vendor SDKs; stream into Kafka topics |

### Example: ITCH Protocol to Kafka

```properties
# connect-itch-source.properties
name=ITCH-source-nasdaq
connector.class=com.example.itch.ItchSourceConnector
tasks.max=4
kafka.topic=market-data.trades.nasdaq
nasdaq.feed.host=10.0.1.100
nasdaq.feed.port=9000
nasdaq.symbols=AAPL,MSFT,TSLA,SPY,QQQ

# Transform: add symbol as key for partitioning
transforms=ExtractKey
transforms.ExtractKey.type=org.apache.kafka.connect.transforms.ValueToKey
transforms.ExtractKey.fields=symbol

# SMT: extract symbol from value and use as record key
transforms=ExtractSymbol
transforms.ExtractSymbol.type=org.apache.kafka.connect.transforms.ValueToKey
transforms.ExtractSymbol.fields=symbol
```

### Example: CDC from Security Master Database

```properties
name=securities-cdc
connector.class=io.debezium.connector.postgresql.PostgresConnector
database.hostname=db.internal
database.port=5432
database.user=connect
database.password=***
database.dbname=securities_master
table.include.list=public.securities,public.exchanges
topic.prefix=reference-data
key.converter=io.confluent.connect.avro.AvroConverter
key.converter.schema.registry.url=http://schema-registry:8081
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081
```

### Scaling Kafka Connect Workers

```properties
# distributed mode for production
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
group.id=connect-cluster

key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081

# Internal topic configs (use dedicated topics for connect internals)
config.storage.topic=connect-configs
config.storage.replication.factor=3
offset.storage.topic=connect-offsets
offset.storage.replication.factor=3
status.storage.topic=connect-status
status.storage.replication.factor=3
```

### Key Sources

- Apache Kafka Connect docs: https://kafka.apache.org/documentation/#connect
- Confluent Kafka Connect 101: https://developer.confluent.io/courses/kafka-connect/intro/
- Confluent Hub (connector marketplace): https://www.confluent.io/hub/

---

## 6. Schema Registry with Avro / Protobuf

### Why Schema Registry for Market Data (8)

Market data schemas evolve (new fields added, exchange protocol changes, new asset types). Schema Registry provides:
- Schema versioning with compatibility checks
- Eliminates schema evolution bugs in production
- Reduces message size (Avro/Protobuf encode without field names)
- Enables polyglot producers/consumers

### Schema Compatibility Strategy

```
# For market data: BACKWARD compatibility is the industry standard
# New consumers can read old data; old consumers can read new data (if new fields are optional)

# Schema Registry config:
compatibility.level=BACKWARD

# For reference data: FULL compatibility recommended
# Both forward and backward compatibility required
```

### Example Avro Schema: Market Tick

```json
{
  "type": "record",
  "name": "MarketTick",
  "namespace": "com.wttrading.marketdata",
  "fields": [
    {"name": "symbol",       "type": "string"},
    {"name": "exchange",     "type": "string"},
    {"name": "price",        "type": "double"},
    {"name": "size",         "type": "long"},
    {"name": "side",         "type": {"type": "enum", "name": "Side", "symbols": ["BID", "ASK"]}},
    {"name": "timestamp_ns", "type": "long"},
    {"name": "sequence_num", "type": "long"},
    {"name": "condition",    "type": ["null", "string"], "default": null}
  ]
}
```

### Example Avro Schema: Order Event

```json
{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.wttrading.orders",
  "fields": [
    {"name": "order_id",       "type": "string"},
    {"name": "client_order_id", "type": ["null", "string"], "default": null},
    {"name": "symbol",         "type": "string"},
    {"name": "side",            "type": {"type": "enum", "symbols": ["BUY", "SELL"]}},
    {"name": "order_type",      "type": {"type": "enum", "symbols": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"]}},
    {"name": "quantity",        "type": "long"},
    {"name": "price",           "type": ["null", "double"], "default": null},
    {"name": "status",          "type": {"type": "enum", "symbols": ["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED"]}},
    {"name": "filled_quantity", "type": "long", "default": 0},
    {"name": "avg_fill_price",  "type": ["null", "double"], "default": null},
    {"name": "timestamp_ns",    "type": "long"},
    {"name": "account_id",      "type": "string"}
  ]
}
```

### Producer/Consumer Configuration with Schema Registry

```java
// Producer
Map<String, Object> producerConfig = new HashMap<>();
producerConfig.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
producerConfig.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class);
producerConfig.put("schema.registry.url", "http://schema-registry:8081");
// Auto-register schema on first produce
producerConfig.put("auto.register.schemas", "true");

// Consumer
Map<String, Object> consumerConfig = new HashMap<>();
consumerConfig.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, KafkaAvroDeserializer.class);
consumerConfig.put("schema.registry.url", "http://schema-registry:8081");
// Specific Avro records (generated classes)
consumerConfig.put("specific.avro.reader", "true");
```

### Protobuf Alternative

Confluent Schema Registry also supports Protobuf (9), which may be preferred if:
- Your team already uses Protobuf/gRPC
- You need cross-language support with well-established tooling
- You want field-level encoding efficiency

```properties
# Protobuf config
key.converter=io.confluent.connect.protobuf.ProtobufConverter
value.converter=io.confluent.connect.protobuf.ProtobufConverter
value.converter.schema.registry.url=http://schema-registry:8081
```

### Subject Naming Strategy

```properties
# TopicNameStrategy (default): one subject per topic
# Use this for market data — each topic has one schema
key.subject.name.strategy=io.confluent.kafka.serializers.subject.TopicNameStrategy
value.subject.name.strategy=io.confluent.kafka.serializers.subject.TopicNameStrategy

# RecordNameStrategy: one subject per schema type
# Use when a topic carries multiple message types
value.subject.name.strategy=io.confluent.kafka.serializers.subject.RecordNameStrategy
```

### Key Sources

- Confluent Schema Registry docs: https://docs.confluent.io/platform/current/schema-registry/index.html
- Confluent Schema Registry course: https://developer.confluent.io/courses/schema-registry/
- Avro specification: https://avro.apache.org/docs/current/spec.html
- Protobuf with Schema Registry: https://docs.confluent.io/platform/current/schema-registry/serdes-develop/index.html#protobuf

---

## 7. Exactly-Once Semantics & Idempotent Producers

### Why EOS Matters in Trading (10, 11)

In trading pipelines, **duplicate** messages can cause:
- Double-counting of fills (P&L errors)
- Incorrect position calculations
- Erroneous risk limit breaches
- Regulatory reporting inaccuracies

**Missing** messages can cause:
- Incomplete order book reconstruction
- Missed trade signals
- Gaps in audit trails

### Idempotent Producers (At-Least-Once → Exactly-Once Within Partition)

```properties
# Enable idempotent producer
enable.idempotence=true
# Required settings (auto-set when enable.idempotence=true in modern clients):
acks=all
retries=Integer.MAX_VALUE
max.in.flight.requests.per.connection=5  # KIP-98 allows 5 with idempotence
```

**What this guarantees:** No duplicate messages produced to a single partition, even on broker retries.

### Transactional Producers (Exactly-Once Across Multiple Partitions/Topics)

For scenarios where you read from one topic and write to another (e.g., tick → aggregated OHLCV), use the Kafka Transactions API:

```java
Properties props = new Properties();
props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "ohlcv-aggregator-1");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
props.put(ProducerConfig.ACKS_CONFIG, "all");

KafkaProducer<String, OHLCVBar> producer = new KafkaProducer<>(props);
producer.initTransactions();

try {
    producer.beginTransaction();

    // Read ticks, aggregate into OHLCV, produce to output topic
    while (hasMoreTicks()) {
        Tick tick = consumeTick();
        OHLCVBar bar = aggregate(tick);
        producer.send(new ProducerRecord<>("market-data.ohlcv.1m", bar));
    }

    producer.commitTransaction();
} catch (ProducerFencedException | TimeoutException e) {
    producer.abortTransaction();
    producer.close();
}
```

### Consumer: Read Committed Isolation

```properties
# Consumers that read from transactional producers must set:
isolation.level=read_committed
# Default is 'read_uncommitted' which would see uncommitted (potentially rolled-back) messages
```

### Idempotent Consumers (Handling Duplicates on the Consumer Side)

Even with idempotent producers, consumers may still see duplicates in edge cases (consumer rebalances, crash before commit). Implement application-level idempotency:

```python
def process_tick(tick):
    # Check if we've already processed this event
    event_id = f"{tick.symbol}:{tick.exchange}:{tick.sequence_num}:{tick.timestamp_ns}"

    if seen_events.exists(event_id):
        log.info(f"Duplicate event, skipping: {event_id}")
        return

    # Process the event
    update_order_book(tick)
    update_position(tick)

    # Record that we've processed it
    seen_events.add(event_id)

    # Commit offset
    consumer.commit()
```

**Storage for seen events:** Redis Bloom filter, RocksDB (Kafka Streams state store), or a database table with unique constraint on `(symbol, sequence_num)`.

### Exactly-Once in Kafka Streams / Flink

For stream processing, both Kafka Streams and Apache Flink natively support EOS:

```java
// Kafka Streams EOS
Properties streamsConfig = new Properties();
streamsConfig.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, "exactly_once_v2");
streamsConfig.put(StreamsConfig.ISOLATION_LEVEL_CONFIG, "read_committed");

KStream<String, Tick> ticks = builder.stream("market-data.ticks");
KStream<String, OHLCVBar> ohlcv = ticks
    .groupByKey()
    .windowedBy(TimeWindows.ofSizeWithNoGrace(Duration.ofMinutes(1)))
    .aggregate(/* aggregation logic */, aggOHLCV)
    .toStream();
ohlcv.to("market-data.ohlcv.1m");
```

### EOS Trade-Offs

| Aspect | At-Least-Once | Exactly-Once |
|---|---|---|
| Latency | Lower (no transaction overhead) | ~10-20% higher |
| Throughput | Higher | Slightly lower |
| Complexity | Lower | Requires transactions + idempotent consumers |
| Use case | Analytics, monitoring, ML features | Trading execution, P&L, compliance, risk |

### Key Sources

- Kafka Message Delivery Guarantees: https://docs.confluent.io/kafka/message-delivery-guarantees.html
- Kafka Transactions docs: https://kafka.apache.org/documentation/#usingtransactions
- Confluent idempotence blog: https://www.confluent.io/blog/enabling-exactly-once-kafka-streams/
- KIP-98 (Exactly Once Delivery): https://cwiki.apache.org/confluence/display/KAFKA/KIP-98+-+Exactly+Once+Delivery+and+Transactional+Messaging

---

## 8. Recommended Topic Topology

### Complete Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Exchange Feed  │     │  News Providers  │     │   Broker OMS     │
│  (TCP/ITCH/FAST) │     │   (REST/WSS)     │     │  (FIX/WebSocket) │
└───────┬──────────┘     └───────┬──────────┘     └───────┬──────────┘
        │                        │                        │
        ▼                        ▼                        ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Kafka Connect    │     │ Kafka Connect    │     │ Kafka Clients    │
│ Source: ITCH     │     │ Source: REST     │     │ (FIX/Ouch)       │
│ → ticks, quotes  │     │ → news            │     │ → orders         │
└───────┬──────────┘     └───────┬──────────┘     └───────┬──────────┘
        │                        │                        │
        └────────────┬───────────┘                        │
                     ▼                                    ▼
             ┌───────────────┐                    ┌───────────────┐
             │  Apache Kafka  │                    │  Apache Kafka  │
             │               │                    │               │
             │ market-data.* │                    │ orders.*       │
             │ reference.*   │                    │ news.*         │
             │ system.*      │                    └───────┬───────┘
             └───┬─────┬─────┘                            │
                 │     │                                  │
        ┌────────┘     │                          ┌───────┘
        │              │                          │
        ▼              ▼                          ▼
┌───────────────┐ ┌───────────────┐ ┌─────────────────────┐
│ Kafka Connect │ │ Kafka         │ │ Kafka Streams       │
│ Sink: S3/     │ │ Consumers     │ │ / Flink             │
│ Parquet       │ │               │ │                     │
│ (Archive)     │ │ - Trading     │ │ - OHLCV aggregation │
│               │ │ - Risk Engine │ │ - VWAP calculation  │
│               │ │ - Analytics   │ │ - Signal generation │
│               │ │ - ML Training │ │ - Anomaly detection │
└───────────────┘ └───────────────┘ └─────────────────────┘
```

### Topic Configuration Matrix

```yaml
# ============================================================
# MARKET DATA TOPICS
# ============================================================
market-data.ticks:
  partitions: 1024
  cleanup.policy: delete
  retention.ms: 259200000      # 3 days
  remote.log.retention.ms: 946080000000  # 30 years (tiered)
  replication.factor: 3
  key: symbol
  value.schema: MarketTick (Avro)
  min.insync.replicas: 2
  compression.type: lz4

market-data.quotes:
  partitions: 1024
  cleanup.policy: delete
  retention.ms: 86400000       # 24 hours
  remote.log.retention.ms: 946080000000  # 30 years to object store
  replication.factor: 3
  key: symbol
  value.schema: Quote (Avro)
  compression.type: lz4

market-data.trades:
  partitions: 512
  cleanup.policy: delete
  retention.ms: 2592000000     # 30 days
  replication.factor: 3
  min.insync.replicas: 2
  key: symbol
  value.schema: Trade (Avro)
  compression.type: lz4

market-data.ob.level2:
  partitions: 512
  cleanup.policy: delete
  retention.ms: 43200000       # 12 hours
  replication.factor: 3
  key: symbol
  value.schema: OrderBookUpdate (Avro)
  compression.type: zstd

market-data.ohlcv.1m:
  partitions: 256
  cleanup.policy: delete
  retention.ms: 94608000000    # 3 years
  replication.factor: 3
  key: "symbol:interval"
  value.schema: OHLCVBar (Avro)
  compression.type: lz4
  # Produced transactionally from tick stream

market-data.ohlcv.1h:
  partitions: 128
  cleanup.policy: delete
  retention.ms: 315360000000   # 10 years
  replication.factor: 3
  key: "symbol:interval"
  value.schema: OHLCVBar (Avro)
  compression.type: lz4

reference-data.securities:
  partitions: 16
  cleanup.policy: compact
  replication.factor: 3
  min.compaction.lag.ms: 86400000  # 1 day
  key: isin / figi
  value.schema: Security (Avro)
  delete.retention.ms: 86400000    # keep tombstones 1 day

# ============================================================
# ORDER MANAGEMENT TOPICS
# ============================================================
orders.new:
  partitions: 64
  cleanup.policy: compact,delete
  retention.ms: 7776000000     # 90 days
  key: order_id
  value.schema: OrderEvent (Avro)

orders.fill:
  partitions: 64
  cleanup.policy: compact,delete
  retention.ms: 7776000000     # 90 days
  key: order_id
  value.schema: FillEvent (Avro)

# ============================================================
# NEWS TOPICS
# ============================================================
news.events:
  partitions: 16
  cleanup.policy: delete
  retention.ms: 15768000000    # 6 months
  key: null (round-robin)
  value.schema: NewsEvent (Avro)
  compression.type: gzip

# ============================================================
# SYSTEM TOPICS
# ============================================================
system.health:
  partitions: 1
  cleanup.policy: compact
  key: service_name
  value.schema: HealthCheck (Avro)
```

### Consumer Group Matrix

| Consumer Group | Subscriptions | Consumers | Key Config |
|---|---|---|---|
| `realtime-trading-engine` | `market-data.ticks`, `market-data.quotes`, `market-data.trades` | 1024 | `fetch.min.bytes=1`, `fetch.max.wait.ms=10`, `isolation.level=read_committed` |
| `risk-monitor` | `market-data.ticks`, `market-data.trades`, `orders.fill` | 256 | `isolation.level=read_committed`, `enable.auto.commit=false` |
| `ohclv-aggregator` | `market-data.ticks` | 256 | Processing guarantee: `exactly_once_v2`, transactional producer |
| `archive-sink-ticks` | `market-data.ticks` | 512 | `fetch.max.bytes=52428800` (50MB batches for S3 sink) |
| `archive-sink-quotes` | `market-data.quotes` | 1024 | Same as above |
| `news-sentiment-analyzer` | `news.events` | 8 | `max.poll.records=100`, batch NLP processing |
| `backfill-engine` | `market-data.ohlcv.1h`, `market-data.ohlcv.1d` | 32 | `auto.offset.reset=earliest`, for historical analysis |

---

## Sources and References

[1] Confluent Developer — Kafka Topics 101: https://developer.confluent.io/courses/apache-kafka/topics/

[2] Confluent Developer — Kafka Partitions 101: https://developer.confluent.io/courses/apache-kafka/partitions/

[3] Kafka Summit Talk — "How to Choose the Number of Topics/Partitions": https://www.confluent.io/blog/how-to-choose-the-number-of-topicspartitions-in-a-kafka-cluster/

[4] Apache Kafka Documentation — Topic Configs: https://kafka.apache.org/documentation/#topicconfigs

[5] Confluent — Tiered Storage: https://docs.confluent.io/cloud/current/clusters/tiered-storage.html

[6] Confluent Developer — Kafka Consumers 101: https://developer.confluent.io/courses/apache-kafka/consumers/

[7] Apache Kafka — Kafka Connect Docs: https://kafka.apache.org/documentation/#connect

[8] Confluent — Schema Registry: https://docs.confluent.io/platform/current/schema-registry/index.html

[9] Confluent — Schema Registry Serdes (Protobuf/Avro/JSON): https://docs.confluent.io/platform/current/schema-registry/serdes-develop/index.html

[10] Confluent — Message Delivery Guarantees: https://docs.confluent.io/kafka/message-delivery-guarantees.html

[11] KIP-98 — Exactly Once Delivery & Transactional Messaging: https://cwiki.apache.org/confluence/display/KAFKA/KIP-98+-+Exactly+Once+Delivery+and+Transactional+Messaging

[12] Apache Kafka — Kafka FAQ: https://kafka.apache.org/faq

[13] Kafka — Design Document: https://kafka.apache.org/documentation/#design

[14] Confluent — Producer Design: https://docs.confluent.io/kafka/producer-design.html

[15] Confluent — Consumer Design: https://docs.confluent.io/kafka/consumer-design.html

[16] Confluent — Replication: https://docs.confluent.io/kafka/replication.html

[17] Confluent — Log Compaction: https://docs.confluent.io/kafka/log-compaction.html

[18] Confluent — How to Use Kafka Tools: https://docs.confluent.io/kafka/operations-tools/use-kafka-tools-ccloud.html

[19] Confluent — View Consumer Group Info: https://docs.confluent.io/kafka/operations-tools/manage-consumer-groups.html

[20] Confluent — Choose and Change Partition Count: https://docs.confluent.io/kafka/operations-tools/partition-determination.html

---

*This document was compiled from authoritative Apache Kafka and Confluent sources, combined with industry best practices for financial data streaming architectures.*
