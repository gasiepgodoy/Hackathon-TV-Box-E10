"""Stub para futura integração com portais universitários via Playwright."""

from collector.base import AcademicDataSource, CollectedEvent


class UniversityPortalScraper(AcademicDataSource):
    """Placeholder para scraping de portais acadêmicos autenticados.

    Para implementar:
    1. Instalar playwright: pip install playwright && playwright install
    2. Implementar login e navegação no portal alvo
    3. Mapear HTML para CollectedEvent
    4. Registrar em collector/main.py como fonte alternativa
    """

    def __init__(self, portal_url: str, username: str, password: str) -> None:
        self._portal_url = portal_url
        self._username = username
        self._password = password

    @property
    def source_name(self) -> str:
        return "Portal Universitário"

    @property
    def source_type(self) -> str:
        return "portal"

    async def fetch_current_events(
        self, latitude: float, longitude: float, location_name: str
    ) -> CollectedEvent:
        raise NotImplementedError(
            "Implemente o scraper do portal universitário substituindo OpenMeteoSource."
        )
