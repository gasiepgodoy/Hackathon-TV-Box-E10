"""Serviço de coleta de dados acadêmicos."""

from collector.base import AcademicDataSource, CollectedEvent
from collector.open_meteo import OpenMeteoSource
from collector.scheduler import CollectorScheduler

__all__ = ["AcademicDataSource", "CollectedEvent", "OpenMeteoSource", "CollectorScheduler"]
