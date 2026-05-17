# Architecture Reference: WT Trading Platform

**Data Pipeline & Inter-Service Security**

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 2026-05-17 |
| **Audience** | Infrastructure Engineers, Platform Architects, Technical Leads |
| **Status** | Decision Reference |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Event Streaming Architecture](#2-event-streaming-architecture)
   - 2.1 [Kafka Topic Design for Market Data](#21-kafka-topic-design-for-market-data)
   - 2.2 [Redis Caching Patterns for Real-Time Data](#22-redis-caching-patterns-for-real-time-data)
   - 2.3 [Serialization Format Selection](#23-serialization-format-selection)
   - 2.4 [Throughput/Latency Analysis](#24-throughputlatency-analysis)
   - 2.5 [Combined Pipeline Architecture](#25-combined-pipeline-architecture)
3. [Kubernetes Deployment Patterns](#3-kubernetes-deployment-patterns)
   - 3.1 [Kafka on K8s: Strimzi + KRaft](#31-kafka-on-k8s-strimzi--kraft)
   - 3.2 [Redis on K8s: Operator + Bitnami](#32-redis-on-k8s-operator--bitnami)
   - 3.3 [Storage, Scaling, Monitoring, Backup](#33-storage-scaling-monitoring-backup)
4. [mTLS in Kubernetes](#4-mtls-in-kubernetes)
   - 4.1 [mTLS Fundamentals](#41-mtls-fundamentals)
   - 4.2 [Istio Service Mesh mTLS](#42-istio-service-mesh-mtls)
   - 4.3 [Linkerd Service Mesh mTLS](#43-linkerd-service-mesh-mtls)
   - 4.4 [Manual mTLS (No Mesh)](#44-manual-mtls-no-mesh)
   - 4.5 [Service Mesh Comparison + Performance](#45-service-mesh-comparison--performance)
   - 4.6 [Certificate Rotation](#46-certificate-rotation)
5. [Architecture Decision Records](#5-architecture-decision-records)
6. [Sources & References](#6-sources--references)

---

## 1. Executive Summary

This document synthesizes research across six key infrastructure areas for the WT Trading Platform. The platform requires a low-latency, high-throughput market data pipeline combined with strict inter-service security. Below are the key decisions and recommendations.

### Key Architectural Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Protobuf** over Avro/JSON for serialization | ~40% faster ser/deser than Avro (1,402ns vs 2,371ns), 242 vs 488 bytes uncompressed, best multi-language support (Go, Rust, Python, Java) |
| 2 | **Apache Kafka** (Strimzi, KRaft) for event streaming | Proven at 2M+ writes/sec on 3 nodes, p50=2ms, p99=3ms end-to-end latency, mature ecosystem |
| 3 | **Redis** for real-time caching layer | Sub-millisecond per-operation latency (SET ~146K ops/sec single-node, 7M+ with pipelining) |
| 4 | **Redis Streams** > Pub/Sub for tick data | Provides persistence, consumer groups, and replayability absent in Pub/Sub |
| 5 | **Sorted sets with hash tags** for order books | Enables range queries by price level with co-located cluster slots |
| 6 | **Redis Cluster** for >100K ops/sec | Linear horizontal scaling across shards |
| 7 | **Tiered storage** (local SSD + S3) for Kafka | Keep 7 days hot on SSD, archive 10+ years to object storage |
| 8 | **Istio STRICT mTLS** with PERMISSIVE migration | Most mature L7 policy engine; migrate incrementally PERMISSIVE->STRICT |
| 9 | **cert-manager** for certificate lifecycle | Kubernetes-native, automatic renewal at 2/3 of certificate lifetime |
| 10 | **10GbE minimum** network for data plane | 1M ticks/sec at 256 bytes + 3x replication requires ~7.2 Gbps |

### Recommended Reference Architectures by Latency Budget

**Sub-millisecond trading (HFT) — bypass Kafka on hot path:**

```
Feed Handler ── Shared Memory / UDP ── Strategy Engine ── Exchange
                              │
                         Kafka (async, warm path)
                              │
                         Redis (async, warm cache)
```

**Low-latency algorithmic trading (1–50ms tolerance) — full pipeline:**

```
Feed Handler ── Kafka Producer ── Kafka Cluster ── Kafka Consumer
                                             ── Deserialization (Protobuf)
                                             ── Redis (SET/GET, pipelined)
                                             ── Strategy Engine
```

| Architecture Pattern | E2E Latency | Use Case |
|---|---|---|
| HFT (bypass Kafka) | < 1 ms | Sub-millisecond execution |
| Low-latency (acks=1, linger=0, Protobuf, pipelined Redis) | 4–15 ms p99 | Algorithmic trading |
| Analytics/research (acks=all, linger=5, batched) | 10–50 ms p99 | Backtesting, model training |

---

## 2. Event Streaming Architecture

The market data pipeline processes tick data, order events, and news through Kafka (durable event log) and Redis (real-time hot cache). Protobuf provides the serialization layer across both.

### 2.1 Kafka Topic Design for Market Data

#### Naming Convention: Dot-Separated Hierarchy

Pattern: `<domain>.<subdomain>.<message-type>`

```
# Market Data
market-data.ticks           Raw tick-by-tick price data
market-data.quotes          Best-bid-offer (BBO) quotes
market-data.trades          Executed trades
market-data.ob.level2       L2 order book snapshots/updates
market-data.ob.level3       L3 order book (individual order events)
market-data.ohlcv.1m        1-minute OHLCV candles
market-data.ohlcv.5m        5-minute OHLCV candles
market-data.ohlcv.1h        1-hour OHLCV candles
market-data.index           Index values
market-data.fx              Foreign exchange rates
market-data.crypto          Cryptocurrency prices

# Reference Data
reference-data.securities   Security master / instrument definitions
reference-data.exchanges    Exchange calendars, trading sessions
reference-data.currency     Currency pairs & rates

# Order Management
orders.new                  New order submissions
orders.amend                Order amendments
orders.cancel               Order cancellations
orders.fill                 Execution / fill notifications
orders.rejection            Order rejections

# News / Sentiment
news.events                 News articles / press releases
news.sentiment              NLP-derived sentiment scores

# System
system.health               Heartbeat / health-check events
system.errors               Error events from pipeline
```

#### Best Practices

| Principle | Recommendation |
|---|---|
| Separator | `.` for namespace hierarchy |
| Case | Lowercase with hyphens for multi-word segments |
| Length | Under 249 characters (hard limit) |
| Special chars | Avoid `/`, `$`, space; use `[a-z0-9.-]` |
| Granularity | Separate by consumer interest, not by volume |
| Wildcard subscriptions | Name so consumers can use regex (e.g., `market-data.ohlcv.*`) |

#### Partition Strategy

```
┌────────────────────────────────────────────────────────┐
│  Partition 0  │  AAPL ticks → strictly ordered        │
│  Partition 1  │  MSFT ticks → strictly ordered        │
│  Partition 2  │  TSLA ticks → strictly ordered        │
│  Partition N  │  GOOGL ticks → strictly ordered       │
│                                                        │
│  hash("AAPL") % 512 = 0  → always partition 0        │
│  hash("MSFT") % 512 = 1  → always partition 1        │
│  hash("TSLA") % 512 = 2  → always partition 2        │
└────────────────────────────────────────────────────────┘
```

| Data Type | Partition Key | Rationale |
|---|---|---|
| Tick data | `symbol` | All ticks ordered per symbol; enables replay |
| Quotes (BBO) | `symbol` | Best-bid-offer must be in order per symbol |
| L2 Order Book | `symbol` | Strict per-symbol ordering for reconstruction |
| L3 Order Book | `symbol` | or `symbol` + `order_id` composite |
| Trades | `symbol` | Execution order per symbol must be preserved |
| OHLCV | `symbol` + `interval` | Candles per-symbol per-interval |
| Reference Data | `id` (ISIN/FIGI) | Use log compaction |
| News | `null` (round-robin) | No ordering requirement |

#### Topic Configuration Matrix

```yaml
# ============================================================
# MARKET DATA TOPICS
# ============================================================
market-data.ticks:
  partitions: 1024
  cleanup.policy: delete
  retention.ms: 259200000           # 3 days (range: 1-7 days)
  remote.log.retention.ms: 946080000000  # 30 years tiered
  replication.factor: 3
  key: symbol
  compression.type: lz4
  min.insync.replicas: 2

market-data.quotes:
  partitions: 1024
  cleanup.policy: delete
  retention.ms: 86400000            # 24 hours (range: 6-24h)
  remote.log.retention.ms: 946080000000
  replication.factor: 3
  key: symbol
  compression.type: lz4
  min.insync.replicas: 2

market-data.trades:
  partitions: 512
  cleanup.policy: delete
  retention.ms: 2592000000          # 30 days (range: 7-30)
  replication.factor: 3
  key: symbol
  compression.type: lz4
  min.insync.replicas: 2

market-data.ob.level2:
  partitions: 512
  cleanup.policy: delete
  retention.ms: 43200000            # 12 hours (range: 6-12h)
  replication.factor: 3
  key: symbol
  compression.type: zstd
  min.insync.replicas: 2

market-data.ohlcv.1m:
  partitions: 256
  cleanup.policy: delete
  retention.ms: 94608000000         # 3 years (range: 1-3y)
  replication.factor: 3
  key: "symbol:interval"
  compression.type: lz4

reference-data.securities:
  partitions: 16
  cleanup.policy: compact           # keep latest state forever
  replication.factor: 3
  key: isin / figi
  min.compaction.lag.ms: 86400000

orders.*:
  partitions: 64
  cleanup.policy: compact,delete
  retention.ms: 7776000000          # 90 days (range: 30-90)
  key: order_id
  min.insync.replicas: 2
```

#### Consumer Group Strategy

| Consumer Group | Subscriptions | Parallelism | Key Config |
|---|---|---|---|
| `realtime-trading-engine` | ticks, quotes, trades | 1024 | `fetch.min.bytes=1`, `fetch.max.wait.ms=10` |
| `risk-monitor` | ticks, trades, fills | 256 | `isolation.level=read_committed` |
| `ohclv-aggregator` | ticks | 256 | `exactly_once_v2`, transactional producer |
| `archive-sink-ticks` | ticks | 512 | `fetch.max.bytes=52428800` |
| `archive-sink-quotes` | quotes | 1024 | same as above |
| `news-sentiment-analyzer` | news.events | 8 | `max.poll.records=100` |
| `backfill-engine` | ohlcv.1h, ohlcv.1d | 32 | `auto.offset.reset=earliest` |

**Static group membership** for rolling deployments:

```properties
group.instance.id=trading-engine-node-1
session.timeout.ms=45000
heartbeat.interval.ms=15000
```

#### Exactly-Once Semantics

| Aspect | At-Least-Once | Exactly-Once | Recommendation |
|---|---|---|---|
| Latency | Lower | ~10-20% higher overhead | Analytics, monitoring |
| Throughput | Higher | Slightly lower | Trading, P&L, compliance, risk |
| Config | `acks=1` | `enable.idempotence=true`, `isolation.level=read_committed` | Use EOS for order/financial data |

```properties
# Idempotent producer settings
enable.idempotence=true
acks=all
retries=Integer.MAX_VALUE
max.in.flight.requests.per.connection=5
```

> **Source:** Confluent: https://developer.confluent.io/courses/apache-kafka/topics/, https://developer.confluent.io/courses/apache-kafka/partitions/, https://developer.confluent.io/courses/apache-kafka/consumers/

**Schema Registry:** BACKWARD compatibility for market data, FULL for reference data. One subject per topic (TopicNameStrategy default).

---

### 2.2 Redis Caching Patterns for Real-Time Data

Redis provides the ultra-fast hot cache layer for the trading platform. Three primary caching patterns are used:

| Pattern | Use Case | Operations | Expected Throughput |
|---|---|---|---|
| **Redis Streams** | Tick data replay, event sourcing | XADD, XREADGROUP | 90K-120K ops/sec per stream |
| **Sorted Sets + Hash Tags** | Order book (price-level queries) | ZADD, ZRANGEBYSCORE | 118K ZADD ops/sec single-node |
| **String SET/GET** | Real-time snapshots, BBO | SET, GET | ~146K SET, ~157K GET ops/sec |

#### Redis Streams for Tick Data

Why Streams > Pub/Sub:

| Feature | Redis Streams | Redis Pub/Sub |
|---|---|---|
| Persistence | Yes (messages survive crash) | No (fire-and-forget) |
| Consumer Groups | Yes (coordinated consumption) | No (fan-out to all) |
| Replay | Yes (read from arbitrary ID) | No |
| Backpressure | Yes | No |

```
# Tick data ingestion
XADD ticks:AAPL * symbol AAPL price 245.67 side BID ts_ns 1715923200000
XADD ticks:AAPL * symbol AAPL price 245.69 side ASK ts_ns 1715923201000

# Consumer group reading
XREADGROUP GROUP trading-rg consumer-1 STREAMS ticks:AAPL >
```

#### Sorted Sets + Hash Tags for Order Books

Hash tags `{symbol}` ensure all order book data for one symbol lands on the same cluster node:

```
# Order book for AAPL using hash tag
ZADD {AAPL}:ob 245.65 "bid:user1:100"
ZADD {AAPL}:ob 245.63 "bid:user2:200"
ZADD {AAPL}:ob 245.69 "ask:user3:150"

# Query top 10 bid levels
ZREVRANGEBYSCORE {AAPL}:ob +inf -inf LIMIT 0 10
```

#### Caching Pattern Summary

| Pattern | When to Use | Data Type |
|---|---|---|
| Redis Streams | Tick data, event log with replay | append-only events |
| SortedSets + Hash Tags | Order book, price-level queries | scored collections |
| String SET/GET | Last-known price, BBO snapshots | key-value blobs |
| Hashes | Instrument metadata | field-value pairs |

#### Redis Cluster Sizing

| Config | Throughput | Latency |
|---|---|---|
| 1 node (single-threaded) | ~150K ops/sec | < 1 ms |
| 3-node cluster | ~450K ops/sec | < 1.5 ms |
| 6-node cluster | ~1.0-1.5M ops/sec | 1-3 ms |
| With pipelining (128 batch) | ~3.0M+ ops/sec | sub-ms per command |
| Redis Enterprise | 2M+ ops/sec | sub-ms |

#### Pipelining — Critical for High Throughput

| Pipeline Size | SET ops/sec | GET ops/sec |
|---|---|---|
| 1 (no pipeline) | ~146K | ~157K |
| 16 | ~850K | ~950K |
| 64 | ~1.8M | ~2.1M |
| 128 | ~3.0M | ~3.2M |
| 512 | ~7.0M+ | ~8.0M+ |

> **Source:** Redis benchmarks: https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/

---

### 2.3 Serialization Format Selection

#### Performance Comparison (JVM Serializers Benchmark)

| Format | Raw Size (B) | Compressed (B) | Ser+Deser (ns) | Max Throughput/core |
|---|---|---|---|---|
| **Protobuf (native)** | **242** | 152 | **1,402** | ~713K msg/sec |
| Avro fastserde (specific) | 224 | 136 | 2,647 | ~378K msg/sec |
| Avro fastserde (generic) | 224 | 136 | 2,371 | ~422K msg/sec |
| FlatBuffers | 424 | 234 | 2,124 | ~471K msg/sec |
| CBOR (Jackson) | 150 | 86 | 1,248 | ~801K msg/sec |
| **JSON (Jackson)** | **488** | 271 | **3,397** | ~294K msg/sec |
| JSON (DSL-JSON) | 488 | 271 | 1,647 | ~607K msg/sec |

#### Recommendation: Protobuf

**Selected.** Protobuf is the primary serialization format for the trading platform.

| Advantage | Detail |
|---|---|
| Speed | ~40% faster than Avro, 2.4x faster than Jackson JSON |
| Size | 242 bytes vs 488 bytes (JSON 50% smaller) |
| Multi-language | Excellent Go, Rust, Python, Java, C++, TypeScript support |
| Schema Registry | Supported in Confluent/Apicurio/AWS registries |
| Consumer simplicity | No reader schema needed — wire-level field IDs |
| Ecosystem | Mature Kafka serializer (`kafka-protobuf-serializer`) |

**Alternative: Avro** — viable if you need:
- Maximum Kafka ecosystem maturity (8-year head start)
- Java-only stack (you'll avoid Avro's weak Go/Rust support)
- Complex schema evolution (renames, aliases)

#### Estimated Message Sizes (Market Data)

| Message Type | JSON (B) | Protobuf (B) | Avro (B) |
|---|---|---|---|
| Tick (simple) | 150-200 | 40-60 | 30-50 |
| Order Event | 300-500 | 80-120 | 60-100 |
| Depth Update (10 levels) | 800-1200 | 200-300 | 150-250 |
| Heartbeat | 50-80 | 10-20 | 10-15 |

At 1M ticks/sec: **250 MB/s (JSON) vs ~50-100 MB/s (Protobuf/Avro)** — a significant network cost difference.

#### Kafka Serialization Configuration

```properties
key.converter=io.confluent.connect.protobuf.ProtobufConverter
value.converter=io.confluent.connect.protobuf.ProtobufConverter
value.converter.schema.registry.url=http://schema-registry:8081
auto.register.schemas=false  # Require pre-registered schemas
compatibility.level=BACKWARD
```

#### Redis Serialization

Store Protobuf as byte blobs. Redis has no native Protobuf support, but storing serialized bytes is efficient for full-message read/write patterns (typical for market data caches).

```
# Store tick data as Protobuf bytes
SET tick:latest:AAPL <protobuf-binary-blob>

# Retrieve and deserialize client-side
GET tick:latest:AAPL → Protobuf.deserialize() → MarketTick
```

> **Source:** JVM Serializers: https://github.com/eishay/jvm-serializers/wiki; Protobuf: https://developers.google.com/protocol-buffers/docs/proto3

---

### 2.4 Throughput/Latency Analysis

#### Kafka Performance

| Scenario | Throughput | Latency | Notes |
|---|---|---|---|
| Single broker, 3 partitions, acks=all | 100-200K rps | 2-5 ms p99 | NVMe, 1 KB msgs |
| Cluster (3 brokers), 12 partitions | **2-3M+ rps** | 5-10 ms p99 | NVMe, 1 KB msgs |
| 3 producers × 3 async replication | **2.02M rps** | — | 3-node JBOD cluster (LinkedIn benchmark) |
| 3 parallel consumers | **2.62M rps** | — | Sequential disk reads |

**End-to-End Latency (Producer → Replicated → Consumer):**

| Percentile | Latency |
|---|---|
| p50 | 2 ms |
| p99 | 3 ms |
| p99.9 | 14 ms |

#### Producer Configuration Trade-Offs

| Config | Throughput | E2E Latency | Durability |
|---|---|---|---|
| acks=0 | Maximum | 1-2 ms | NONE |
| acks=1 | High | 2-5 ms | Leader only |
| acks=all, min.insync.replicas=2 | Good | 5-15 ms | Full ISR |
| linger.ms=0 | Low | 1-3 ms | Varies |
| linger.ms=5, batch.size=64K | High | 5-10 ms | Varies |

#### Combined End-to-End Latency Breakdown

**Optimistic Scenario (same DC/rack):**

| Stage | Latency | Notes |
|---|---|---|
| Network: Feed → Producer → Kafka | 0.5-2 ms | Same rack / datacenter |
| Kafka processing + replication (acks=1) | 2-5 ms | p99 |
| Kafka consumer poll | 0.5-1 ms | Batch poll, batch.size=1000 |
| Protobuf deserialization | 0.1-0.5 ms | ~1,402ns ser+deser |
| Redis write (SET/ZADD/XADD) | 0.5-1 ms | Same DC, Redis on LAN |
| **TOTAL** | **~4-12 ms (p99)** | |

**Conservative Scenario (cross-AZ, full ISR):**

| Stage | Latency | Notes |
|---|---|---|
| Network: Feed → Producer → Kafka | 1-5 ms | Cross-AZ or cross-rack |
| Kafka processing + replication (acks=all) | 5-15 ms | Full ISR ack |
| Kafka consumer poll | 1-5 ms | Auto-commit + poll latency |
| Deserialization (complex/JSON) | 0.5-2 ms | |
| Redis write (clustered, multi-hop) | 1-3 ms | Redis Cluster cross-node |
| **TOTAL** | **~9-33 ms (p99)** | |

#### Throughput Feasibility at 1M ticks/sec

| Component | Required Ops/sec | Feasible? | Configuration |
|---|---|---|---|
| Kafka producer | 1M rps | Yes | 3-6 partitions, acks=1 |
| Kafka consumer | 1M rps | Yes | 2-3 consumer instances |
| Redis writes | 3M+ ops/sec | Yes | 2-3 nodes + pipelining |
| Redis reads | 5M+ ops/sec | Yes | 4-6 replicas + pipelining |

#### Network Bandwidth Requirements

| Message Size | Per-sec | × 3x Repl | Network Required |
|---|---|---|---|
| 72 bytes (minimal) | 72 MB/s | 216 MB/s | ~2 Gbps |
| 100 bytes (realistic) | 100 MB/s | 300 MB/s | ~2.4 Gbps |
| 128 bytes (+ overhead) | 128 MB/s | 384 MB/s | ~3.1 Gbps |
| 256 bytes (full depth) | 256 MB/s | ~768 MB/s | **~6.2 Gbps** |

**Recommendation:** 10 Gbps+ for 1M+ ticks/sec, 25 Gbps+ for 5M+ ticks/sec.

#### CPU Budget at 1M rps

| Component | Cores | Notes |
|---|---|---|
| Kafka producer | 2-4 | Compression adds 1-2 cores |
| Kafka broker (per node × 3) | 4-8 each | With compression |
| Kafka consumer | 2-4 | Decompression adds load |
| Application layer | 4-8 | Deserialization + strategy |
| Redis (per node) | 1 each | Single-threaded per instance |
| **Total estimated** | **14-29 cores** | Before LB / infra |

> **Source:** LinkedIn Kafka benchmark: https://engineering.linkedin.com/kafka/benchmarking-apache-kafka-2-million-writes-second-three-cheap-machines

---

### 2.5 Combined Pipeline Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Exchange Feed  │     │  News Providers  │     │   Broker OMS     │
│  (TCP/ITCH/FAST) │     │   (REST/WSS)     │     │  (FIX/WebSocket) │
└───────┬──────────┘     └───────┬──────────┘     └───────┬──────────┘
        │                        │                        │
        ▼                        ▼                        ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Kafka Connect    │     │ Kafka Connect    │     │ Kafka Clients    │
│ Source: ITCH     │     │ Source: REST     │     │ (FIX/OUCH)       │
│ → ticks/quotes   │     │ → news           │     │ → orders         │
└───────┬──────────┘     └───────┬──────────┘     └───────┬──────────┘
        │                        │                        │
        └────────────┬───────────┘                        │
                     ▼                                    ▼
             ┌─────────────────┐                  ┌─────────────────┐
             │  Apache Kafka    │                  │  Apache Kafka    │
             │  (KRaft, 3 node) │                  │  (KRaft, 3 node) │
             │  market-data.*   │                  │  orders.*        │
             │  reference.*     │                  │  news.*          │
             └──┬───────┬───────┘                  └────────┬────────┘
                │       │                                   │
         ┌──────┘       └──────┐                    ┌───────┘
         ▼                     ▼                    ▼
┌────────────────┐ ┌──────────────────┐ ┌─────────────────────────┐
│ Kafka Streams  │ │ Kafka Connect    │ │ Kafka Consumers          │
│ / Flink        │ │ Sink: S3/Parquet │ │                          │
│                │ │ (Archive to S3)  │ │ - Trading Engine         │
│ - OHLCV agg    │ │                  │ │ - Risk Engine            │
│ - VWAP calc    │ │                  │ │ - Analytics              │
│ - Anomaly det  │ │                  │ │ - ML Training            │
└───────┬────────┘ └──────────────────┘ └───────────┬─────────────┘
        │                                           │
        ▼                                           ▼
┌────────────────┐                    ┌─────────────────────────────┐
│ Redis Cluster  │                    │ Additional Processing       │
│                │                    │                             │
│ Streams:       │                    │ - Backtesting engine        │
│   ticks:*      │                    │ - Portfolio risk calc       │
│ SortedSets:    │                    │ - ML feature store          │
│   {sym}:ob:*   │                    │                             │
│ Strings:       │                    │                             │
│   tick:LATEST  │                    │                             │
└────────────────┘                    └─────────────────────────────┘
```

**Data Flow:**

1. Exchange feeds connect via Kafka Connect (ITCH/FAST) or custom producers
2. Raw ticks land on `market-data.ticks` with symbol-based partitioning
3. Kafka Streams aggregates ticks → OHLCV candles → `market-data.ohlcv.1m`
4. Consumers simultaneously read ticks for trading, risk, and analytics
5. Kafka Connect sinks archive to S3/Parquet for long-term storage
6. Stream processors write latest state to Redis for sub-millisecond cache queries
7. Trading engines read Redis for real-time order book and position snapshots

---

## 3. Kubernetes Deployment Patterns

### 3.1 Kafka on K8s: Strimzi + KRaft

**Selected: Strimzi Operator with KRaft mode** (no Zookeeper). Strimzi is the CNCF-graduated Kafka operator, and KRaft eliminates the operational burden of managing Zookeeper.

#### Installation

```bash
helm repo add strimzi https://strimzi.io/charts/
helm install strimzi strimzi/strimzi-kafka-operator \
  --namespace kafka --create-namespace
```

#### Production Cluster Config (KRaft)

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: wt-kafka
  namespace: kafka
spec:
  kafka:
    version: "3.9.0"
    replicas: 3
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
      - name: tls
        port: 9093
        type: internal
        tls: true
        authentication:
          type: scram-sha-512
    config:
      offsets.topic.replication.factor: 3
      transaction.state.log.replication.factor: 3
      transaction.state.log.min.isr: 2
      default.replication.factor: 3
      min.insync.replicas: 2
      log.retention.hours: 168
      log.segment.bytes: 1073741824
    storage:
      type: jbod
      volumes:
        - id: 0
          type: persistent-claim
          size: 200Gi
          class: gp3
          deleteClaim: false
    jvmOptions:
      -Xms: "4g"
      -Xmx: "4g"
    metricsConfig:
      type: jmxPrometheusExporter
      valueFrom:
        configMapKeyRef:
          name: kafka-metrics
          key: kafka-metrics-config.yml
  entityOperator:
    topicOperator: {}
    userOperator: {}
```

#### KRaft Advantages

| Feature | With Zookeeper | KRaft |
|---|---|---|
| Deployed components | Kafka + ZK (3 nodes each) | Kafka only (3 nodes) |
| Controller election | Via ZK quorum | Internal Raft quorum |
| Max partitions | ~200K | 200,000+ (practical limit 2M) |
| Operational complexity | Higher (2 systems) | Lower (1 system) |

**Alternative: Confluent for Kubernetes (CFK)** — commercial option with enterprise support. Helm: `helm repo add confluentinc https://confluentinc.github.io/cpk-helm-charts/`.

> **Sources:** Strimzi: https://strimzi.io/ | GitHub: https://github.com/strimzi/strimzi-kafka-operator | KRaft: https://kafka.apache.org/documentation/#kraft | Strimzi KRaft: https://strimzi.io/docs/operators/latest/deploying.html#deploying-cluster-operator-kraft-str

---

### 3.2 Redis on K8s: Operator + Bitnami

Two deployment options are recommended:

#### Option A: Bitnami Helm Chart (Recommended for most teams)

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install wt-redis bitnami/redis \
  --namespace redis --create-namespace \
  -f values-production.yaml
```

Production `values-production.yaml`:

```yaml
architecture: replication

auth:
  enabled: true
  existingSecret: redis-credentials

master:
  persistence:
    enabled: true
    size: 20Gi
    storageClass: gp3
  resources:
    requests:
      cpu: "1000m"
      memory: "4Gi"
    limits:
      cpu: "2000m"
      memory: "8Gi"

replica:
  replicaCount: 2
  persistence:
    enabled: true
    size: 20Gi
  resources:
    requests:
      cpu: "1000m"
      memory: "4Gi"
    limits:
      cpu: "2000m"
      memory: "8Gi"

metrics:
  enabled: true
  serviceMonitor:
    enabled: true
    namespace: redis
    interval: 15s

sentinel:
  enabled: true
  masterSet: mymaster
  automateClusterRecovery: true
```

#### Option B: Redis Operator (Spot by NetApp)

```bash
helm repo add ot-helm https://ot-container-kit.github.io/helm-charts/
helm install redis-operator ot-helm/redis-operator \
  --namespace redis --create-namespace
```

```yaml
apiVersion: redis.redis.opstreelabs.in/v1beta1
kind: RedisCluster
metadata:
  name: wt-redis-cluster
  namespace: redis
spec:
  clusterSize: 3          # 3 masters
  clusterVersion: v7
  kubernetesConfig:
    image: "redis:7.4"
  storage:
    volumeClaimTemplate:
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 10Gi
        storageClassName: gp3
  resources:
    requests:
      cpu: "500m"
      memory: 1Gi
    limits:
      cpu: "2000m"
      memory: 4Gi
  redisConfig:
    additionalRedisConfig: |
      maxmemory-policy allkeys-lru
      maxmemory 3gb
```

#### Redis Topology Comparison

| Mode | Nodes | Use Case | Failover |
|---|---|---|---|
| Standalone | 1 | Dev/test only | Manual |
| Replication + Sentinel | 1 master + 2 replicas | Production cache | Auto (sentinel) |
| Cluster (sharded) | 3 masters + 3 replicas | High-throughput | Auto (cluster) |

```
                  ┌─────────┐
                  │ Service │
                  │(ClusterIP)
                  └────┬────┘
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
      ┌──────────┐┌──────────┐┌──────────┐
      │Master-0  ││Master-1  ││Master-2  │
      └────┬─────┘└────┬─────┘└────┬─────┘
           │           │           │
      ┌────┴─────┐┌────┴─────┐┌────┴─────┐
      │Replica-0  ││Replica-1  ││Replica-2  │
      └──────────┘└──────────┘└──────────┘
```

> **Sources:** Bitnami: https://github.com/bitnami/charts/tree/main/bitnami/redis | Redis Operator: https://github.com/RedisLabs/redis-operator | Bitnami Docs: https://docs.bitnami.com/kubernetes/infrastructure/redis/

---

### 3.3 Storage, Scaling, Monitoring, Backup

#### Storage Configuration

**AWS EKS GP3 (recommended):**

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: kafka-storage
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  fsType: ext4
  encrypted: "true"
  iops: "3000"
  throughput: "125"
allowVolumeExpansion: true
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
```

**Storage Recommendations:**

| Parameter | Kafka | Redis |
|---|---|---|
| Volume size | Start ≥100Gi (JBOD), 200Gi for trading-grade | Start ≥20Gi |
| IOPS | ≥3000 (Kafka I/O heavy) | ≥1000 |
| Reclaim policy | Retain (never auto-delete) | Retain |
| Volume binding | WaitForFirstConsumer | WaitForFirstConsumer |
| Encryption | Always | Always |

**Storage Sizing:**

```
Kafka: (avg_msg_size × msgs_per_sec × retention_sec × replication_factor) / producer_count + 20%
Redis:  maxmemory × 2 (RDB snapshots + AOF overhead) + 10%
```

#### Resource Allocation

**Kafka (trading-grade, per broker):**

| CPU | Memory | IOPS | Notes |
|---|---|---|---|
| 4-8 cores | 16-32 GiB | 10,000+ | High-throughput financial data |

```yaml
resources:
  requests:
    cpu: "2000m"
    memory: "8Gi"
  limits:
    cpu: "4000m"
    memory: "16Gi"
```

**Redis (per node, cluster mode):**

| CPU | Memory | IOPS | Notes |
|---|---|---|---|
| 2-4 cores | 8-16 GiB | 5,000+ | High-throughput caching |

```yaml
resources:
  requests:
    cpu: "1000m"
    memory: "4Gi"
  limits:
    cpu: "2000m"
    memory: "8Gi"
```

#### Scaling Strategies

**Manual scaling (Kafka via Strimzi):**

```bash
# Scale brokers
kubectl edit kafka wt-kafka -n kafka
# Change spec.kafka.replicas: 3 → 5

# Rebalance with Cruise Control
kubectl apply -f kafka-rebalance.yaml
```

**KEDA for consumer auto-scaling:**

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: consumer-scaler
  namespace: kafka
spec:
  scaleTargetRef:
    name: wt-consumer-deployment
  minReplicaCount: 2
  maxReplicaCount: 20
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: wt-kafka-kafka-bootstrap.kafka.svc:9092
        consumerGroup: wt-consumer-group
        topic: market-data.ticks
        lagThreshold: "1000"
```

> **Warning:** HPA does NOT scale Kafka brokers or Redis data nodes directly. Use manual scaling or vendor-specific scaling for StatefulSet data nodes.

#### Monitoring — Prometheus/Grafana

**Key Kafka Metrics:**

| Metric | Alert Threshold | Description |
|---|---|---|
| `kafka_server_UnderReplicatedPartitions` | > 0 | Under-replicated partitions |
| `kafka_controller_KafkaController_OfflinePartitionsCount` | > 0 | Offline partitions (critical) |
| `kafka_server_ReplicaManager_IsrShrinksPerSec` | > 0 sustained | ISR shrinking |
| `kafka_log_LogFlushRateAndTimeMs` | > 1000ms | Disk flush latency |

**Key Redis Metrics:**

| Metric | Alert Threshold | Description |
|---|---|---|
| `redis_memory_used_bytes` | > 90% of maxmemory | Memory pressure |
| `redis_rejected_connections_total` | > 0 | Connection rejections |
| `replication_offset_lag` | > 1000 keys | Replication lag |
| `redis_keyspace_hit_rate` | < 80% (caches) | Cache hit rate |

**Recommended Grafana Dashboards:**

| Dashboard | ID | Source |
|---|---|---|
| Kafka Overview | 7589 | Grafana.com |
| Strimzi Kafka | 11176 | Grafana.com |
| Redis Dashboard (Redis Exporter) | 763 | Grafana.com |
| Redis Cluster | 12691 | Grafana.com |

#### Backup & Restore

**Velero (cluster-wide PVC snapshots):**

```bash
# Daily Kafka backups
velero schedule create kafka-daily \
  --schedule="0 2 * * *" \
  --include-namespaces kafka \
  --snapshot-volumes=true \
  --ttl 720h

# Restore
velero restore create --from-backup kafka-pre-upgrade
```

**Kafka MirrorMaker 2 (cross-cluster replication for DR):**

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaMirrorMaker2
metadata:
  name: wt-mirror
  namespace: kafka
spec:
  version: "3.9.0"
  replicas: 2
  connectCluster: "kafka-target"
  clusters:
    - alias: "kafka-source"
      bootstrapServers: source-kafka-bootstrap.source.svc:9092
    - alias: "kafka-target"
      bootstrapServers: target-kafka-bootstrap.target.svc:9092
  mirrors:
    - sourceCluster: "kafka-source"
      targetCluster: "kafka-target"
      topicsPattern: "wt-.*"
      groupsPattern: "wt-.*"
```

| DR Pattern | Use Case | Complexity |
|---|---|---|
| Active-Passive | DR failover | Low |
| Active-Active | Multi-region reads | High (offset syncing) |

**Redis RDB Snapshots (automated via CronJob):**

```yaml
redis.conf: |
  save 900 1        # After 900s if 1 key changed
  save 300 10       # After 300s if 10 keys changed
  save 60 10000     # After 60s if 10000 keys changed
  appendonly yes
  appendfsync everysec
```

**Velero limitation:** Volume snapshots are crash-consistent, not application-consistent. For Kafka, prefer MirrorMaker 2 for cross-cluster replication. For Redis, prefer native RDB/AOF exports.

> **Source:** Velero: https://velero.io/docs/ | KEDA: https://keda.sh/docs/2.16/scalers/apache-kafka/

---

## 4. mTLS in Kubernetes

All inter-service communication in the trading platform must be encrypted and authenticated. mTLS provides encryption in transit, server identity verification, and client identity verification.

### 4.1 mTLS Fundamentals

**How mTLS Works for Microservices:**

```
1. CA issues per-service certificates (SANS identify the workload)
2. Service A calls Service B → TLS handshake begins
3. Service B presents its server cert → A verifies against CA
4. Service A presents its client cert → B verifies against CA
5. Both sides authenticated → encrypted session proceeds
```

| Approach | How It Works | Control Level | Complexity |
|---|---|---|---|
| **Service Mesh** (Istio/Linkerd) | Sidecar proxy handles mTLS transparently | High (per-policy) | Low-Medium |
| **Manual Sidecar Proxies** | Custom Envoy/Nginx sidecars | High | High |
| **Application-Level** | App code handles TLS directly | Highest | Very High |
| **SPIFFE/SPIRE** | Standardized workload identity, mesh-agnostic | High | Medium-High |

> TLS 1.3 handshake: 2-5ms full, ~0.5ms with session resumption. Connection pooling (Envoy default) amortizes to nearly zero for persistent connections.

---

### 4.2 Istio Service Mesh mTLS

**Architecture:** Envoy proxy sidecars handle all mTLS. `istiod` control plane includes a built-in CA issuing short-lived certificates.

#### PeerAuthentication Modes

```yaml
# namespace-wide STRICT mTLS
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: strict-mtls
  namespace: trading
spec:
  mtls:
    mode: STRICT
```

| Mode | Behavior | Use Case |
|---|---|---|
| `STRICT` | Rejects all plaintext traffic | Production target state |
| `PERMISSIVE` | Accepts both plaintext and mTLS | Migration phase |
| `DISABLE` | No mTLS | Not recommended |

#### DestinationRule (Client-Side)

```yaml
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: default-mtls
  namespace: trading
spec:
  host: "*.trading.svc.cluster.local"
  trafficPolicy:
    tls:
      mode: ISTIO_MUTUAL
```

#### AuthorizationPolicy (Zero-Trust Access Control)

```yaml
# Deny-all baseline
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: deny-all
  namespace: trading
spec: {}
# Empty spec = deny everything by default
```

```yaml
# Explicit allow: order-service → risk-engine
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: order-to-risk
  namespace: trading
spec:
  selector:
    matchLabels:
      app: risk-engine
  action: ALLOW
  rules:
  - from:
    - source:
        principals: ["cluster.local/ns/trading/sa/order-service"]
    to:
    - operation:
        methods: ["POST"]
        paths: ["/api/risk/check"]
```

#### Migration Path: PERMISSIVE → STRICT

```
1. Install Istio with PERMISSIVE default
2. Mesh target namespaces (sidecar injection enabled)
3. Set DestinationRule → ISTIO_MUTUAL for intra-mesh traffic
4. Verify no plaintext traffic via Istio telemetry:
   istioctl authn tls-check <pod> -n trading
5. Switch PeerAuthentication → STRICT
```

> **Sources:** Istio Security: https://istio.io/latest/docs/concepts/security/ | mTLS Migration: https://istio.io/latest/docs/tasks/security/authentication/mtls-migration/

---

### 4.3 Linkerd Service Mesh mTLS

**Architecture:** Lightweight Rust-based `linkerd-proxy` sidecar. mTLS is **automatic and enabled by default** — no configuration required for baseline protection.

#### How It Works

```
Control Plane: trust anchor → issuer cert (K8s Secret)
    ↓
Data Plane: proxy generates key in tmpfs → CSR to identity → receives cert (24h TTL)
    ↓
Proxy-to-proxy: TLS 1.3 with ML-KEM-768 + X25519 (post-quantum resistant)
```

| Feature | Linkerd | Istio |
|---|---|---|
| mTLS Default | Yes (automatic, no config needed) | No (must configure PeerAuth + DestRule) |
| Certificate TTL | 24 hours (auto-rotated) | 24 hours (auto-rotated) |
| Proxy language | Rust (linkerd-proxy) | C++ (Envoy) |
| Install complexity | Low (`linkerd install \| k apply`) | High (Helm + CRDs + istioctl) |
| Authorization | ServerAuthorization (simpler) | AuthorizationPolicy (layered ALLOW/DENY/CUSTOM) |

#### ServerAuthorization (Linkerd's access control)

```yaml
apiVersion: policy.linkerd.io/v1alpha1
kind: ServerAuthorization
metadata:
  name: risk-engine-authz
  namespace: trading
spec:
  server:
    name: risk-engine
  client:
    meshTLS:
      identities:
      - "default:trading:order-service"
    networks:
    - cidr: 10.0.0.0/8
```

#### Post-Quantum Security (as of Linkerd 2.19)

| Parameter | Value |
|---|---|
| TLS Version | 1.3 |
| Key Exchange | Hybrid ML-KEM-768 + X25519 |
| Cipher Suite | AES_128_GCM |

> **Sources:** Linkerd mTLS: https://linkerd.io/docs/features/automatic-mtls/ | Linkerd Architecture: https://linkerd.io/docs/reference/architecture/

---

### 4.4 Manual mTLS (No Mesh)

**Approach: cert-manager + Application-Level mTLS**

No sidecar proxies. Applications configure TLS directly, with cert-manager handling certificate issuance and rotation.

#### Step 1: Deploy cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.1/cert-manager.yaml
```

#### Step 2: Create Internal CA

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: bootstrap-selfsigned
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: root-ca
  namespace: cert-manager
spec:
  isCA: true
  duration: 87600h  # 10 years
  secretName: root-ca-secret
  issuerRef:
    name: bootstrap-selfsigned
    kind: ClusterIssuer
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: internal-ca
spec:
  ca:
    secretName: root-ca-secret
```

#### Step 3: Per-Service Certificates

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: order-service-cert
  namespace: trading
spec:
  secretName: order-service-tls
  duration: 720h   # 30 days
  renewBefore: 360h
  issuerRef:
    name: internal-ca
    kind: ClusterIssuer
  commonName: order-service.trading.svc.cluster.local
  dnsNames:
    - order-service.trading.svc.cluster.local
    - order-service
  privateKey:
    algorithm: ECDSA
    size: 256
  usages:
    - digital signature
    - key encipherment
    - server auth
    - client auth
```

#### Step 4: Application-Level mTLS (Go Example)

```go
func main() {
    cert, _ := tls.LoadX509KeyPair("/var/run/secrets/tls/tls.crt", "/var/run/secrets/tls/tls.key")
    caCert, _ := os.ReadFile("/var/run/secrets/tls/ca.crt")
    caPool := x509.NewCertPool()
    caPool.AppendCertsFromPEM(caCert)

    tlsConfig := &tls.Config{
        Certificates: []tls.Certificate{cert},
        ClientAuth:   tls.RequireAndVerifyClientCert,
        ClientCAs:    caPool,
        MinVersion:   tls.VersionTLS12,
    }

    server := &http.Server{Addr: ":8443", TLSConfig: tlsConfig}
    server.ListenAndServeTLS("", "")
}
```

#### Manual mTLS Trade-Offs

| Advantage | Disadvantage |
|---|---|
| Zero proxy overhead (no extra hop) | Every language stack needs implementation |
| Lowest possible latency (no sidecar) | Certificate management per service |
| Full control over TLS parameters | CA bundle distribution across services |
| No additional memory/CPU per pod | Application-level circuit breaking needed |

> **Sources:** cert-manager: https://cert-manager.io/docs/ | gRPC mTLS: https://grpc.io/docs/guides/auth/#tls/ | Trust Manager: https://cert-manager.io/docs/trust/trust-manager/

---

### 4.5 Service Mesh Comparison + Performance

#### Resource Overhead

| Component | Istio (Envoy) | Linkerd (linkerd-proxy) |
|---|---|---|
| Memory per sidecar | 90-120 MB | 10-25 MB |
| CPU per 1K rps | ~50-100 mcpu | ~20-50 mcpu |
| Control plane memory | 500 MB - 1 GB | 100-200 MB |
| Control plane CPU | 200-500 mcpu | 100-200 mcpu |
| Binary size | ~80 MB | ~12 MB |

> For 50 microservices at 1K rps each: Istio ≈ 5-6 GB total sidecar memory. Linkerd ≈ 0.5-1.25 GB.

#### Latency Overhead

| Approach | P50 Latency | P99 Latency | Cold Start |
|---|---|---|---|
| No mesh (baseline) | 1-2 ms | 5-10 ms | N/A |
| Istio Sidecar | +1-2 ms (P50) | +3-5 ms (P99) | +5-10s |
| Istio Ambient (L4) | +1 ms (P50) | +2-3 ms (P99) | ~0s |
| Istio Ambient (L7) | +1.5 ms (P50) | +3-4 ms (P99) | ~0s |
| Linkerd Sidecar | +0.5-1 ms (P50) | +2 ms (P99) | +2-5s |
| Manual (cert-manager) | +0.1-0.5 ms | +0.5-1 ms | 0s |

#### Istio Ambient Mode (Mesh Without Sidecars)

Ambient mode replaces per-pod sidecars with shared `ztunnel` (L4, DaemonSet) and optional `waypoint` proxies (L7, per namespace):

```
Client App → iptables → ztunnel (node-shared) --mTLS→ ztunnel (node) → Server App
                                        ↓
                                waypoint proxy (optional, L7 per namespace)
```

| Metric | Sidecar Mode | Ambient Mode | Improvement |
|---|---|---|---|
| Memory per workload | ~100 MB/pod | ~0 (shared ztunnel) | 100% savings |
| CPU per 1K rps | ~50 mcpu/pod | ~5-10 mcpu | 80-90% savings |
| P50 Latency | ~2-3 ms | ~1.5-2.5 ms | 25-50% better |
| P99 Latency | ~8-15 ms | ~5-10 ms | 30-40% better |

**Status (2026):** Istio Ambient is GA since Istio 1.20.

#### Decision Matrix

| Requirement | Recommended Approach |
|---|---|
| Sub-ms latency budget for order execution | Manual mTLS or Linkerd (avoid Istio sidecar) |
| Fastest time to production security | Istio or Linkerd (automatic) |
| Strict compliance audit trail | Istio (AuthorizationPolicy audit logs) |
| Minimal resource overhead | Linkerd or Istio Ambient |
| Multi-language polyglot stack | Istio or Linkerd (transparent proxies) |
| Zero trust + fine-grained L7 access control | Istio (most mature policy engine) |
| Mixed K8s + VMs + bare metal | SPIFFE/SPIRE |
| Post-quantum requirements | Linkerd 2.19 (ML-KEM-768 hybrid) |

#### Trading Platform Recommendation

| Latency Budget | Recommendation |
|---|---|
| < 1 ms (HFT execution path) | **Manual mTLS** — no proxy overhead |
| 2-10 ms (algorithmic trading) | **Linkerd** or **Istio Ambient** — lowest proxy overhead |
| > 10 ms (analytics, research) | **Istio sidecar** — max feature set, policy engine |

---

### 4.6 Certificate Rotation

| Pattern | Rotation Frequency | Automation | Operational Overhead |
|---|---|---|---|
| cert-manager + internal CA | 30-90 days (configurable) | Fully automatic (K8s controller) | Low |
| cert-manager + Let's Encrypt | 90 days (fixed) | Fully automatic (ACME) | Low |
| step-ca (Smallstep) | Hours to days | Via step CLI or ACME | Medium |
| SPIFFE/SPIRE | 1h-24h (default 1h) | Automatic (agent renewals) | Medium-High |
| Istio built-in CA | 24h | Automatic (istiod) | None |
| Linkerd CA | 24h | Automatic (identity controller) | None |
| Manual app-level mTLS | Whatever you code | Whatever you code | Very High |

#### Pattern 1: cert-manager (Recommended for Kubernetes)

cert-manager renews at 2/3 of certificate lifetime. A 30-day cert auto-renews on day 20. The old cert stays valid until expiry — zero downtime.

#### Pattern 2: step-ca (Smallstep)

Standalone PKI with ACME support. Ideal for hybrid cloud (K8s + VMs + bare metal). Supports short-lived certs (hours, not days).

```bash
helm install step smallstep/step-certificates \
  --set ca.name="Trading Platform CA" \
  --set ca.dns="ca.trading.svc.cluster.local"
```

#### Pattern 3: SPIFFE/SPIRE

CNCF standard for workload identity. Best for multi-cluster, cross-mesh, or mixed infrastructure environments.

```
SPIRE Server (K8s CA)
    ↓
SPIRE Agent (DaemonSet on each node)
    ↓ Workload API (Unix Socket)
Application / Envoy
    ↓ SPIFFE SVID (X.509 with SPIFFE ID)
Service-to-service mTLS
```

#### Istio + cert-manager Integration

Replace Istio's built-in CA with cert-manager via `istio-csr`:

```bash
helm install -n cert-manager istio-csr jetstack/cert-manager-istio-csr \
  --set app.issuer.kind=ClusterIssuer \
  --set app.issuer.name=istio-ca
```

Gives cert-manager's certificate lifecycle management with Istio's automatic mTLS provisioning.

> **Sources:** cert-manager: https://cert-manager.io/ | step-ca: https://smallstep.com/docs/step-ca/ | SPIFFE/SPIRE: https://spiffe.io/ | istio-csr: https://cert-manager.io/docs/usage/istio-csr/

---

## 5. Architecture Decision Records

The following ADRs are summarized from this reference. Each represents a final decision with context and rationale.

### ADR-001: Protobuf as Primary Serialization Format

**Decision:** Use Protobuf for all Kafka message serialization and Redis cached values.

**Rationale:** Protobuf is 2.4x faster than Jackson JSON (1,402ns vs 3,397ns ser+deser), produces 50% smaller payloads (242 vs 488 bytes), and has excellent multi-language support for the platform's Go/Rust/Java services. Avro is competitive on size but slower on serialization and has weaker Go/Rust support.

**Alternatives considered:** Avro (strong Kafka ecosystem, rejected for speed and language support), MessagePack (no schema evolution, rejected).

**Status:** Accepted.

---

### ADR-002: Apache Kafka with Strimzi and KRaft

**Decision:** Deploy Apache Kafka using the Strimzi operator in KRaft mode (no Zookeeper).

**Rationale:** Strimzi is the CNCF-graduated Kafka operator with full lifecycle management. KRaft eliminates Zookeeper, reducing operational complexity and improving partition scaling (200K+ vs 200K limit). Performance proven at 2M+ writes/sec on 3-node commodity hardware.

**Alternatives considered:** Confluent for Kubernetes (commercial, viable for enterprise support if needed), Banzai Koperator (less mature ecosystem).

**Status:** Accepted.

---

### ADR-003: Redis for Real-Time Caching Layer

**Decision:** Use Redis as the real-time hot cache, with Redis Streams for tick data, Sorted Sets with hash tags for order books, and String SET/GET for latest snapshots.

**Rationale:** Sub-millisecond per-operation latency, proven throughput to 7M+ ops/sec with pipelining, horizontal scaling via Redis Cluster for >100K ops/sec per shard. Redis Streams provide persistence, consumer groups, and replayability — making it superior to Pub/Sub for tick data.

**Alternatives considered:** Memcached (no persistence, no streams, no sorted sets, rejected).

**Status:** Accepted.

---

### ADR-004: Istio mTLS with Gradual Migration

**Decision:** Use Istio for inter-service mTLS, starting in PERMISSIVE mode and migrating to STRICT.

**Rationale:** Istio provides the most mature L7 policy engine (AuthorizationPolicy with ALLOW/DENY/CUSTOM layers), Envoy's connection pooling and HTTP/2 multiplexing reduce mTLS handshake overhead, and PERMISSIVE→STRICT migration is well-documented and low-risk. For latency-critical paths on the order execution hot path, manual mTLS is recommended as an escape hatch.

**Alternatives considered:** Linkerd (lower overhead, automatic mTLS, but weaker L7 policy engine). Manual mTLS (lowest latency, highest operational cost). Istio Ambient (lower overhead, GA since 1.20, consider as future migration target).

**Status:** Accepted.

---

### ADR-005: Kafka Exactly-Once for Financial Data

**Decision:** Enable exactly-once semantics (`enable.idempotence=true`, `isolation.level=read_committed`) for order, fill, and risk-related Kafka topics.

**Rationale:** Duplicate messages can cause double-counting of fills, incorrect positions, erroneous risk breaches, and compliance inaccuracies. The ~10-20% latency overhead is acceptable for correctness on financial paths. Analytics and monitoring topics may use at-least-once.

**Status:** Accepted.

---

### ADR-006: Tiered Storage for Kafka

**Decision:** Enable Kafka tiered storage — 7 days retention on local SSD brokers, 10+ years in S3/GCS object storage.

**Rationale:** Market data has divergent retention needs: real-time consumers need 1-7 days of hot data; compliance and backtesting need years of history. Tiered storage separates these cost profiles. Local SSDs handle real-time throughput; object storage handles archival at ~1/10 the cost.

**Status:** Accepted.

---

### ADR-007: 10GbE Minimum Network for Data Plane

**Decision:** All data plane nodes (Kafka brokers, Redis nodes, trading engines) must have 10 Gigabit Ethernet minimum. 25GbE for environments targeting 5M+ ticks/sec.

**Rationale:** At 1M ticks/sec with 256-byte average message and 3x Kafka replication, the cluster requires ~7.2 Gbps of network bandwidth. Adding Redis replication and inter-service communication pushes total toward 10 Gbps. 1GbE would be a hard bottleneck.

**Status:** Accepted.

---

## 6. Sources & References

### Kafka / Event Streaming

| Topic | URL |
|---|---|
| Confluent — Kafka Topics 101 | https://developer.confluent.io/courses/apache-kafka/topics/ |
| Confluent — Kafka Partitions 101 | https://developer.confluent.io/courses/apache-kafka/partitions/ |
| Confluent — Kafka Consumers 101 | https://developer.confluent.io/courses/apache-kafka/consumers/ |
| Confluent — Schema Registry | https://docs.confluent.io/platform/current/schema-registry/index.html |
| Confluent — Schema Registry Serdes (Protobuf/Avro) | https://docs.confluent.io/platform/current/schema-registry/serdes-develop/index.html |
| Confluent — Message Delivery Guarantees | https://docs.confluent.io/kafka/message-delivery-guarantees.html |
| Confluent — Tiered Storage | https://docs.confluent.io/cloud/current/clusters/tiered-storage.html |
| Confluent — How to Choose Partitions | https://www.confluent.io/blog/how-to-choose-the-number-of-topicspartitions-in-a-kafka-cluster/ |
| Apache Kafka — Documentation | https://kafka.apache.org/documentation/ |
| Apache Kafka — FAQ | https://kafka.apache.org/faq |
| Apache Kafka — Design | https://kafka.apache.org/documentation/#design |
| KIP-98 — Exactly Once Delivery | https://cwiki.apache.org/confluence/display/KAFKA/KIP-98+-+Exactly+Once+Delivery+and+Transactional+Messaging |

### Serialization Benchmarks

| Topic | URL |
|---|---|
| JVM Serializers Benchmark (jvm-serializers) | https://github.com/eishay/jvm-serializers/wiki |
| Rust serde benchmark | https://github.com/serde-rs/json-benchmark |
| Protocol Buffers proto3 spec | https://developers.google.com/protocol-buffers/docs/proto3 |
| Apache Avro Specification | https://avro.apache.org/docs/1.12.0/specification/ |
| LinkedIn FastSerde for Avro | https://engineering.linkedin.com/blog/2019/07/fastserde |
| Confluent — Protobuf in Schema Registry | https://www.confluent.io/blog/schema-registry-protobuf/ |
| Apicurio Registry | https://www.apicur.io/registry/docs/ |
| FlatBuffers | https://google.github.io/flatbuffers/ |
| MessagePack | https://msgpack.org/ |

### Redis

| Topic | URL |
|---|---|
| Redis Benchmark Documentation | https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/ |
| Redis — Network Workload Benchmarks | https://redis.io/blog/benchmarking-results-for-network-bound-workloads/ |
| RedisJSON Documentation | https://docs.redis.com/latest/rl/develop/data-types/json/ |
| Redis Operator (Spot/NetApp) | https://github.com/RedisLabs/redis-operator |
| Bitnami Redis Helm Chart | https://github.com/bitnami/charts/tree/main/bitnami/redis |

### Kafka Performance

| Topic | URL |
|---|---|
| LinkedIn — 2M writes/sec benchmark | https://engineering.linkedin.com/kafka/benchmarking-apache-kafka-2-million-writes-second-three-cheap-machines |
| LinkedIn — Benchmark Config | https://gist.github.com/jkreps/c7ddb4041ef62a900e6c |
| Robinhood Engineering Blog | https://engineering.robinhood.com/ |
| Stripe — Scaling Kafka | Stripe engineering blog |
| Uber — Scaling Kafka | https://eng.uber.com/ |

### Kubernetes Deployment (Strimzi, Bitnami, K8s)

| Topic | URL |
|---|---|
| Strimzi Documentation | https://strimzi.io/documentation/ |
| Strimzi GitHub | https://github.com/strimzi/strimzi-kafka-operator |
| Strimzi KRaft Deploy | https://strimzi.io/docs/operators/latest/deploying.html#deploying-cluster-operator-kraft-str |
| Apache Kafka KRaft Docs | https://kafka.apache.org/documentation/#kraft |
| Confluent Operator | https://docs.confluent.io/operator/current/overview.html |
| Bitnami Redis Helm | https://github.com/bitnami/charts/tree/main/bitnami/redis |
| KEDA Kafka Scaler | https://keda.sh/docs/2.16/scalers/apache-kafka/ |
| Velero Backup | https://velero.io/docs/ |
| Kubernetes StatefulSet Docs | https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/ |
| Kubernetes Storage Classes | https://kubernetes.io/docs/concepts/storage/storage-classes/ |
| AWS EKS Storage Classes | https://docs.aws.amazon.com/eks/latest/userguide/storage-classes.html |

### mTLS / Service Mesh / Certificates

| Topic | URL |
|---|---|
| Istio Security Architecture | https://istio.io/latest/docs/concepts/security/ |
| Istio mTLS Migration | https://istio.io/latest/docs/tasks/security/authentication/mtls-migration/ |
| Istio Ambient Mesh | https://istio.io/latest/docs/overview/dataplane-modes/ |
| Istio Ambient GA | https://istio.io/latest/blog/2024/ambient-mesh-ga/ |
| Istio Performance Improvements | https://istio.io/latest/blog/2023/proxy-performance-improvements/ |
| Linkerd Automatic mTLS | https://linkerd.io/docs/features/automatic-mtls/ |
| Linkerd Architecture | https://linkerd.io/docs/reference/architecture/ |
| Buoyant mTLS Guide | https://buoyant.io/mtls-guide/ |
| cert-manager CA Issuer | https://cert-manager.io/docs/configuration/ca/ |
| cert-manager ACME/Let's Encrypt | https://cert-manager.io/docs/configuration/acme/ |
| cert-manager istio-csr | https://cert-manager.io/docs/usage/istio-csr/ |
| trust-manager (CA distribution) | https://cert-manager.io/docs/trust/trust-manager/ |
| Smallstep step-ca | https://smallstep.com/docs/step-ca/ |
| SPIFFE/SPIRE | https://spiffe.io/ |
| SPIFFE/SPIRE GitHub | https://github.com/spiffe/spire |
| Envoy TLS Configuration | https://www.envoyproxy.io/docs/envoy/latest/configuration/security/secret |
| gRPC TLS Auth | https://grpc.io/docs/guides/auth/#tls |
| Service Mesh Benchmark Comparison | https://itnext.io/a-benchmark-of-istio-linkerd-and-consul-service-meshes-4d7d1e3d7a37 |

---

*This document was compiled from authoritative Apache Kafka, Confluent, Redis, Istio, Linkerd, and Kubernetes sources, combined with industry best practices for financial data streaming architectures. It serves as the primary infrastructure reference for the WT Trading Platform.*

*Last updated: 2026-05-17*
