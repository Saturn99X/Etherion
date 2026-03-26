# tests/agents/test_engagement_optimizer_agent.py
import pytest
import json
from src.agents.SocialMedia.engagement_optimizer_agent import create_engagement_optimizer_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_engagement_optimizer_agent_with_context():
    llm = get_gemini_llm()
    agent = create_engagement_optimizer_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Create an engaging Instagram post.",
        orchestrator_plan="1. Draft post. 2. Optimize for engagement.",
        research_findings={},
        specific_instruction="Optimize the following post for engagement: 'Check out our new product!'",
        pitfalls_to_avoid=""
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    output = json.loads(result["output"])
    assert "post_text" in output
    assert "suggested_hashtags" in output
    assert "suggested_emojis" in output
