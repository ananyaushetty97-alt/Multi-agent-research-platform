"""
Shared configuration for the memory module.
Reads values from environment variables (populated from your local .env file).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MemorySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Redis (STM)
    redis_url: str = "redis://localhost:6379/0"
    stm_ttl_seconds: int = 3600  # 1 hour default session TTL

    # Postgres (LTM)
    postgres_dsn: str = "postgresql://postgres:devpassword@localhost:5432/research_platform"

    # Embedding model (local, free, no API key needed)
    embedding_model_name: str = "all-MiniLM-L6-v2"

    # Semantic cache
    cache_similarity_threshold: float = 0.90
    cache_ttl_seconds: int = 86400  # 24 hours default cache entry lifetime


settings = MemorySettings()
