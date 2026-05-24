from pydantic_settings import BaseSettings
from pydantic import field_validator
from pathlib import Path


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7

    # Database (individual fields for ConfigMap compatibility)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "execute_db"
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

    @property
    def database_url(self) -> str:
        """Construct database URL from individual fields.
        
        Falls back to SQLite on /tmp/execute.db when no password is set
        (local dev mode). Uses PostgreSQL+asyncpg when DB_PASSWORD is provided.
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
