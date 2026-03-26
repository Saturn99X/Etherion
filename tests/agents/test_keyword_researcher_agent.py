# tests/agents/test_keyword_researcher_agent.py
import pytest
import json
from src.agents.BlogPost.keyword_researcher_agent import create_keyword_researcher_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_keyword_researcher_agent_with_context():
    llm = get_gemini_llm()
    agent = create_keyword_researcher_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Write a blog post about sustainable fashion.",
        orchestrator_plan="1. Research keywords. 2. Generate content.",
        research_findings={"text_results": ["Consumers are interested in eco-friendly materials and ethical production."]},
        specific_instruction="Research relevant SEO keywords for a blog post about sustainable fashion.",
        pitfalls_to_avoid="Avoid keywords that are too broad."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "sustainable fashion" in result["output"].lower()
    assert "primary" in result["output"].lower()