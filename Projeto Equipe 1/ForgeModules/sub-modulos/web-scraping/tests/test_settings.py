"""Testes de configuração."""

from config.settings import Settings


def test_database_url() -> None:
    settings = Settings(
        postgres_user="user",
        postgres_password="pass",
        postgres_host="db",
        postgres_port=5432,
        postgres_db="academic",
    )
    assert "postgresql+asyncpg://user:pass@db:5432/academic" == settings.database_url


def test_redis_url_without_password() -> None:
    settings = Settings(redis_host="redis", redis_port=6379, redis_db=0)
    assert settings.redis_url == "redis://redis:6379/0"
