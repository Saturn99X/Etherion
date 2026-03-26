# tests/agents/test_angle_ideation_agent.py
import pytest
import json
from src.agents.SocialMedia.angle_ideation_agent import create_angle_ideation_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_angle_ideation_agent_with_context():
    llm = get_gemini_llm()
    agent = create_angle_ideation_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Promote our new line of sunglasses on Instagram.",
        orchestrator_plan="1. Brainstorm angles. 2. Draft posts.",
        research_findings={"text_results": ["Retro styles are trending.", "Consumers want UV protection."]},
        specific_instruction="Brainstorm 3 creative angles for an Instagram post about our new sunglasses.",
        pitfalls_to_avoid="Avoid generic lifestyle shots."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "angle" in result["output"].lower()
