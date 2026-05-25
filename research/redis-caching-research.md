# Redis Caching Patterns for Real-Time Trading Data

> **Compiled:** 2026-05-17
> **Purpose:** Redis caching patterns for a trading platform handling tick data, order books, and real-time snapshots
> **Sources:** Redis official documentation, Redis Engineering blog, Redis Conf presentations, vendor benchmarks

---

## 1. Executive Summary

Redis serves as the ultra-low-latency hot cache layer for the trading platform. Three primary caching patterns are used:

| Pattern | Use Case | Key Finding |
|---|---|---|
| **Redis Streams** | Tick data event log with replay | Superior to Pub/Sub: persistence, consumer groups, replayability |
| **Sorted Sets + Hash Tags** | Order book price-level queries | Enables range queries with co-located cluster slots via hash tags |
| **String SET/GET** | Real-time snapshots (BBO, last price) | ~146K SET / ~157K GET ops/sec single-node |

**Thesis:** Redis Streams are the recommended ingestion pattern for tick data (over Pub/Sub), Sorted Sets with hash tags for order book caching, and Redis Cluster for horizontal scaling beyond 100K ops/sec. Per-operation latency is sub-millisecond at all levels.

---

## 2. Redis Streams for Tick Data

### Why Streams Over Pub/Sub

| Feature | Redis Streams | Pub/Sub |
|---|---|---|
| Persistence | Yes (messages survive restart) | No (fire-and-forget) |
| Consumer Groups | Yes (coordinated consumption) | No (fan-out to all subscribers) |
| Replay from arbitrary point | Yes (XREAD with ID) | No |
| Delivery acknowledgment | Yes (XACK) | No |
| Pending messages tracking | Yes (XPENDING) | No |
| Backpressure | Yes (stream maxlen) | No |

For tick data, where every price update must be durable and replayable, Pub/Sub's fire-and-forget semantics are inadequate. Streams provide at-least-once delivery with XACK-based acknowledgment.

### Usage Pattern

```bash
# Producer: append tick for AAPL with auto-generated timestamp ID
XADD ticks:AAPL * symbol AAPL exchange NASDAQ price 245.67 side BID size 100 ts_ns 1715923200000

# Producer: enforce maxlen to keep last 1M entries
XADD ticks:AAPL MAXLEN ~ 1000000 * symbol AAPL price 245.69 ...

# Consumer group: read new entries
XREADGROUP GROUP trading-rg consumer-1 COUNT 10 BLOCK 5000 STREAMS ticks:AAPL >

# Consumer: acknowledge processing
XACK ticks:AAPL trading-rg <message-id>
```

### Stream Performance

| Scenario | Throughput | Latency | Notes |
|---|---|---|---|
| XADD single append | ~90-120K ops/sec | < 1 ms | Single stream |
| XADD + XREADGROUP (1 producer, 1 consumer) | ~60-80K ops/sec | 1-2 ms | Consumer group overhead |
| XADD + XREADGROUP (parallel consumers) | ~200K+ ops/sec | 1-3 ms | Multiple consumer groups |

---

## 3. Sorted Sets + Hash Tags for Order Books

### Hash Tags for Cluster Co-Location

When Redis Cluster is deployed, keys are sharded across nodes based on CRC16 hash. Hash tags `{}` ensure related keys always land on the same shard:

```bash
# All order book data for AAPL on same node
ZADD {AAPL}:ob 245.65 "bid:user1:100"
ZADD {AAPL}:ob 245.63 "bid:user2:200"  
ZADD {AAPL}:ob 245.69 "ask:user3:150"

# Query top 10 bid/ask levels from any client — no cross-node MOVED redirect
ZREVRANGEBYSCORE {AAPL}:ob +inf 245.65 LIMIT 0 10    # Bids
ZRANGEBYSCORE {AAPL}:ob 245.68 +inf LIMIT 0 10       # Asks
```

### Performance

