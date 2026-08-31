"""Ferramentas LangChain para consulta ao banco."""

from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from database.repository import EventRepository


def create_db_tools(session: AsyncSession) -> list[Any]:
    """Cria ferramentas vinculadas à sessão do banco."""

    @tool
    async def consultar_ultima_atualizacao() -> str:
        """Retorna a hora da última atualização de dados acadêmicos."""
        repo = EventRepository(session)
        latest = await repo.get_latest_update()
        if not latest:
            return "Ainda não há atualizações registradas."
        return f"Última atualização: {latest.recorded_at.isoformat()}"

    @tool
    async def consultar_aulas_maximas_hoje() -> str:
        """Retorna o maior número de aulas simultâneas registradas hoje."""
        repo = EventRepository(session)
        max_aulas = await repo.get_max_metric_today("temperature")
        if max_aulas is None:
            return "Nenhuma aula registrada hoje."
        return f"Maior número de aulas simultâneas hoje: {max_aulas} aulas"

    @tool
    async def consultar_dados_recentes(horas: int = 2) -> str:
        """Lista dados das últimas N horas (padrão: 2)."""
        repo = EventRepository(session)
        records = await repo.get_recent_updates(hours=horas)
        if not records:
            return f"Nenhum dado nas últimas {horas} hora(s)."
        lines = []
        for r in records[:20]:
            metrics = ", ".join(f"{m.metric_key}={m.metric_value} {m.unit}" for m in r.metrics)
            lines.append(f"{r.recorded_at.isoformat()}: {metrics}")
        return "\n".join(lines)

    return [consultar_ultima_atualizacao, consultar_aulas_maximas_hoje, consultar_dados_recentes]
