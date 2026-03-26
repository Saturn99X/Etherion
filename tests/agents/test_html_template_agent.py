# tests/agents/test_html_template_agent.py
import pytest
import json
from src.agents.Email.html_template_agent import create_html_template_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_html_template_agent_with_context():
    llm = get_gemini_llm()
    agent = create_html_template_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Send a welcome email.",
        orchestrator_plan="1. Draft email. 2. Wrap in HTML.",
        research_findings={},
        specific_instruction="Wrap the following email in the 'basic_template.html': Subject: Welcome!, Body: Welcome to our newsletter.",
        pitfalls_to_avoid=""
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "<html>" in result["output"].lower()
    assert "welcome!" in result["output"].lower()
