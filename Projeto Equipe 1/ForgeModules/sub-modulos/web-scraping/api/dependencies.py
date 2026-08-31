"""Dependências compartilhadas da API."""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from agent.chain import AcademicAgent
from database.connection import get_session
from shared.cache import CacheService


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


def get_cache(request: Request) -> CacheService:
    return request.app.state.cache


def get_agent(request: Request) -> AcademicAgent:
    return request.app.state.agent
