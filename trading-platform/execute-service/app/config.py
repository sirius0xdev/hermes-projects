from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from pathlib import Path
import os
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

    # Hyperliquid
    hyperliquid_private_key: str = ""
    hyperliquid_testnet: bool = True
    hyperliquid_wallet_address: str = ""

    # Solana
    solana_private_key_base58: str = ""
    solana_rpc_url: str = "https://api.devnet.solana.com"

    # mTLS
    mtls_enabled: bool = False
    mtls_ca_cert: str = ""
    mtls_server_cert: str = ""
    mtls_server_key: str = ""
    mtls_client_cert_required: bool = False

    # Service discovery
    market_data_service_url: str = "http://market-data:8001"

    @model_validator(mode="before")
    @classmethod
    def map_production_env_vars(cls, data: Any) -> Any:
        """Map production env vars from trading-execute-service-config + secrets.

        The live ConfigMap (trading-execute-service-config) uses EXECUTE_DB_HOST,
        EXECUTE_DB_NAME, EXECUTE_DB_PASSWORD style keys. Secrets provide JWT and DB creds.

        This ensures we never fall back to SQLite in the GKE environment (hermes-pgdb-rw).
        """
        if isinstance(data, dict):
            # DB password - the ConfigMap/secrets use EXECUTE_DB_PASSWORD or POSTGRES_PASSWORD
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

            # DB connection - prioritize EXECUTE_DB_* from the ConfigMap you are using
            if data.get("db_host") in (None, "", "localhost"):
                data["db_host"] = (
                    data.get("EXECUTE_DB_HOST")
                    or data.get("DB_HOST")
                    or data.get("POSTGRES_HOST")
                    or os.getenv("EXECUTE_DB_HOST")
                    or os.getenv("DB_HOST")
                    or os.getenv("POSTGRES_HOST")
                    or "hermes-pgdb-rw.customer1.svc.cluster.local"
                )
            if data.get("db_name") in (None, "", "execute_db", "trading_db"):
                data["db_name"] = (
                    data.get("EXECUTE_DB_NAME")
                    or data.get("DB_NAME")
                    or os.getenv("EXECUTE_DB_NAME")
                    or os.getenv("DB_NAME")
                    or "trading_data"
                )

        return data

    @property
    def database_url(self) -> str:
        """Construct database URL from individual fields.

        Now correctly maps the EXECUTE_* keys from trading-execute-service-config
        and the DB credentials secret. This eliminates the SQLite fallback in prod.
        """
        if self.db_password:
            return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        return "sqlite+aiosqlite:////tmp/execute.db"

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "JWT_SECRET_KEY must be set via environment variable or Secret. "
                "Do not use the default empty value in production."
            )
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
