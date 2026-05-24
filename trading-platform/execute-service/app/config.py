from pydantic_settings import BaseSettings
from pydantic import field_validator
from pathlib import Path


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7

    # Database (SQLite default for dev, asyncpg for prod)
    database_url: str = "sqlite+aiosqlite:////data/execute.db"

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

    @field_validator("database_url")
    @classmethod
    def validate_db(cls, v: str) -> str:
        return v

    model_config = {"env_prefix": "EXECUTE_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
