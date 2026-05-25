# Kubernetes Production Deployment Patterns: Redis & Kafka

> Research document — May 2026
> Focus: Production-ready patterns using Helm operators, KRaft mode for Kafka, Redis Operator, monitoring, scaling, and backup/restore.

---

## Table of Contents

1. [Kafka on Kubernetes](#1-kafka-on-kubernetes)
   - 1.1 Strimzi Operator
   - 1.2 KRaft Mode (No Zookeeper)
   - 1.3 Helm Charts
2. [Redis on Kubernetes](#2-redis-on-kubernetes)
   - 2.1 Redis Operator
   - 2.2 Bitnami Helm Charts
   - 2.3 Redis Cluster on K8s
3. [StatefulSet Best Practices](#3-statefulset-best-practices)
4. [PVC / Storage Class Recommendations](#4-pvc--storage-class-recommendations)
5. [Resource Allocation Patterns](#5-resource-allocation-patterns)
6. [Scaling Strategies](#6-scaling-strategies)
7. [Monitoring with Prometheus/Grafana](#7-monitoring-with-prometheusgrafana)
8. [Backup and Restore Patterns](#8-backup-and-restore-patterns)
9. [Network Policies for Data Plane Isolation](#9-network-policies-for-data-plane-isolation)
10. [Complete Reference Architecture](#10-complete-reference-architecture)

---

## 1. Kafka on Kubernetes

### 1.1 Strimzi Operator

**Source:** https://strimzi.io/
**GitHub:** https://github.com/strimzi/strimzi-kafka-operator
**Docs:** https://strimzi.io/documentation/

Strimzi is the CNCF-graduated (now Incubating) operator for running Apache Kafka on Kubernetes. It provides:

- **Kafka** — manages brokers with declarative YAML
- **Kafka Connect** — source/sink connector management
- **Kafka MirrorMaker 2** — cross-cluster replication
- **Kafka Bridge** — HTTP/AMQP protocol gateway
- **Cruise Control** — automated rebalancing and optimization
- **Kafka Exporter** — Prometheus-compatible metrics

**Installation via Helm:**

```bash
helm repo add strimzi https://strimzi.io/charts/
helm install strimzi strimzi/strimzi-kafka-operator \
  --namespace kafka --create-namespace
```

**Key Custom Resource Definitions (CRDs):**
- `Kafka` — the main cluster definition
- `KafkaTopic` — topic provisioning
- `KafkaUser` — SCRAM-SHA and mTLS user management
- `KafkaConnector` — Connect sink/source connectors
- `KafkaMirrorMaker2` — cross-cluster mirroring

**Example — Minimal Kafka Cluster (KRaft):**

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
    storage:
      type: jbod
      volumes:
        - id: 0
          type: persistent-claim
          size: 100Gi
          deleteClaim: false
          class: gp3
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

---

### 1.2 KRaft Mode (No Zookeeper)

**Source:** https://kafka.apache.org/documentation/#kraft
**Strimzi Docs:** https://strimzi.io/docs/operators/latest/deploying.html#deploying-cluster-operator-kraft-str

KRaft (Kafka Raft) eliminates Zookeeper as of Kafka 3.3+ (GA). Strimzi supports KRaft mode natively.

**Key advantages:**
- Simplified architecture (no separate Zookeeper deployment)
- Faster controller elections
- Better scaling for large clusters (more partitions, more brokers)
- Reduced operational overhead

**KRaft-specific configuration in Strimzi:**

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: wt-kafka-kraft
  namespace: kafka
spec:
  kafka:
    version: "3.9.0"
    replicas: 3
    # KRaft requires dedicated controller-eligible and broker-eligible nodes
    # In Strimzi, all nodes can play both roles when using KRaft
    config:
      # KRaft-specific settings
      num.partitions: 6
      num.recovery.threads.per.data.dir: 4
      offsets.topic.replication.factor: 3
      transaction.state.log.replication.factor: 3
      transaction.state.log.min.isr: 2
      default.replication.factor: 3
      min.insync.replicas: 2
      # KRaft metadata log settings
      log.retention.hours: 168
      log.segment.bytes: 1073741824
    # No zookeeper section — this triggers KRaft mode
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
      - name: tls
        port: 9093
        type: internal
        tls: true
    storage:
      type: persistent-claim
      size: 100Gi
      deleteClaim: false
      class: gp3
      # Separate metadata log volume (optional, for performance)
  # No entityOperator.zookeeper section needed
```

**Important KRaft considerations:**
- Minimum 3 replicas for production (controller quorum)
- Use `process.roles=broker,controller` for combined nodes
- Metadata volume should be on fast storage (SSD/IOPS-optimized)
- Strimzi automatically sets `process.roles` when no `zookeeper` section is present

**Scaling up partitions limit:** KRaft in K8s supports 200,000+ partitions vs ~200K with Zookeeper.

---

### 1.3 Helm Charts for Kafka

**Alternative: Confluent Operator**
- Source: https://docs.confluent.io/operator/current/overview.html
- Helm: https://charts.confluent.io/

**Confluent for Kubernetes (CFK):**

```bash
helm repo add confluentinc https://confluentinc.github.io/cpk-helm-charts/
helm install confluent-operator confluentinc/confluent-for-kubernetes \
  --namespace confluent --create-namespace
```

**Confluent Kafka Cluster (KRaft):**

```yaml
apiVersion: platform.confluent.io/v1beta1
kind: Kafka
metadata:
  name: wt-kafka
spec:
  replicas: 3
  dataVolumeCapacity: 100Gi
  config:
    offsets.topic.replication.factor: 3
    transaction.state.log.replication.factor: 3
    min.insync.replicas: 2
  dependencies:
    kafkaMetadata:
      type: kraft
```

**Third-party option: Banzai Cloud Kafka Operator (Koperator)**
- GitHub: https://github.com/banzaicloud/koperator
- Focuses on elasticity, auto-scaling, and Cruise Control integration

---

## 2. Redis on Kubernetes

### 2.1 Redis Operator

**Spot by NetApp Redis Operator** (formerly RedisLabs/redis-operator)
- **Source:** https://github.com/RedisLabs/redis-operator
- **Documentation:** https://docs.redis.com/latest/kubernetes/
- **Alternative:** https://github.com/spotahome/redis-operator (simpler, lighter)

The Spot operator provides Redis Enterprise on K8s with:
- Redis Cluster (sharding)
- Redis Sentinel (HA)
- Standalone deployments
- Backup/restore
- TLS support
- Prometheus metrics

**Installation:**

```bash
helm repo add ot-helm https://ot-container-kit.github.io/helm-charts/
helm install redis-operator ot-helm/redis-operator \
  --namespace redis --create-namespace
```

**Example — Redis Cluster via Operator:**

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
    imagePullPolicy: Always
  redisExporter:
    enabled: true
    image: "oliver006/redis_exporter:v1.67.0"
  storage:
    volumeClaimTemplate:
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 10Gi
        storageClassName: gp3
  podSecurityContext:
    runAsUser: 1000
    fsGroup: 1000
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2000m
      memory: 4Gi
  redisConfig:
    additionalRedisConfig: |
      maxmemory-policy allkeys-lru
      maxmemory 3gb
```

### 2.2 Bitnami Helm Charts

**Source:** https://github.com/bitnami/charts/tree/main/bitnami/redis
**Docs:** https://docs.bitnami.com/kubernetes/infrastructure/redis/

Bitnami is the most widely used Redis Helm chart in production.

**Installation:**

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install wt-redis bitnami/redis \
  --namespace redis --create-namespace \
  --set architecture=replication \
  --set auth.enabled=true \
  --set auth.password=<strong-password> \
  --set master.persistence.size=20Gi \
  --set replica.replicaCount=2 \
  --set metrics.enabled=true \
  --set volumePermissions.enabled=true
```

**Production values.yaml:**

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
    accessModes:
      - ReadWriteOnce
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2000m
      memory: 4Gi
  podSecurityContext:
    runAsUser: 1000
    fsGroup: 1000

replica:
  replicaCount: 2
  persistence:
    enabled: true
    size: 20Gi
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2000m
      memory: 4Gi

metrics:
  enabled: true
  serviceMonitor:
    enabled: true
    namespace: redis
    interval: 15s

sentinel:
  enabled: true
  masterSet: mymaster
  initialCheckTimeout: 5
  getMasterTimeout: 90
  automateClusterRecovery: true
```

**Redis Cluster mode (sharded) via Bitnami:**

```yaml
architecture: cluster
cluster:
  nodes: 6              # 3 masters + 3 replicas
  replicas: 1
auth:
  enabled: true
  existingSecret: redis-credentials
metrics:
  enabled: true
  serviceMonitor:
    enabled: true
```

### 2.3 Redis Cluster on K8s — Key Considerations

**Topology patterns:**
- **Standalone** — single pod, dev/test only
- **Replication** — master + read replicas, manual failover or with Sentinel
- **Sentinel** — automated failover, no sharding
- **Cluster mode** — sharding across 6+ nodes (3 masters + 3 replicas minimum)

**Redis Cluster in K8s challenges:**
- Cluster requires gossip ports (16379) in addition to client port (6379)
- Pod IP changes on restart require `cluster-announce-ip` configuration
- Bitnami chart handles this via headless services and proper DNS

**Bitnami cluster topology example:**

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
      │(6379,16379│(6379,16379│(6379,16379│
      └────┬─────┘└────┬─────┘└────┬─────┘
           │           │           │
      ┌────┴─────┐┌────┴─────┐┌────┴─────┐
      │Replica-0 ││Replica-1 ││Replica-2 │
      └──────────┘└──────────┘└──────────┘
```

---

## 3. StatefulSet Best Practices

**Source:** https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/
**Docs:** https://kubernetes.io/docs/tutorials/stateful-application/

StatefulSets are the backbone of running stateful data infrastructure on K8s.

### Best Practices

**1. Use Pod Disruption Budgets (PDBs):**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kafka-pdb
  namespace: kafka
spec:
  minAvailable: 2           # At least 2 brokers must be running
  selector:
    matchLabels:
      app.kubernetes.io/name: kafka
```

**2. Anti-affinity for high availability:**

```yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchExpressions:
            - key: app.kubernetes.io/name
              operator: In
              values:
                - kafka
        topologyKey: kubernetes.io/hostname   # Spread across nodes
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values:
                  - kafka
          topologyKey: topology.kubernetes.io/zone  # Prefer spread across AZs
```

**3. Graceful termination:**

```yaml
spec:
  terminationGracePeriodSeconds: 60  # Kafka needs time to flush + leadership transfer
  lifecycle:
    preStop:
      exec:
        command:
          - /bin/bash
          - -c
          - |
            # For Kafka: trigger leadership transfer before shutdown
            kafka-leader-election.sh --bootstrap-server localhost:9092
            # For Redis: trigger BGSAVE and wait
            redis-cli BGSAVE
            sleep 10
```

**4. Pod management policy:**

```yaml
spec:
  podManagementPolicy: Parallel   # For faster scaling
  # vs OrderedReady (default) — useful for bootstrapped clusters like etcd
  serviceName: kafka-headless
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      partition: 0  # For staged rollouts, set to higher number
```

**5. Init containers for storage preparation:**

```yaml
initContainers:
  - name: fix-permissions
    image: busybox:1.36
    command: ["sh", "-c", "chown -R 1000:1000 /var/lib/kafka/data"]
    volumeMounts:
      - name: kafka-data
        mountPath: /var/lib/kafka/data
```

**6. Use pod topology spread constraints (K8s 1.19+):**

```yaml
spec:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
      labelSelector:
        matchLabels:
          app.kubernetes.io/name: kafka
```

---

## 4. PVC / Storage Class Recommendations

**Source:** https://kubernetes.io/docs/concepts/storage/storage-classes/
**AWS EBS:** https://docs.aws.amazon.com/eks/latest/userguide/storage-classes.html
**GCP PD:** https://cloud.google.com/kubernetes-engine/docs/how-to/persistent-volumes/gce-pd-csi-driver

### Storage Class by Cloud Provider

**AWS EKS — GP3 (General Purpose SSD):**

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
  iops: "3000"          # Explicit IOPS for gp3 (min 3000)
  throughput: "125"     # MiB/s (min 125)
allowVolumeExpansion: true
reclaimPolicy: Retain   # Never delete data automatically
volumeBindingMode: WaitForFirstConsumer  # Delay provisioning until pod scheduled
```

**AWS EKS — io2 (High Performance):**

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: kafka-high-perf
provisioner: ebs.csi.aws.com
parameters:
  type: io2
  fsType: ext4
  encrypted: "true"
  iopsPerGB: "50"       # Up to 500 IOPS/GB for io2
allowVolumeExpansion: true
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
```

**GCP GKE — SSD Persistent Disk:**

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: kafka-storage
provisioner: pd.csi.storage.gke.io
parameters:
  type: pd-ssd
  replication-type: regional-pd  # For cross-AZ replication
  disk-encryption-kms-key: projects/my-project/locations/us-central1/keyRings/my-ring/cryptoKeys/my-key
allowVolumeExpansion: true
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
```

### Key Recommendations

| Parameter | Recommendation | Rationale |
|-----------|---------------|-----------|
| `reclaimPolicy` | **Retain** | Never auto-delete broker/Redis data |
| `volumeBindingMode` | **WaitForFirstConsumer** | Ensures PV provisioned in correct AZ |
| `allowVolumeExpansion` | **true** | Enables online PVC resizing |
| `fsType` | **ext4 or xfs** | Both work; xfs often better for Kafka |
| IOPS | **3000+ for Kafka**, 1000+ for Redis | Kafka is I/O heavy |
| Encryption | **Always** | Encrypt at rest for compliance |
| Volume size | **Start ≥50Gi Kafka, ≥10Gi Redis** | Leave headroom for growth |

### Kafka JBOD Configuration (Multiple Volumes)

```yaml
storage:
  type: jbod
  volumes:
    - id: 0
      type: persistent-claim
      size: 200Gi
      class: kafka-storage
      deleteClaim: false
    - id: 1
      type: persistent-claim
      size: 200Gi
      class: kafka-storage
      deleteClaim: false
```

### Storage Sizing Formula

**Kafka broker storage:**
```
Storage = (avg_message_size × messages_per_sec × retention_seconds × replication_factor) / producers_count + 20% buffer
```

**Redis storage:**
```
Storage = maxmemory × 2 (for RDB snapshots + AOF overhead) + 10% buffer
```

---

## 5. Resource Allocation Patterns

### Kafka Resource Guidelines

| Cluster Size | CPU (per broker) | Memory (per broker) | IOPS | Notes |
|-------------|-----------------|---------------------|------|-------|
| Small (<10 topics) | 1-2 cores | 4-8 GiB | 3000 | Dev/light production |
| Medium (10-100 topics) | 2-4 cores | 8-16 GiB | 5000-10000 | Typical production |
| Large (100+ topics) | 4-8 cores | 16-32 GiB | 10000+ | High-throughput |
| Tier-1 (critical) | 8+ cores | 32-64 GiB | 15000+ | Financial/trading |

**Kafka JVM heap sizing:**
```yaml
config:
  # Strimzi environment variable for JVM heap
  # Set via Kafka CR
  jvmOptions:
    -Xms: "4g"
    -Xmx: "4g"
    gcLoggingEnabled: true
    javaSystemProperties:
      - name: "io.netty.recycler.maxCapacityPerThread"
        value: "4096"
```

**Example — Production Kafka resource spec:**

```yaml
resources:
  requests:
    cpu: "2000m"
    memory: "8Gi"
  limits:
    cpu: "4000m"
    memory: "16Gi"
```

### Redis Resource Guidelines

| Mode | CPU (per node) | Memory (per node) | IOPS | Notes |
|------|---------------|-------------------|------|-------|
| Standalone | 0.5-1 core | 1-2 GiB | 1000 | Dev, caches |
| Replication | 1-2 cores | 4-8 GiB | 3000 | Production cache |
| Cluster | 2-4 cores | 8-16 GiB | 5000 | High-throughput |
| Trading-grade | 4-8 cores | 16-32 GiB | 10000+ | State storage |

**Example — Redis resource spec:**

```yaml
resources:
  requests:
    cpu: "1000m"
    memory: "4Gi"
  limits:
    cpu: "2000m"
    memory: "8Gi"
```

### Network Bandwidth Considerations

**Kafka:**
- Broker-to-broker: replication traffic can saturate network
- Client-to-broker: depends on producer/consumer throughput
- **Recommendation:** Use nodes with ≥5 Gbps network, ideally 10-25 Gbps for production
- Enable TCP keepalive: `socket.timeout.ms=30000`

**Redis:**
- Generally lower bandwidth than Kafka (smaller values, higher QPS)
- **Recommendation:** ≥2 Gbps for production cluster

### Resource quotas per namespace

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: kafka-quota
  namespace: kafka
spec:
  hard:
    requests.cpu: "32"
    requests.memory: 64Gi
    limits.cpu: "64"
    limits.memory: 128Gi
    persistentvolumeclaims: "20"
```

---

## 6. Scaling Strategies

### 6.1 Manual Scaling

**Kafka (Strimzi):**

```bash
# Scale brokers up
kubectl edit kafka wt-kafka -n kafka
# Change spec.kafka.replicas: 3 → 5

# Rebalance partitions after scaling
kubectl apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaRebalance
metadata:
  name: wt-rebalance
  namespace: kafka
  labels:
    strimzi.io/cluster: wt-kafka
spec:
  goals:
    - NetworkInboundCapacityGoal
    - NetworkOutboundCapacityGoal
    - DiskCapacityGoal
    - ReplicaCapacityGoal
EOF
```

**Redis (manual replica scaling):**

```bash
helm upgrade wt-redis bitnami/redis \
  --set replica.replicaCount=4 \
  -n redis
```

### 6.2 Horizontal Pod Autoscaler (HPA)

**Note:** HPA does NOT directly scale Kafka brokers or Redis data nodes (StatefulSets with data affinity challenges). HPA is used for:

- Kafka Connect workers
- Kafka Bridge pods
- Application producers/consumers
- Redis proxy/gateway layers

**HPA for Kafka Connect:**

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kafka-connect-hpa
  namespace: kafka
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: wt-kafka-connect
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
    - type: Pods
      pods:
        metric:
          name: kafka_connect_active_tasks
        target:
          type: AverageValue
          averageValue: "50"
```

### 6.3 Vertical Pod Autoscaler (VPA)

**Caution:** VPA + StatefulSets = pod restarts (VPA updates by evicting pods). Use VPA only in recommendation mode for Kafka/Redis, or during maintenance windows.

**Install VPA:**

```bash
kubectl apply -f https://github.com/kubernetes/autoscaler/releases/download/vertical-pod-autoscaler-1.1.0/vpa-v1-crd-gen.yaml
kubectl apply -f https://github.com/kubernetes/autoscaler/releases/download/vertical-pod-autoscaler-1.1.0/vpa-rbac.yaml
kubectl apply -f https://github.com/kubernetes/autoscaler/releases/download/vertical-pod-autoscaler-1.1.0/vpa-admission-controller.yaml
kubectl apply -f https://github.com/kubernetes/autoscaler/releases/download/vertical-pod-autoscaler-1.1.0/vpa-recommender.yaml
```

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: kafka-vpa
  namespace: kafka
spec:
  targetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: wt-kafka-kafka
  updatePolicy:
    updateMode: "Off"            # "Recommendation" mode — no auto-eviction
  resourcePolicy:
    containerPolicies:
      - containerName: kafka
        minAllowed:
          cpu: 2000m
          memory: 4Gi
        maxAllowed:
          cpu: 8000m
          memory: 32Gi
```

### 6.4 Kubernetes Event-Driven Autoscaling (KEDA)

**For scaling consumers based on Kafka lag:**

**Source:** https://keda.sh/docs/2.16/scalers/apache-kafka/

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
        topic: trading-events
        lagThreshold: "1000"
        allowIdleConsumers: "false"
    - type: cpu
      metricType: Utilization
      metadata:
        value: "70"
```

---

## 7. Monitoring with Prometheus/Grafana

### 7.1 Kafka Monitoring

**Strimzi Kafka Exporter** — included with Strimzi operator:

**Metrics ConfigMap:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kafka-metrics
  namespace: kafka
  labels:
    app: strimzi
data:
  kafka-metrics-config.yml: |
    lowercaseOutputName: true
    rules:
      # Topic metrics
      - pattern: kafka.server<type=(.+), name=(.+), topic=(.+)><>Value
        name: kafka_server_$1_$2
        labels:
          topic: "$3"
      # Broker metrics
      - pattern: kafka.server<type=(.+), name=(.+)><>Value
        name: kafka_server_$1_$2
      # Controller metrics
      - pattern: kafka.controller<type=(.+), name=(.+)><>Value
        name: kafka_controller_$1_$2
      # Producer/consumer metrics
      - pattern: kafka.server<type=(.+), client-id=(.+)><>Value
        name: kafka_server_$1
        labels:
          client-id: "$2"
      # JMX metrics
      - pattern: java.lang<type=(.+), name=(.+)><>Value
        name: java_lang_$1_$2
```

**ServiceMonitor for Kafka Exporter:**

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: kafka-monitor
  namespace: monitoring
spec:
  selector:
    matchLabels:
      strimzi.io/kind: Kafka
      strimzi.io/name: wt-kafka
  namespaceSelector:
    matchNames:
      - kafka
  endpoints:
    - port: metrics
      interval: 15s
      path: /metrics
```

**Key Kafka Metrics to Monitor:**

| Metric | Alert Threshold | Description |
|--------|----------------|-------------|
| `kafka_server_BrokerTopicMetrics_MessagesInPerSec` | < expected baseline | Message throughput |
| `kafka_server_UnderReplicatedPartitions` | > 0 | Under-replicated partitions |
| `kafka_controller_KafkaController_OfflinePartitionsCount` | > 0 | Offline partitions (critical) |
| `kafka_server_ReplicaManager_IsrShrinksPerSec` | > 0 sustained | ISR shrinking |
| `kafka_network_RequestMetrics_RequestsPerSec` | > baseline + 3σ | Request rate spike |
| `kafka_server_SessionExpireListener_ZooKeeperDisconnectsPerSec` | > 0 | ZK connectivity (if used) |
| `kafka_log_LogFlushRateAndTimeMs` | > 1000ms | Disk flush latency |

### 7.2 Redis Monitoring

**Redis Exporter** (oliver006/redis_exporter):

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: redis-monitor
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: redis-exporter
  namespaceSelector:
    matchNames:
      - redis
  endpoints:
    - port: metrics
      interval: 15s
      path: /metrics
```

**Key Redis Metrics to Monitor:**

| Metric | Alert Threshold | Description |
|--------|----------------|-------------|
| `redis_memory_used_bytes` | > 90% of maxmemory | Memory pressure |
| `redis_connected_clients` | > 80% of maxclients | Connection pool |
| `redis_rejected_connections_total` | > 0 | Connection rejections |
| `redis_commands_per_sec` | < baseline - 50% | Throughput drop |
| `redis_keyspace_hits / (hits + misses)` | < 0.8 (for caches) | Cache hit rate |
| `redis_replication_offset_lag` | > 1000 keys | Replication lag |
| `redis_rdb_last_bgsave_status` | != 1 | RDB save failure |
| `redis_aof_last_bgrewrite_status` | != 1 | AOF rewrite failure |

### 7.3 Grafana Dashboards

**Recommended dashboards (import by ID):**

| Dashboard | ID | Source |
|-----------|-----|--------|
| Kafka Overview | 7589 | Grafana.com |
| Kafka Exporter Overview | 9628 | Grafana.com |
| Strimzi Kafka | 11176 | Grafana.com |
| Redis Dashboard (Redis Exporter) | 763 | Grafana.com |
| Redis Cluster | 12691 | Grafana.com |

### 7.4 Alerting Rules

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: kafka-alerts
  namespace: monitoring
spec:
  groups:
    - name: kafka.rules
      interval: 30s
      rules:
        - alert: KafkaUnderReplicatedPartitions
          expr: kafka_server_ReplicationManager_UnderReplicatedPartitions > 0
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "Kafka has under-replicated partitions"
        - alert: KafkaOfflinePartitions
          expr: kafka_controller_KafkaController_OfflinePartitionsCount > 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Kafka has offline partitions — data loss risk"
        - alert: KafkaBrokerDown
          expr: up{job="kafka"} == 0
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "Kafka broker {{ $labels.instance }} is down"
```

---

## 8. Backup and Restore Patterns

### 8.1 Velero for Cluster-Wide Backups

**Source:** https://velero.io/docs/
**GitHub:** https://github.com/vmware-tanzu/velero

**Install Velero (AWS S3 example):**

```bash
velero install \
  --provider aws \
  --bucket wt-k8s-backups \
  --secret-file ./velero-aws-credentials \
  --backup-location-config region=us-east-1 \
  --snapshot-location-config region=us-east-1 \
  --use-volume-snapshots=true
```

**Velero backup for Kafka namespace:**

```bash
# Schedule daily backups
velero schedule create kafka-daily \
  --schedule="0 2 * * *" \
  --include-namespaces kafka \
  --snapshot-volumes=true \
  --ttl 720h  # 30 day retention

# On-demand backup
velero backup create kafka-pre-upgrade \
  --include-namespaces kafka \
  --snapshot-volumes=true \
  --wait

# Restore
velero restore create --from-backup kafka-pre-upgrade
```

**Velero for Redis namespace:**

```bash
velero schedule create redis-daily \
  --schedule="0 3 * * *" \
  --include-namespaces redis \
  --snapshot-volumes=true \
  --ttl 720h
```

**Limitations of Velero for Kafka/Redis:**
- Volume snapshots are crash-consistent, not application-consistent
- For Kafka: consider using MirrorMaker 2 for cross-cluster replication instead
- For Redis: prefer native RDB/AOF exports for point-in-time recovery

### 8.2 Kafka MirrorMaker 2 (Cross-Cluster Replication)

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
      config:
        config.storage.replication.factor: -1
        offset.storage.replication.factor: -1
        status.storage.replication.factor: -1
    - alias: "kafka-target"
      bootstrapServers: target-kafka-bootstrap.target.svc:9092
      config:
        config.storage.replication.factor: 3
        offset.storage.replication.factor: 3
        status.storage.replication.factor: 3
  mirrors:
    - sourceCluster: "kafka-source"
      targetCluster: "kafka-target"
      sourceConnector:
        config:
          replication.factor: 3
          offset-syncs.topic.replication.factor: 3
          sync.topic.acls.enabled: "false"
          sync.topic.configs.enabled: "true"
      heartbeatConnector:
        config:
          heartbeats.topic.replication.factor: 3
      checkpointConnector:
        config:
          checkpoints.topic.replication.factor: 3
      topicsPattern: "wt-.*"      # Mirror only wt- prefixed topics
      groupsPattern: "wt-.*"      # Mirror consumer group offsets
```

**Active-Active vs Active-Passive:**

| Pattern | Use Case | Complexity |
|---------|----------|------------|
| Active-Passive | DR failover | Low |
| Active-Active | Multi-region reads | High (offset syncing needed) |

### 8.3 Redis RDB Snapshots + AOF

**Configure RDB snapshots via ConfigMap:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-config
  namespace: redis
data:
  redis.conf: |
    save 900 1        # After 900s if 1 key changed
    save 300 10       # After 300s if 10 keys changed
    save 60 10000     # After 60s if 10000 keys changed
    rdbcompression yes
    rdbchecksum yes
    dbfilename dump.rdb
    appendonly yes
    appendfsync everysec
    dir /data
```

**Automated backup via CronJob (push to S3/GCS):**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: redis-backup
  namespace: redis
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: redis-backup
              image: bitnami/redis:7.4
              command:
                - /bin/bash
                - -c
                - |
                  # Trigger BGSAVE on master
                  redis-cli -h wt-redis-master.redis.svc -a $REDIS_PASSWORD BGSAVE
                  sleep 10
                  # Check if save completed
                  redis-cli -h wt-redis-master.redis.svc -a $REDIS_PASSWORD LASTSAVE
                  # Copy dump.rdb to backup location
                  # (Requires shared volume or kubectl cp)
                  # Then upload to S3
                  aws s3 cp /data/dump.rdb s3://wt-redis-backups/$(date +%Y%m%d-%H%M%S)/dump.rdb
              env:
                - name: REDIS_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: redis-credentials
                      key: redis-password
              volumeMounts:
                - name: redis-data
                  mountPath: /data
          volumes:
            - name: redis-data
              persistentVolumeClaim:
                claimName: wt-redis-master-0
          restartPolicy: OnFailure
```

---

## 9. Network Policies for Data Plane Isolation

**Source:** https://kubernetes.io/docs/concepts/services-networking/network-policies/

### 9.1 Kafka Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: kafka-network-policy
  namespace: kafka
spec:
  podSelector:
    matchLabels:
      strimzi.io/kind: Kafka
      strimzi.io/name: wt-kafka
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow client (producer/consumer) connections
    - from:
        - namespaceSelector:
            matchLabels:
              app-network: data-plane
        - podSelector:
            matchLabels:
              app.kubernetes.io/part-of: wt-trading
      ports:
        - port: 9092   # Plain
        - port: 9093   # TLS
    # Allow intra-cluster broker communication
    - from:
        - podSelector:
            matchLabels:
              strimzi.io/kind: Kafka
      ports:
        - port: 9092
        - port: 9093
        - port: 9091   # Controller communication (KRaft)
        - port: 2888   # Controller-to-controller (KRaft)
        - port: 3888   # Controller election (KRaft)
    # Allow Prometheus scraping
    - from:
        - namespaceSelector:
            matchLabels:
              monitoring: enabled
      ports:
        - port: 9404   # JMX Exporter
  egress:
    # Allow DNS resolution
    - to:
        - namespaceSelector: {}
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
    # Allow broker-to-broker communication
    - to:
        - podSelector:
            matchLabels:
              strimzi.io/kind: Kafka
      ports:
        - port: 9092
        - port: 9093
        - port: 9091
        - port: 2888
        - port: 3888
```

### 9.2 Redis Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-network-policy
  namespace: redis
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: redis
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow client connections
    - from:
        - namespaceSelector:
            matchLabels:
              app-network: data-plane
        - podSelector:
            matchLabels:
              app.kubernetes.io/part-of: wt-trading
      ports:
        - port: 6379   # Client
        - port: 16379  # Cluster bus (gossip)
    # Allow intra-Redis communication
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: redis
      ports:
        - port: 6379
        - port: 16379  # Cluster gossip
        - port: 26379  # Sentinel (if enabled)
    # Allow Prometheus scraping
    - from:
        - namespaceSelector:
            matchLabels:
              monitoring: enabled
      ports:
        - port: 9121   # Redis Exporter
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {}
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
    # Allow intra-Redis communication (gossip, replication)
    - to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: redis
      ports:
        - port: 6379
        - port: 16379
        - port: 26379
```

### 9.3 Default Deny Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: kafka
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress

# Same for redis namespace
```

### 9.4 CNI Plugin Recommendations

| CNI | Network Policy Support | Notes |
|-----|----------------------|-------|
| Calico | Full | Best K8s-native option, eBGP support |
| Cilium | Full + L7 | eBPF-based, can inspect Kafka protocol |
| Amazon VPC | Limited | Network Policy via Security Groups (CNI v1.14+) |
| Weave Net | Full | Good for simple setups, deprecated |

**Cilium for Kafka protocol-level policies:**

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: kafka-l7-policy
  namespace: kafka
spec:
  endpointSelector:
    matchLabels:
      app: wt-producer
  ingress:
    - toPorts:
        - ports:
            - port: "9092"
              protocol: TCP
          rules:
            kafka:
              - role: "produce"
                topic: "wt-trading-events"
              - role: "consume"
                topic: "wt-trading-events"
                group: "wt-consumer-group"
```

---

## 10. Complete Reference Architecture

### Directory Structure

```
infra/
├── helm-values/
│   ├── kafka/
│   │   ├── values-production.yaml
│   │   └── kafka-metrics-config.yml
│   ├── redis/
│   │   ├── values-production.yaml
│   │   └── redis.conf
│   └── monitoring/
│       ├── prometheus-values.yaml
│       └── grafana-values.yaml
├── kustomize/
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── namespaces.yaml
│   │   └── network-policies/
│   │       ├── kafka-network-policy.yaml
│   │       └── redis-network-policy.yaml
│   └── overlays/
│       ├── staging/
│       └── production/
├── velero/
│   ├── schedules.yaml
│   └── credentials
└── scripts/
    ├── backup-redis.sh
    ├── restore-redis.sh
    └── verify-kafka-replication.sh
```

### Namespace Layout

```
┌─────────────────────────────────────────────────┐
│  Cluster                                        │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐ │
│  │ kafka    │  │ redis    │  │ monitoring     │ │
│  │ ns       │  │ ns       │  │ ns             │ │
│  │          │  │          │  │                │ │
│  │ - Kafka  │  │ - Redis  │  │ - Prometheus   │ │
│  │   brokers│  │   cluster│  │ - Grafana      │ │
│  │ - Connect│  │ - Exporter│ │ - Alertmanager │ │
│  │ - MM2    │  │          │  │                │ │
│  └──────────┘  └──────────┘  └────────────────┘ │
│                                                  │
│  ┌──────────┐  ┌──────────┐                     │
│  │ wt-app   │  │ velero   │                     │
│  │ ns       │  │ ns       │                     │
│  │          │  │          │                     │
│  │ -Trading │  │ -Backup  │                     │
│  │  services│  │  schedules│                    │
│  └──────────┘  └──────────┘                     │
└─────────────────────────────────────────────────┘
```

### Deployment Order

```
1. Install cert-manager (required by operators)
   helm install cert-manager jetstack/cert-manager --set installCRDs=true

2. Install Prometheus Stack (needed before data plane)
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm install prometheus prometheus-community/kube-prometheus-stack

3. Install Strimzi Operator
   helm install strimzi strimzi/strimzi-kafka-operator --namespace kafka --create-namespace

4. Install Redis Operator (or Bitnami charts)
   helm install wt-redis bitnami/redis --namespace redis --create-namespace -f values-production.yaml

5. Deploy Kafka cluster (KRaft)
   kubectl apply -f kafka-cluster.yaml

6. Deploy topics and users
   kubectl apply -f kafka-topics.yaml
   kubectl apply -f kafka-users.yaml

7. Configure monitoring (ServiceMonitors, Grafana dashboards)

8. Configure network policies

9. Set up Velero backup schedules

10. Deploy MirrorMaker 2 (if DR needed)
```

---

## Sources and References

### Kafka
1. Strimzi Official Documentation — https://strimzi.io/documentation/
2. Strimzi GitHub Repository — https://github.com/strimzi/strimzi-kafka-operator
3. Apache Kafka KRaft Documentation — https://kafka.apache.org/documentation/#kraft
4. Confluent Operator Documentation — https://docs.confluent.io/operator/current/overview.html
5. Confluent Helm Charts — https://github.com/confluentinc/cp-helm-charts
6. KEDA Kafka Scaler — https://keda.sh/docs/2.16/scalers/apache-kafka/
7. Strimzi Kafka Rebalance — https://strimzi.io/docs/operators/latest/deploying.html#assembly-using-cruise-control-str

### Redis
8. Bitnami Redis Helm Chart — https://github.com/bitnami/charts/tree/main/bitnami/redis
9. Bitnami Redis Documentation — https://docs.bitnami.com/kubernetes/infrastructure/redis/
10. Redis Operator (OpsTree/Spot) — https://github.com/RedisLabs/redis-operator
11. Redis Enterprise Kubernetes Docs — https://docs.redis.com/latest/kubernetes/
12. Redis Exporter — https://github.com/oliver006/redis_exporter
13. Spotahome Redis Operator — https://github.com/spotahome/redis-operator

### Kubernetes Stateful Applications
14. Kubernetes StatefulSet Best Practices — https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/
15. Kubernetes Storage Classes — https://kubernetes.io/docs/concepts/storage/storage-classes/
16. AWS EBS CSI Driver — https://github.com/kubernetes-sigs/aws-ebs-csi-driver
17. Kubernetes Network Policies — https://kubernetes.io/docs/concepts/services-networking/network-policies/

### Monitoring
18. Prometheus Community Helm Charts — https://github.com/prometheus-community/helm-charts
19. Grafana Kafka Dashboards — https://grafana.com/grafana/dashboards/7589
20. Grafana Redis Dashboards — https://grafana.com/grafana/dashboards/763
21. Kafka JMX Prometheus Exporter — https://github.com/prometheus/jmx_exporter

### Backup
22. Velero Documentation — https://velero.io/docs/
23. Velero GitHub — https://github.com/vmware-tanzu/velero
24. Kafka MirrorMaker 2 Documentation — https://kafka.apache.org/documentation/#georeplication

### CNPs / CNI
25. Cilium Documentation — https://docs.cilium.io/en/stable/
26. Calico Documentation — https://projectcalico.docs.tigera.io/

---

## Quick Reference: Production Defaults

| Parameter | Kafka | Redis Cluster |
|-----------|-------|---------------|
| Replicas | 3 (minimum) | 6 (3m + 3r, minimum) |
| CPU request | 2000m | 1000m |
| Memory request | 8Gi | 4Gi |
| PVC size | 100Gi | 10-20Gi |
| Storage class | gp3/io2 (AWS), pd-ssd (GCP) | gp3 (AWS), pd-ssd (GCP) |
| Network | 5-25 Gbps | 2-10 Gbps |
| Backup | MirrorMaker2 + Velero snapshots | RDB CronJob + Velero |
| Monitoring | JMX Exporter + ServiceMonitor | Redis Exporter + ServiceMonitor |
| PDB | minAvailable: 2 | minAvailable: 3 |
| Termination grace | 60s | 30s |
| HPA | KEDA for consumers | N/A (stateful) |
| VPA | Recommendation mode only | Recommendation mode only |
