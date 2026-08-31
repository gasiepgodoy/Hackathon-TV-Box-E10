"""Testes do agente acadêmico."""

import pytest

from agent.chain import AcademicAgent
from config.settings import Settings


@pytest.fixture
def agent() -> AcademicAgent:
    return AcademicAgent(Settings(llm_provider="mock"))


def test_agent_mock_provider(agent: AcademicAgent) -> None:
    assert agent._llm is None
    assert agent.settings.llm_provider == "mock"
