# tests/agents/test_seo_optimizer_agent.py
import pytest
import json
from src.agents.BlogPost.seo_optimizer_agent import create_seo_optimizer_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_seo_optimizer_agent_with_context():
    llm = get_gemini_llm()
    agent = create_seo_optimizer_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Optimize a blog post for SEO.",
        orchestrator_plan="1. Generate SEO metadata. 2. Suggest internal links.",
        research_findings={"text_results": ["SEO is important for visibility."]},
        specific_instruction="Optimize the following blog post draft for SEO: 'This is a draft blog post about the benefits of meditation. It covers stress reduction, improved focus, and emotional well-being.'",
        pitfalls_to_avoid="Do not use clickbait titles."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    output = json.loads(result["output"])
    assert "seoMetadata" in output
    assert "linkSuggestions" in output
    assert "seoTitle" in output["seoMetadata"]