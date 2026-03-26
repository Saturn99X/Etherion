# tests/agents/test_content_generator_agent.py
import pytest
import json
from src.agents.BlogPost.content_generator_agent import create_content_generator_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_content_generator_agent_with_context():
    llm = get_gemini_llm()
    agent = create_content_generator_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Write a blog post about the future of AI in healthcare.",
        orchestrator_plan="1. Research AI in healthcare. 2. Generate content. 3. Optimize for SEO.",
        research_findings={"text_results": ["AI is revolutionizing diagnostics.", "Personalized treatment plans are now possible with AI."]},
        specific_instruction="Generate a comprehensive blog post about the future of AI in healthcare, covering diagnostics, personalized medicine, and drug discovery. Include a section on ethical considerations.",
        pitfalls_to_avoid="Avoid overly technical language and focus on the patient benefits."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "healthcare" in result["output"].lower()
    assert "ethical considerations" in result["output"].lower()