| Operation | Throughput (single-node) | Latency |
|---|---|---|
| ZADD | ~118K ops/sec | < 1 ms |
| ZRANGEBYSCORE | ~130K ops/sec | < 1 ms |

Sorted sets are ideal for order books because they maintain score-based ordering (price level) automatically, enabling efficient range queries per price level.

---

## 4. String SET/GET for Real-Time Snapshots

For "latest known state" patterns such as last tick price or best-bid-offer:

| Operation | Throughput (single-node) | Latency |
|---|---|---|
| SET | ~146K ops/sec | < 1 ms |
| GET | ~157K ops/sec | < 0.63 ms |
| GET + SET (atomic) | ~140K ops/sec | ~1 ms |

```bash
# Store latest tick as Protobuf binary blob
SET tick:latest:AAPL <protobuf-binary>

# Query latest
GET tick:latest:AAPL

# Store with expiry (auto-cleanup for stale data)
SET tick:latest:AAPL <data> EX 60   # 60-second TTL
```

---

## 5. Redis Cluster for Horizontal Scaling

### When to Use Cluster

| Throughput Need | Deployment | Rationale |
|---|---|---|
| < 100K ops/sec | Single node | Single-threaded Redis handles this easily |
| 100K - 500K ops/sec | Replication + Sentinel | Read scale-out, automatic failover |
| > 100K ops/sec (write-heavy) | Redis Cluster | Horizontal sharding across nodes |
| > 1M ops/sec | Redis Cluster (6+ nodes) or Redis Enterprise | Linear scaling |

### Cluster Topology

**Minimum production: 3 masters + 3 replicas**

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
      │(slots:0-5460│slots:5461-│slots:10923│
      │          │10922      │-16383     │
      └────┬─────┘└────┬─────┘└────┬─────┘
           │           │           │
      ┌────┴─────┐┌────┴─────┐┌────┴─────┐
      │Replica-0 ││Replica-1 ││Replica-2 │
      └──────────┘└──────────┘└──────────┘
```

### Cluster Scaling

| Config | Throughput | Latency |
|---|---|---|
| 1 node | ~150K ops/sec | < 1 ms |
| 3-node cluster | ~450K ops/sec | < 1.5 ms |
| 6-node cluster | ~1.0-1.5M ops/sec | 1-3 ms |
| Redis Enterprise | 2M+ ops/sec | Sub-millisecond |

---

## 6. Pipelining — Critical for High Throughput

When batching commands in a single TCP send (pipelining), throughput multiplies dramatically:

| Pipeline Size | SET ops/sec | GET ops/sec | LPUSH ops/sec |
|---|---|---|---|
| 1 (no pipeline) | ~146K | ~157K | ~144K |
| 16 | ~850K | ~950K | ~800K |
| 64 | ~1.8M | ~2.1M | ~1.6M |
| 128 | ~3.0M | ~3.2M | ~2.8M |
| 512 | ~7.0M+ | ~8.0M+ | ~7.5M+ |

At 1M ticks/sec, a single Redis node with pipeline size 128 can handle all throughput. This is the recommended optimization for the trading platform's ingestion path.

---

## 7. Redis 7.0+ Optimizations

| Feature | Benefit | Impact |
|---|---|---|
| Multi-key slot validation | Allows CROSSSLOT operations in cluster | More flexible queries |
| Function commands | Lua functions with ACL support | Safer custom logic |
| Improved eviction | Better LRU/LFU algorithm | More predictable memory |
| RESP3 protocol | Native type support | Reduced client-side parsing |

---

## 8. Sources & References

| Topic | URL |
|---|---|
| Redis Official Benchmark Docs | https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/ |
| Redis — Network Workload Benchmarks | https://redis.io/blog/benchmarking-results-for-network-bound-workloads/ |
| Redis Streams Documentation | https://redis.io/docs/data-types/streams/ |
| Redis Pipelining Docs | https://redis.io/docs/latest/operate/oss_and_stack/develop/pipelining/ |
| Redis Cluster Hash Tags | https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/ |
| Redis 7.0 Release Notes | https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/redis-7/ |
