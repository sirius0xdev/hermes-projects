"""Reasoning service configuration."""

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Reasoning service settings."""

    # LLM / vLLM config
    llm_base_url: str = Field(
        default="http://localhost:8001",
        description="vLLM or OpenAI-compatible API base URL",
    )
    llm_api_key: str = Field(default="", description="API key for LLM endpoint")
    llm_model: str = Field(
        default="meta-llama/Llama-3.3-70B-Instruct",
        description="Model name/ID",
    )
    llm_max_tokens: int = Field(default=4096, description="Max output tokens")
    llm_temperature: float = Field(default=0.7, description="Sampling temperature")

    # Embedding / RAG config
    embedding_service_url: str = Field(
        default="http://localhost:8002",
        description="Embedding service base URL",
    )
    embedding_model: str = Field(
        default="nomic-ai/nomic-embed-text-v1.5",
        description="Embedding model name",
    )
    rag_top_k: int = Field(default=5, description="Top-K docs for RAG retrieval")
    rag_min_similarity: float = Field(
        default=0.7, description="Minimum similarity threshold for RAG"
    )

    # System prompts
    system_prompt_chat: str = Field(
        default=(
            "You are a helpful financial analysis assistant. "
            "Provide clear, data-driven insights about markets, assets, and trading."
        ),
        description="Default system prompt for chat",
    )
    system_prompt_recommend: str = Field(
        default=(
            "You are a financial recommendation engine. "
            "Given market context and user preferences, suggest actionable trading ideas "
            "with risk assessments."
        ),
        description="Default system prompt for recommendations",
    )

    class Config:
        env_prefix = "REASONING_"
        env_file = ".env"
