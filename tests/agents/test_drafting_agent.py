# tests/agents/test_drafting_agent.py
import pytest
import json
from src.agents.Copywriter.drafting_agent import create_drafting_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_drafting_agent_with_context():
    llm = get_gemini_llm()
    agent = create_drafting_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Write a blog post about the future of AI.",
        orchestrator_plan="1. Research AI trends. 2. Draft blog post. 3. Refine draft.",
        research_findings={"text_results": ["AI is growing fast.", "AI will change many industries."]},
        specific_instruction="Draft a 500-word blog post about the future of AI, focusing on its impact on daily life.",
        pitfalls_to_avoid="Avoid technical jargon."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert len(result["output"]) > 100
