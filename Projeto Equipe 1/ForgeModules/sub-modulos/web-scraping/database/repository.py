"""Repositório de acesso aos dados acadêmicos."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import CollectorStatus, DataSource, EventMetric, EventUpdate, Location


class EventRepository:
    """Operações de leitura e escrita no banco."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_seed_data(
        self,
        source_name: str,
        source_type: str,
        base_url: str,
        location_name: str,
        latitude: float,
        longitude: float,
    ) -> tuple[DataSource, Location]:
        source = await self._get_or_create_source(source_name, source_type, base_url)
        location = await self._get_or_create_location(location_name, latitude, longitude)
        await self._ensure_collector_status()
        return source, location

    async def _get_or_create_source(
        self, name: str, source_type: str, base_url: str
    ) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == name))
        source = result.scalar_one_or_none()
        if source is None:
            source = DataSource(name=name, source_type=source_type, base_url=base_url)
            self.session.add(source)
            await self.session.commit()
            await self.session.refresh(source)
        return source

    async def _get_or_create_location(
        self, name: str, latitude: float, longitude: float
    ) -> Location:
        result = await self.session.execute(select(Location).where(Location.name == name))
        location = result.scalar_one_or_none()
        if location is None:
            location = Location(
                name=name,
                latitude=Decimal(str(latitude)),
                longitude=Decimal(str(longitude)),
            )
            self.session.add(location)
            await self.session.commit()
            await self.session.refresh(location)
        return location

    async def _ensure_collector_status(self) -> CollectorStatus:
        result = await self.session.execute(select(CollectorStatus).limit(1))
        status = result.scalar_one_or_none()
        if status is None:
            status = CollectorStatus(is_running=False, total_records=0)
            self.session.add(status)
            await self.session.commit()
            await self.session.refresh(status)
        return status

    async def save_update(
        self,
        source_id: int,
        location_id: int,
        recorded_at: datetime,
        metrics: dict[str, tuple[Decimal, str]],
        raw_payload: dict[str, Any],
    ) -> EventUpdate:
        update = EventUpdate(
            source_id=source_id,
            location_id=location_id,
            recorded_at=recorded_at,
            raw_payload=raw_payload,
        )
        self.session.add(update)
        await self.session.flush()

        for key, (value, unit) in metrics.items():
            self.session.add(
                EventMetric(
                    update_id=update.id,
                    metric_key=key,
                    metric_value=value,
                    unit=unit,
                )
            )

        status = await self._ensure_collector_status()
        status.last_success_at = datetime.now(timezone.utc)
        status.total_records = (status.total_records or 0) + 1
        status.is_running = True
        status.last_error_message = None

        await self.session.commit()
        await self.session.refresh(update)
        return update

    async def record_collector_error(self, message: str) -> None:
        status = await self._ensure_collector_status()
        status.last_error_at = datetime.now(timezone.utc)
        status.last_error_message = message
        status.is_running = True
        await self.session.commit()

    async def set_collector_running(self, running: bool) -> None:
        status = await self._ensure_collector_status()
        status.is_running = running
        await self.session.commit()

    async def get_collector_status(self) -> CollectorStatus:
        return await self._ensure_collector_status()

    async def count_records(self) -> int:
        result = await self.session.execute(select(func.count(EventUpdate.id)))
        return result.scalar_one()

    async def get_latest_update(self) -> EventUpdate | None:
        stmt = (
            select(EventUpdate)
            .options(selectinload(EventUpdate.metrics), selectinload(EventUpdate.location))
            .order_by(desc(EventUpdate.recorded_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history(self, limit: int = 100, offset: int = 0) -> list[EventUpdate]:
        stmt = (
            select(EventUpdate)
            .options(selectinload(EventUpdate.metrics), selectinload(EventUpdate.location))
            .order_by(desc(EventUpdate.recorded_at))
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_updates(self, hours: int = 2) -> list[EventUpdate]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(EventUpdate)
            .options(selectinload(EventUpdate.metrics))
            .where(EventUpdate.recorded_at >= since)
            .order_by(desc(EventUpdate.recorded_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_metrics_for_rag(self, limit: int = 50) -> list[dict[str, Any]]:
        stmt = (
            select(EventUpdate)
            .options(selectinload(EventUpdate.metrics), selectinload(EventUpdate.location))
            .order_by(desc(EventUpdate.recorded_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        documents: list[dict[str, Any]] = []
        for update in result.scalars().all():
            metrics = {m.metric_key: f"{m.metric_value} {m.unit}" for m in update.metrics}
            documents.append(
                {
                    "id": update.id,
                    "recorded_at": update.recorded_at.isoformat(),
                    "location": update.location.name if update.location else "N/A",
                    "metrics": metrics,
                    "text": self._format_update_text(update),
                }
            )
        return documents

    @staticmethod
    def _format_update_text(update: EventUpdate) -> str:
        parts = [f"Atualização em {update.recorded_at.isoformat()}"]
        if update.location:
            parts.append(f"Local: {update.location.name}")
        for metric in update.metrics:
            label = {
                "temperature": "Aulas Ativas",
                "wind_speed": "Eventos Acadêmicos",
                "humidity": "Notícias",
            }.get(metric.metric_key, metric.metric_key)
            parts.append(f"{label}: {metric.metric_value} {metric.unit}")
        return " | ".join(parts)

    async def get_max_metric_today(self, metric_key: str) -> Decimal | None:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.max(EventMetric.metric_value))
            .join(EventUpdate)
            .where(
                EventMetric.metric_key == metric_key,
                EventUpdate.recorded_at >= today_start,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
