# tests/agents/test_email_body_drafter_agent.py
import pytest
import json
from src.agents.Email.email_body_drafter_agent import create_email_body_drafter_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_email_body_drafter_agent_with_context():
    llm = get_gemini_llm()
    agent = create_email_body_drafter_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Draft a welcome email for new subscribers.",
        orchestrator_plan="1. Draft welcome email.",
        research_findings={},
        specific_instruction="Draft the body of a welcome email for new subscribers to our 'Tech Weekly' newsletter. The email should be friendly and briefly explain what to expect from the newsletter.",
        pitfalls_to_avoid="Do not include any promotional material."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "welcome" in result["output"].lower()
    assert "tech weekly" in result["output"].lower()
