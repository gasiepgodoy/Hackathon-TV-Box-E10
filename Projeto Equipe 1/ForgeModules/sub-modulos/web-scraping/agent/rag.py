"""Retriever RAG sobre dados PostgreSQL."""

import re
from typing import Any

from langchain_core.documents import Document
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from database.repository import EventRepository


class RAGRetriever:
    """Recupera documentos relevantes do histórico acadêmico."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def retrieve(self, session: AsyncSession, query: str) -> list[Document]:
        repo = EventRepository(session)
        records = await repo.get_metrics_for_rag(limit=self.settings.rag_top_k * 3)

        if not records:
            return []

        query_lower = query.lower()
        hours_match = re.search(r"(\d+)\s*hora", query_lower)
        if hours_match:
            hours = int(hours_match.group(1))
            recent = await repo.get_recent_updates(hours=hours)
            if recent:
                records = [
                    {
                        "id": u.id,
                        "recorded_at": u.recorded_at.isoformat(),
                        "location": u.location.name if u.location else "N/A",
                        "metrics": {
                            m.metric_key: f"{m.metric_value}{m.unit}" for m in u.metrics
                        },
                        "text": repo._format_update_text(u),
                    }
                    for u in recent
                ]

        scored = [(self._score(doc, query_lower), doc) for doc in records]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [doc for score, doc in scored[: self.settings.rag_top_k] if score > 0]

        if not top and records:
            top = records[: self.settings.rag_top_k]

        return [
            Document(
                page_content=doc["text"],
                metadata={"id": doc["id"], "recorded_at": doc["recorded_at"]},
            )
            for doc in top
        ]

    @staticmethod
    def _score(doc: dict[str, Any], query: str) -> float:
        text = doc["text"].lower()
        score = 0.0
        keywords = [
            "temperatura",
            "vento",
            "umidade",
            "atualização",
            "atualizacao",
            "última",
            "ultima",
            "hoje",
            "hora",
            "dados",
            "máxima",
            "maxima",
            "alta",
        ]
        for kw in keywords:
            if kw in query:
                if kw in text or kw in str(doc.get("metrics", {})).lower():
                    score += 1.0
        for word in query.split():
            if len(word) > 3 and word in text:
                score += 0.5
        return score

    async def build_context(self, session: AsyncSession, query: str) -> tuple[str, list[str]]:
        docs = await self.retrieve(session, query)
        if not docs:
            return "Nenhum dado histórico disponível no banco.", []

        context_lines = [f"- {doc.page_content}" for doc in docs]
        fontes = [doc.metadata.get("recorded_at", "") for doc in docs]
        return "\n".join(context_lines), fontes
