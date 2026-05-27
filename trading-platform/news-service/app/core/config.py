"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "news-analyst-service"
    debug: bool = False

    # PostgreSQL (CNPG news database)
    db_user: str = "trading"
    db_password: str = ""
    db_host: str = "siriusdevops-pgdb-rw.customer1.svc.cluster.local"
    db_port: int = 5432
    db_name: str = "trading_data"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Kafka
    kafka_bootstrap_servers: str = "trading-kafka.customer1.svc.cluster.local:9092"
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


    # PostgreSQL (secondary DB: news_app_db for scraper articles — read-only)
    news_db_host: str = "siriusdevops-pgdb-rw.customer1.svc.cluster.local"
    news_db_port: int = 5432
    news_db_name: str = "news_app_db"
    news_db_user: str = "news_app"
    news_db_password: str = ""
    news_db_pool_size: int = 2
    news_db_max_overflow: int = 5

    @property
    def news_db_url(self) -> str:
        if self.news_db_password:
            return f"postgresql+asyncpg://{self.news_db_user}:{self.news_db_password}@{self.news_db_host}:{self.news_db_port}/{self.news_db_name}"
        return f"postgresql+asyncpg://{self.news_db_user}@{self.news_db_host}:{self.news_db_port}/{self.news_db_name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
