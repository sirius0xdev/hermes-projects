"""Simulation service configuration."""
from __future__ import annotations

import os
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8006
    debug: bool = False

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "trading_data"
    db_user: str = "trading"
    db_password: str = ""
    db_auto_create_tables: bool = False

    # Service discovery
    data_service_url: str = "http://data-service:8001"
    execute_service_url: str = "http://execute-service:8002"

    # Simulation defaults
    mc_simulations: int = 10000
    mc_time_horizon_days: int = 30
    mc_confidence_level: float = 0.95
    mc_initial_capital: float = 100_000.0
    mc_max_position_pct: float = 0.25

    @model_validator(mode="before")
    @classmethod
    def map_production_env_vars(cls, data: Any) -> Any:
        """Map production env vars from ConfigMap + secrets."""
        if isinstance(data, dict):
            # DB password
            if not data.get("db_password"):
                data["db_password"] = (
                    data.get("DB_PASSWORD")
                    or data.get("POSTGRES_PASSWORD")
                    or data.get("SIMULATION_DB_PASSWORD")
                    or os.getenv("DB_PASSWORD")
                    or os.getenv("POSTGRES_PASSWORD")
                    or os.getenv("SIMULATION_DB_PASSWORD")
                    or ""
                )

            # Auto-create flag
            if "db_auto_create_tables" not in data:
                auto_create = data.get("DB_AUTO_CREATE_TABLES") or data.get("SIMULATION_DB_AUTO_CREATE_TABLES") or os.getenv("DB_AUTO_CREATE_TABLES")
                if auto_create is not None:
                    data["db_auto_create_tables"] = auto_create.lower() in ("true", "1", "yes")

            # DB connection
            if data.get("db_host") in (None, "", "localhost"):
                data["db_host"] = (
                    data.get("SIMULATION_DB_HOST")
                    or data.get("DB_HOST")
                    or data.get("POSTGRES_HOST")
                    or os.getenv("SIMULATION_DB_HOST")
                    or os.getenv("DB_HOST")
                    or os.getenv("POSTGRES_HOST")
                    or "localhost"
                )

            if data.get("db_user") in (None, "", "trading"):
                data["db_user"] = (
                    data.get("SIMULATION_DB_USER")
                    or data.get("DB_USER")
                    or os.getenv("SIMULATION_DB_USER")
                    or os.getenv("DB_USER")
                    or "trading"
                )

            if data.get("db_name") in (None, "", "trading_data"):
                data["db_name"] = (
                    data.get("SIMULATION_DB_NAME")
                    or data.get("DB_NAME")
                    or os.getenv("SIMULATION_DB_NAME")
                    or os.getenv("DB_NAME")
                    or "trading_data"
                )

            # Service URLs
            if not data.get("data_service_url"):
                data["data_service_url"] = (
                    os.getenv("DATA_SERVICE_URL") or "http://data-service:8001"
                )
            if not data.get("execute_service_url"):
                data["execute_service_url"] = (
                    os.getenv("EXECUTE_SERVICE_URL") or "http://execute-service:8002"
                )

            # Simulation defaults from env
            if "mc_simulations" not in data:
                v = os.getenv("MC_SIMULATIONS")
                if v is not None:
                    data["mc_simulations"] = int(v)
            if "mc_time_horizon_days" not in data:
                v = os.getenv("MC_TIME_HORIZON_DAYS")
                if v is not None:
                    data["mc_time_horizon_days"] = int(v)

        return data

    @property
    def database_url(self) -> str:
        """Construct database URL. Falls back to SQLite for dev."""
        if self.db_password:
            return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        return "sqlite+aiosqlite:////tmp/simulation.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
