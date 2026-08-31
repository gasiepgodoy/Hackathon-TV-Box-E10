"""Serialização de respostas da API."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from database.models import EventUpdate


def serialize_update(update: EventUpdate) -> dict[str, Any]:
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
        "raw_payload": update.raw_payload,
    }


def metric_display_name(key: str) -> str:
    return {
        "temperature": "Aulas Ativas",
        "wind_speed": "Eventos Acadêmicos",
        "humidity": "Notícias",
    }.get(key, key)
