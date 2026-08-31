"""Configuração centralizada da aplicação."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variáveis de ambiente e defaults da aplicação."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Aplicação
    app_name: str = "Assistente Acadêmico Local"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "academic"
    postgres_password: str = "academic_secret"
    postgres_db: str = "academic_assistant"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    cache_ttl_seconds: int = 60

    # Coletor
    collector_interval_seconds: int = 30
    collector_location_name: str = "Campus Central"
    collector_latitude: float = -23.5505
    collector_longitude: float = -46.6333

    # Fonte de dados (Open-Meteo como proxy de eventos acadêmicos)
    data_source_name: str = "Open-Meteo (Simulação Acadêmica)"
    data_source_type: Literal["api", "scraper", "portal"] = "api"
    data_source_base_url: str = "https://api.open-meteo.com/v1"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Agente IA
    llm_provider: Literal["ollama", "openai", "mock"] = "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    rag_top_k: int = 10

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}@{self.redis_host}:"
                f"{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
