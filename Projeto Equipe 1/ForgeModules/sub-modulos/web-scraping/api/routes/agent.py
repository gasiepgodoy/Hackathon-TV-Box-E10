"""Rotas do agente de IA."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agent.chain import AcademicAgent
from api.dependencies import get_agent, get_db_session

router = APIRouter(prefix="/agente", tags=["agente"])


class PerguntaRequest(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=1000)


class PerguntaResponse(BaseModel):
    pergunta: str
    resposta: str
    fontes: list[str] = Field(default_factory=list)
    provider: str


@router.post("/perguntar", response_model=PerguntaResponse)
async def perguntar(
    body: PerguntaRequest,
    session: AsyncSession = Depends(get_db_session),
    agent: AcademicAgent = Depends(get_agent),
) -> dict[str, Any]:
    """Responde perguntas em linguagem natural usando RAG + LangChain."""
    result = await agent.ask(session, body.pergunta)
    return result
