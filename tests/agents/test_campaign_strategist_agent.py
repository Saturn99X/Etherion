# tests/agents/test_campaign_strategist_agent.py
import pytest
import json
from src.agents.Email.campaign_strategist_agent import create_campaign_strategist_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_campaign_strategist_agent_with_context():
    llm = get_gemini_llm()
    agent = create_campaign_strategist_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Create a welcome email series for new subscribers.",
        orchestrator_plan="1. Design the campaign sequence. 2. Draft each email.",
        research_findings={},
        specific_instruction="Design a 3-step welcome email sequence for new subscribers to our newsletter about sustainable living.",
        pitfalls_to_avoid="Do not be too salesy in the first email."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    output = json.loads(result["output"])
    assert "campaign_name" in output
    assert "sequence" in output
    assert len(output["sequence"]) == 3
