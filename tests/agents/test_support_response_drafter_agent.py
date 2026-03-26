# tests/agents/test_support_response_drafter_agent.py
import pytest
import json
from src.agents.Support.support_response_drafter_agent import create_support_response_drafter_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_support_response_drafter_agent_with_context():
    llm = get_gemini_llm()
    agent = create_support_response_drafter_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Draft a response to a customer complaint.",
        orchestrator_plan="1. Analyze sentiment. 2. Draft response.",
        research_findings={"sentiment": "angry", "urgency": "high"},
        specific_instruction="Draft a response to the following customer complaint: 'My order arrived broken! This is unacceptable!'",
        pitfalls_to_avoid="Do not make promises you can't keep."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "unacceptable" in result["output"].lower() or "sorry" in result["output"].lower()
