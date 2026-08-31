"""Ponto de entrada do serviço coletor."""

import asyncio
import signal

from collector.university_api import UniversityApiSource
from collector.scheduler import CollectorScheduler
from config.settings import get_settings
from database.connection import close_db, get_engine, init_db
from shared.cache import CacheService
from shared.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    await init_db()
    _, session_factory = get_engine()
    assert session_factory is not None

    cache = CacheService(settings)
    await cache.connect()

    data_source = UniversityApiSource(
        base_url=settings.data_source_base_url,
    )

    scheduler = CollectorScheduler(
        settings=settings,
        data_source=data_source,
        session_factory=session_factory,
        cache=cache,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("sinal_parada_recebido")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await scheduler.start()

    logger.info("coletor_em_execucao", intervalo=settings.collector_interval_seconds)
    await stop_event.wait()

    await scheduler.stop()
    await cache.close()
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
