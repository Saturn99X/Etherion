# tests/agents/test_research_agent.py
import pytest
import json
from src.agents.Copywriter.research_agent import create_research_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_research_agent_with_context():
    llm = get_gemini_llm()
    agent = create_research_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Understand the current state of quantum computing.",
        orchestrator_plan="1. Summarize research on quantum computing.",
        research_findings={"text_results": ["Quantum computers use qubits.", "They can solve certain problems much faster than classical computers.", "Major players include Google, IBM, and Rigetti."]},
        specific_instruction="Provide a brief, high-level summary of the key points from the research findings.",
        pitfalls_to_avoid="Do not get into the physics details."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "quantum" in result["output"].lower()
    assert "qubits" in result["output"].lower()
