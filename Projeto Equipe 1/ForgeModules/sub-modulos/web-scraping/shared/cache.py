"""Cliente Redis para cache de dados."""

import json
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from database.repository import EventRepository


class CacheService:
    """Cache Redis para dados atuais e status."""

    KEY_CURRENT = "academic:current_data"
    KEY_STATUS = "academic:status"
    KEY_RECORD_COUNT = "academic:record_count"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            self.settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    async def invalidate_and_refresh(self, session: AsyncSession) -> None:
        repo = EventRepository(session)
        latest = await repo.get_latest_update()
        status = await repo.get_collector_status()
        count = await repo.count_records()

        if self._client is None:
            return

        ttl = self.settings.cache_ttl_seconds

        if latest:
            data = self._serialize_update(latest)
            await self._client.setex(self.KEY_CURRENT, ttl, json.dumps(data, default=str))

        status_data = {
            "is_running": status.is_running,
            "last_success_at": status.last_success_at.isoformat() if status.last_success_at else None,
            "last_error_at": status.last_error_at.isoformat() if status.last_error_at else None,
            "last_error_message": status.last_error_message,
            "total_records": status.total_records,
            "updated_at": status.updated_at.isoformat() if status.updated_at else None,
        }
        await self._client.setex(self.KEY_STATUS, ttl, json.dumps(status_data, default=str))
        await self._client.setex(self.KEY_RECORD_COUNT, ttl, str(count))

    async def get_current_data(self) -> dict[str, Any] | None:
        if not self._client:
            return None
        raw = await self._client.get(self.KEY_CURRENT)
        return json.loads(raw) if raw else None

    async def get_status(self) -> dict[str, Any] | None:
        if not self._client:
            return None
        raw = await self._client.get(self.KEY_STATUS)
        return json.loads(raw) if raw else None

    async def get_record_count(self) -> int | None:
        if not self._client:
            return None
        raw = await self._client.get(self.KEY_RECORD_COUNT)
        return int(raw) if raw else None

    @staticmethod
    def _serialize_update(update: Any) -> dict[str, Any]:
        metrics = {
            m.metric_key: {"value": float(m.metric_value), "unit": m.unit}
            for m in update.metrics
        }
        return {
            "id": update.id,
            "recorded_at": update.recorded_at.isoformat(),
            "collected_at": update.collected_at.isoformat(),
            "location": update.location.name if update.location else None,
            "metrics": metrics,
        }
