# tests/agents/test_audience_agent.py
import pytest
import json
from src.agents.Copywriter.audience_agent import create_audience_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_audience_agent_with_context():
    llm = get_gemini_llm()
    agent = create_audience_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Develop a marketing campaign for a new brand of sustainable coffee.",
        orchestrator_plan="1. Define target audience. 2. Create brand voice. 3. Draft ad copy.",
        research_findings={"text_results": ["Sustainability is a key concern for millennial consumers.", "Coffee drinkers are active on Instagram."]},
        specific_instruction="Define the primary buyer persona for our new sustainable coffee brand.",
        pitfalls_to_avoid="Do not target price-sensitive consumers."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "Name:" in result["output"]
    assert "Demographics:" in result["output"]
    assert "Psychographics:" in result["output"]
