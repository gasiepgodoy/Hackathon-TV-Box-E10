"""Interface abstrata para fontes de dados acadêmicos.

Preparada para substituição por:
- APIs universitárias
- Web scraping com Playwright
- Portais autenticados baseados em HTML
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass
class CollectedEvent:
    """Evento acadêmico normalizado coletado de qualquer fonte."""

    recorded_at: datetime
    metrics: dict[str, tuple[Decimal, str]]
    raw_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class AcademicDataSource(ABC):
    """Contrato para implementações de coleta."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Nome identificador da fonte."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Tipo: api, scraper ou portal."""

    @abstractmethod
    async def fetch_current_events(
        self, latitude: float, longitude: float, location_name: str
    ) -> CollectedEvent:
        """Coleta eventos/dados atuais da fonte."""

    async def close(self) -> None:
        """Libera recursos (sessões HTTP, browsers, etc.)."""
