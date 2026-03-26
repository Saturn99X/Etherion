# tests/agents/test_subject_line_specialist_agent.py
import pytest
import json
from src.agents.Email.subject_line_specialist_agent import create_subject_line_specialist_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_subject_line_specialist_agent_with_context():
    llm = get_gemini_llm()
    agent = create_subject_line_specialist_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Generate subject lines for a welcome email.",
        orchestrator_plan="1. Generate subject lines.",
        research_findings={},
        specific_instruction="Generate subject lines and preview text for the following email body: 'Welcome to our newsletter! We're excited to have you on board.'",
        pitfalls_to_avoid="Avoid using all caps."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    output = json.loads(result["output"])
    assert "subject_lines" in output
    assert "preview_text" in output
    assert len(output["subject_lines"]) >= 3
