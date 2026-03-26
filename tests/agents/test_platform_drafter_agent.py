# tests/agents/test_platform_drafter_agent.py
import pytest
import json
from src.agents.SocialMedia.platform_drafter_agent import create_platform_drafter_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_platform_drafter_agent_with_context():
    llm = get_gemini_llm()
    agent = create_platform_drafter_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Draft a tweet about our new product.",
        orchestrator_plan="1. Draft tweet.",
        research_findings={},
        specific_instruction="Draft a tweet announcing our new eco-friendly water bottle. Mention it's made from recycled materials.",
        pitfalls_to_avoid="Do not exceed the character limit."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "bottle" in result["output"].lower()
    assert "recycled" in result["output"].lower()
