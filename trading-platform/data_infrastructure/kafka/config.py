"""Kafka configuration for market data pipeline."""
from pydantic_settings import BaseSettings
from typing import Optional


class KafkaSettings(BaseSettings):
    # Connection — comma-separated brokers
    bootstrap_servers: str = "localhost:9092"

    # Security (mTLS for prod)
    sasl_mechanism: Optional[str] = None
    sasl_plain_username: Optional[str] = None
    sasl_plain_password: Optional[str] = None
    ssl_cafile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None

    # Producer defaults
    producer_acks: str = "all"          # all = ISR acknowledgment
    producer_compression: str = "lz4"    # lz4 = best throughput/CPU ratio
    producer_linger_ms: int = 5
    producer_batch_size: int = 32768     # 32 KB

    # Consumer defaults
    consumer_group_id: str = "market-data-workers"
    consumer_auto_offset_reset: str = "earliest"
    consumer_max_poll_records: int = 500

    # Topic defaults
    default_partitions: int = 6
    default_replication_factor: int = 1  # 3 for prod

    model_config = {"env_prefix": "KAFKA_", "env_file": ".env", "extra": "ignore"}


kafka_settings = KafkaSettings()
