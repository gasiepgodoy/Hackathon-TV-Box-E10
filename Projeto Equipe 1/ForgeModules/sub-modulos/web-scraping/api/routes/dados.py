"""Rotas de consulta de dados acadêmicos."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_cache, get_db_session
from api.schemas import serialize_update
from database.repository import EventRepository
from shared.cache import CacheService

router = APIRouter(tags=["dados"])


@router.get("/dados-atuais")
async def get_dados_atuais(
    session: AsyncSession = Depends(get_db_session),
    cache: CacheService = Depends(get_cache),
) -> dict[str, Any]:
    """Retorna os dados mais recentes (cache Redis com fallback no banco)."""
    cached = await cache.get_current_data()
    if cached:
        return {"source": "cache", "data": cached}

    repo = EventRepository(session)
    latest = await repo.get_latest_update()
    if not latest:
        return {"source": "database", "data": None, "message": "Nenhum dado coletado ainda."}

    return {"source": "database", "data": serialize_update(latest)}


@router.get("/historico")
async def get_historico(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Histórico completo paginado de atualizações."""
    repo = EventRepository(session)
    records = await repo.get_history(limit=limit, offset=offset)
    total = await repo.count_records()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": [serialize_update(r) for r in records],
    }


@router.get("/ultimas-atualizacoes")
async def get_ultimas_atualizacoes(
    hours: int = Query(default=2, ge=1, le=48),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Atualizações das últimas N horas."""
    repo = EventRepository(session)
    records = await repo.get_recent_updates(hours=hours)

    return {
        "hours": hours,
        "count": len(records),
        "records": [serialize_update(r) for r in records],
    }
