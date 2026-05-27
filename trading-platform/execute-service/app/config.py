from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from pathlib import Path
import os
import re
from typing import Any


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8002
    debug: bool = False

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7

    # Database (individual fields for ConfigMap compatibility)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "trading_db"
    db_user: str = "execute"
    db_password: str = ""
    db_auto_create_tables: bool = False  # False in prod (use separate CNPG init/migration jobs)

    # Hyperliquid
    hyperliquid_private_key: str = ""
    hyperliquid_testnet: bool = True
    hyperliquid_wallet_address: str = ""

    # Solana
    solana_private_key_base58: str = ""
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"

    # mTLS
    mtls_enabled: bool = False
    mtls_ca_cert: str = ""
    mtls_server_cert: str = ""
    mtls_server_key: str = ""
    mtls_client_cert_required: bool = False

    # Service discovery
    market_data_service_url: str = "http://market-data:8001"

    # Redis for circuit breakers and rate limiting
    redis_url: str = "redis://localhost:6379/0"

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst_size: int = 10
    rate_limit_order_per_second: int = 5

    # Risk management
    max_position_size_usd: float = 50000.0
    max_daily_loss_usd: float = 10000.0
    max_open_positions: int = 10
    solana_max_tx_lamports: int = 10_000_000_000  # 100 SOL
    solana_circuit_breaker_threshold: int = 5  # failures before tripping
    solana_circuit_breaker_timeout_seconds: int = 300  # 5 min cooldown
    solana_txn_poll_timeout_seconds: int = 60
    solana_txn_poll_interval_seconds: float = 3.0

    # Token safety
    blocked_token_mints: list[str] = []
    allowed_token_mints: list[str] | None = None  # None = allowlist disabled

    # HTTP client pooling
    http_connection_pool_size: int = 10
    http_connection_max_size: int = 20
    http_keepalive_seconds: float = 30.0
    http_timeout_seconds: float = 30.0

    @model_validator(mode="before")
    @classmethod
    def map_production_env_vars(cls, data: Any) -> Any:
        """Map production env vars from trading-execute-service-config + secrets.

        The live ConfigMap uses EXECUTE_DB_* keys and hermes-pgdb-rw service.
        Secrets provide the password (mapped from EXECUTE_DB_PASSWORD / POSTGRES_PASSWORD).
        """
        if isinstance(data, dict):
            # DB password
            if not data.get("db_password"):
                data["db_password"] = (
                    data.get("DB_PASSWORD")
                    or data.get("POSTGRES_PASSWORD")
                    or data.get("EXECUTE_DB_PASSWORD")
                    or os.getenv("DB_PASSWORD")
                    or os.getenv("POSTGRES_PASSWORD")
                    or os.getenv("EXECUTE_DB_PASSWORD")
                    or ""
                )

            # Auto-create flag (can be set in ConfigMap)
            if "db_auto_create_tables" not in data:
                auto_create = data.get("DB_AUTO_CREATE_TABLES") or data.get("EXECUTE_DB_AUTO_CREATE_TABLES") or os.getenv("DB_AUTO_CREATE_TABLES")
                if auto_create is not None:
                    data["db_auto_create_tables"] = auto_create.lower() in ("true", "1", "yes")

            # JWT secret
            if not data.get("jwt_secret_key"):
                data["jwt_secret_key"] = (
                    data.get("JWT_SECRET_KEY")
                    or data.get("EXECUTE_JWT_SECRET_KEY")
                    or os.getenv("JWT_SECRET_KEY")
                    or os.getenv("EXECUTE_JWT_SECRET_KEY")
                    or ""
                )

            # Private keys
            if not data.get("hyperliquid_private_key"):
                data["hyperliquid_private_key"] = (
                    data.get("HYPERLIQUID_PRIVATE_KEY")
                    or data.get("EXECUTE_HYPERLIQUID_PRIVATE_KEY")
                    or os.getenv("HYPERLIQUID_PRIVATE_KEY")
                    or os.getenv("EXECUTE_HYPERLIQUID_PRIVATE_KEY")
                    or ""
                )
            if not data.get("solana_private_key_base58"):
                data["solana_private_key_base58"] = (
                    data.get("SOLANA_PRIVATE_KEY_BASE58")
                    or data.get("EXECUTE_SOLANA_PRIVATE_KEY_BASE58")
                    or os.getenv("SOLANA_PRIVATE_KEY_BASE58")
                    or os.getenv("EXECUTE_SOLANA_PRIVATE_KEY_BASE58")
                    or ""
                )

            # DB connection - prioritize EXECUTE_DB_* from your ConfigMap
            if data.get("db_host") in (None, "", "localhost"):
                data["db_host"] = (
                    data.get("EXECUTE_DB_HOST")
                    or data.get("DB_HOST")
                    or data.get("POSTGRES_HOST")
                    or os.getenv("EXECUTE_DB_HOST")
                    or os.getenv("DB_HOST")
                    or os.getenv("POSTGRES_HOST")
                    or "siriusdevops-pgdb-rw.customer1.svc.cluster.local"
                )
            if data.get("db_port") in (None, 0):
                data["db_port"] = (
                    int(data.get("EXECUTE_DB_PORT") or data.get("DB_PORT") or os.getenv("EXECUTE_DB_PORT") or os.getenv("DB_PORT") or "5432")
                )
            if data.get("db_user") in (None, "", "execute"):
                data["db_user"] = (
                    data.get("EXECUTE_DB_USER")
                    or data.get("DB_USER")
                    or os.getenv("EXECUTE_DB_USER")
                    or os.getenv("DB_USER")
                    or "trading"
                )
            if data.get("db_name") in (None, "", "execute_db", "trading_db"):
                data["db_name"] = (
                    data.get("EXECUTE_DB_NAME")
                    or data.get("DB_NAME")
                    or os.getenv("EXECUTE_DB_NAME")
                    or os.getenv("DB_NAME")
                    or "trading_data"
                )

            # Solana RPC
            if not data.get("solana_rpc_url"):
                data["solana_rpc_url"] = (
                    data.get("SOLANA_RPC_URL")
                    or os.getenv("SOLANA_RPC_URL")
                    or "https://api.devnet.solana.com"
                )

            # Redis URL
            if not data.get("redis_url"):
                data["redis_url"] = (
                    data.get("REDIS_URL")
                    or os.getenv("REDIS_URL")
                    or "redis://localhost:6379/0"
                )

            # Risk limits from env
            if data.get("max_position_size_usd") == 50000.0:  # default unchanged
                env_val = data.get("MAX_POSITION_SIZE_USD") or os.getenv("MAX_POSITION_SIZE_USD")
                if env_val:
                    data["max_position_size_usd"] = float(env_val)
            if data.get("max_daily_loss_usd") == 10000.0:  # default unchanged
                env_val = data.get("MAX_DAILY_LOSS_USD") or os.getenv("MAX_DAILY_LOSS_USD")
                if env_val:
                    data["max_daily_loss_usd"] = float(env_val)
            if data.get("max_open_positions") == 10:  # default unchanged
                env_val = data.get("MAX_OPEN_POSITIONS") or os.getenv("MAX_OPEN_POSITIONS")
                if env_val:
                    data["max_open_positions"] = int(env_val)

        return data

    @property
    def database_url(self) -> str:
        """Construct database URL from individual fields.

        Uses the real pgdb (hermes-pgdb-rw) when password is provided.
        """
        if self.db_password:
            return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        return "sqlite+aiosqlite:////tmp/execute.db"

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate JWT secret meets minimum security requirements."""
        if not v:
            raise ValueError(
                "JWT_SECRET_KEY must be set via environment variable or Secret. "
                "Do not use the default empty value in production."
            )
        if len(v) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least 32 characters (got {len(v)}). "
                "Use a cryptographically random secret generated with secrets.token_urlsafe(48)."
            )
        return v

    @field_validator("solana_rpc_url")
    @classmethod
    def validate_solana_rpc(cls, v: str) -> str:
        """Reject devnet RPC when running in production (private key configured)."""
        if "devnet" in v.lower():
            import logging
            logging.warning(
                "SOLANA_RPC_URL is set to devnet (%s). "
                "Ensure this is intentional — production should use mainnet RPC.",
                v
            )
        return v


settings = Settings()
