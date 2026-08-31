"""Rotas de status do sistema."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_cache, get_db_session
from api.schemas import serialize_update
from config.settings import get_settings
from database.repository import EventRepository
from shared.cache import CacheService

router = APIRouter(tags=["status"])


@router.get("/status")
async def get_status(
    session: AsyncSession = Depends(get_db_session),
    cache: CacheService = Depends(get_cache),
) -> dict[str, Any]:
    """Status do coletor, cache e aplicação."""
    settings = get_settings()
    repo = EventRepository(session)

    cached_status = await cache.get_status()
    collector = await repo.get_collector_status()
    record_count = await cache.get_record_count()
    if record_count is None:
        record_count = await repo.count_records()

    latest = await repo.get_latest_update()

    return {
        "app": {
            "name": settings.app_name,
            "version": settings.app_version,
        },
        "collector": cached_status
        or {
            "is_running": collector.is_running,
            "last_success_at": collector.last_success_at.isoformat()
            if collector.last_success_at
            else None,
            "last_error_at": collector.last_error_at.isoformat()
            if collector.last_error_at
            else None,
            "last_error_message": collector.last_error_message,
            "total_records": collector.total_records,
        },
        "database": {
            "total_records": record_count,
            "last_update": serialize_update(latest) if latest else None,
        },
        "cache": {
            "enabled": cached_status is not None,
        },
    }
