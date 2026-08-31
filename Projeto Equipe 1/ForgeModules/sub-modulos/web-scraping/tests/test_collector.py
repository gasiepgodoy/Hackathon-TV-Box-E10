"""Testes do coletor Open-Meteo."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from collector.open_meteo import OpenMeteoSource


@pytest.fixture
def source() -> OpenMeteoSource:
    return OpenMeteoSource(
        base_url="https://api.open-meteo.com/v1",
        source_name="Test Source",
    )


@pytest.mark.asyncio
async def test_fetch_current_events_success(source: OpenMeteoSource) -> None:
    mock_response = {
        "current": {
            "time": "2025-06-25T14:00",
            "temperature_2m": 22.5,
            "relative_humidity_2m": 65,
            "wind_speed_10m": 12.3,
        }
    }

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=mock_response)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.closed = False

    with patch.object(source, "_get_session", AsyncMock(return_value=mock_session)):
        event = await source.fetch_current_events(-23.55, -46.63, "Campus")

    assert event.metrics["temperature"] == (Decimal("22.5"), "°C")
    assert event.metrics["wind_speed"] == (Decimal("12.3"), "km/h")
    assert event.metrics["humidity"] == (Decimal("65"), "%")
    assert isinstance(event.recorded_at, datetime)


@pytest.mark.asyncio
async def test_fetch_connection_error(source: OpenMeteoSource) -> None:
    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=aiohttp.ClientError("timeout"))
    mock_session.closed = False

    with patch.object(source, "_get_session", AsyncMock(return_value=mock_session)):
        with pytest.raises(ConnectionError):
            await source.fetch_current_events(-23.55, -46.63, "Campus")


def test_parse_time_fallback(source: OpenMeteoSource) -> None:
    result = source._parse_time(None)
    assert result.tzinfo is not None
