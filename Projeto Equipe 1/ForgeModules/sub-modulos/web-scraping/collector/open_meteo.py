"""Implementação Open-Meteo — simula horários e eventos acadêmicos."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import aiohttp

from collector.base import AcademicDataSource, CollectedEvent
from shared.logging_config import get_logger

logger = get_logger(__name__)

METRIC_LABELS = {
    "temperature": ("Temperatura ambiente (simulada)", "°C"),
    "wind_speed": ("Velocidade do vento (simulada)", "km/h"),
    "humidity": ("Umidade relativa (simulada)", "%"),
}


class OpenMeteoSource(AcademicDataSource):
    """Fonte via API pública Open-Meteo."""

    def __init__(self, base_url: str, source_name: str, timeout: int = 15) -> None:
        self._base_url = base_url.rstrip("/")
        self._source_name = source_name
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def source_type(self) -> str:
        return "api"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def fetch_current_events(
        self, latitude: float, longitude: float, location_name: str
    ) -> CollectedEvent:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            "timezone": "America/Sao_Paulo",
        }
        url = f"{self._base_url}/forecast"
        session = await self._get_session()

        logger.info("coletando_dados", url=url, latitude=latitude, longitude=longitude)

        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                payload: dict[str, Any] = await response.json()
        except aiohttp.ClientError as exc:
            logger.error("falha_conexao_open_meteo", erro=str(exc), url=url)
            raise ConnectionError(f"Falha ao conectar com Open-Meteo: {exc}") from exc

        current = payload.get("current", {})
        recorded_at = self._parse_time(current.get("time"))

        metrics = {
            "temperature": (
                Decimal(str(current.get("temperature_2m", 0))),
                METRIC_LABELS["temperature"][1],
            ),
            "wind_speed": (
                Decimal(str(current.get("wind_speed_10m", 0))),
                METRIC_LABELS["wind_speed"][1],
            ),
            "humidity": (
                Decimal(str(current.get("relative_humidity_2m", 0))),
                METRIC_LABELS["humidity"][1],
            ),
        }

        logger.info(
            "dados_coletados",
            location=location_name,
            recorded_at=recorded_at.isoformat(),
            temperature=str(metrics["temperature"][0]),
            wind_speed=str(metrics["wind_speed"][0]),
            humidity=str(metrics["humidity"][0]),
        )

        return CollectedEvent(
            recorded_at=recorded_at,
            metrics=metrics,
            raw_payload=payload,
            metadata={"location_name": location_name, "source": "open_meteo"},
        )

    @staticmethod
    def _parse_time(time_str: str | None) -> datetime:
        if not time_str:
            return datetime.now(timezone.utc)
        try:
            dt = datetime.fromisoformat(time_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return datetime.now(timezone.utc)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
