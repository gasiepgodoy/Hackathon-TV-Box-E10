"""Agendador assíncrono de coleta a cada 30 segundos."""

import asyncio
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from collector.base import AcademicDataSource
from config.settings import Settings
from database.repository import EventRepository
from shared.cache import CacheService
from shared.logging_config import get_logger

logger = get_logger(__name__)


class CollectorScheduler:
    """Executa coleta periódica com tratamento de falhas."""

    def __init__(
        self,
        settings: Settings,
        data_source: AcademicDataSource,
        session_factory: async_sessionmaker[AsyncSession],
        cache: CacheService,
        on_update: Callable[[], None] | None = None,
    ) -> None:
        self.settings = settings
        self.data_source = data_source
        self.session_factory = session_factory
        self.cache = cache
        self.on_update = on_update
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "coletor_iniciado",
            intervalo=self.settings.collector_interval_seconds,
            fonte=self.data_source.source_name,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        async with self.session_factory() as session:
            repo = EventRepository(session)
            await repo.set_collector_running(False)

        await self.data_source.close()
        logger.info("coletor_parado")

    async def collect_once(self) -> bool:
        """Executa uma coleta imediata. Retorna True se bem-sucedida."""
        async with self.session_factory() as session:
            repo = EventRepository(session)
            source, location = await repo.ensure_seed_data(
                source_name=self.settings.data_source_name,
                source_type=self.settings.data_source_type,
                base_url=self.settings.data_source_base_url,
                location_name=self.settings.collector_location_name,
                latitude=self.settings.collector_latitude,
                longitude=self.settings.collector_longitude,
            )

            try:
                event = await self.data_source.fetch_current_events(
                    latitude=self.settings.collector_latitude,
                    longitude=self.settings.collector_longitude,
                    location_name=self.settings.collector_location_name,
                )
                update = await repo.save_update(
                    source_id=source.id,
                    location_id=location.id,
                    recorded_at=event.recorded_at,
                    metrics=event.metrics,
                    raw_payload=event.raw_payload,
                )
                await self.cache.invalidate_and_refresh(session)
                logger.info("registro_salvo", update_id=update.id)
                if self.on_update:
                    self.on_update()
                return True
            except (ConnectionError, TimeoutError, OSError) as exc:
                await repo.record_collector_error(str(exc))
                logger.error("erro_coleta", erro=str(exc))
                return False
            except Exception as exc:
                await repo.record_collector_error(str(exc))
                logger.exception("erro_inesperado_coleta", erro=str(exc))
                return False

    async def _run_loop(self) -> None:
        async with self.session_factory() as session:
            repo = EventRepository(session)
            await repo.set_collector_running(True)

        while self._running:
            await self.collect_once()
            try:
                await asyncio.sleep(self.settings.collector_interval_seconds)
            except asyncio.CancelledError:
                break
