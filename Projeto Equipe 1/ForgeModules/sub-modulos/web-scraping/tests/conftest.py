"""Fixtures de teste."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from config.settings import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        postgres_host="localhost",
        postgres_port=5432,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_host="localhost",
        redis_port=6379,
        llm_provider="mock",
        debug=True,
    )


@pytest.fixture
async def client(test_settings: Settings):
    app = create_app(test_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
