"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "news-analyst-service"
    debug: bool = False

    # PostgreSQL (CNPG news database)
    db_user: str = "postgres"
    db_password: str = ""
    db_host: str = "customer1-cnpg"
    db_port: int = 5432
    db_name: str = "news"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "news-analyzer"
    kafka_topic_articles: str = "news.articles"
    kafka_topic_analysis: str = "news.analysis"
    kafka_auto_offset_reset: str = "earliest"

    # NLP
    nlp_sentiment_threshold: float = 0.55
    nlp_min_relevance_score: float = 0.3

    # API
    port: int = 8003
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    @property
    def db_url(self) -> str:
        if self.db_password:
            return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        return f"postgresql+asyncpg://{self.db_user}@{self.db_host}:{self.db_port}/{self.db_name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
