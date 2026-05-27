"""Embedding service configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Embedding model
    model_name: str = "nomic-ai/nomic-embed-text-v1.5"
    model_path: str = ""
    embedding_dimensions: int = 768

    # Redis connection
    redis_url: str = "redis://redis-master:6379/0"

    # Vector index
    vector_index_name: str = "embedding_index"
    vector_index_dimensions: int = 768
    vector_index_algorithm: str = "HNSW"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "EMBEDDING_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
