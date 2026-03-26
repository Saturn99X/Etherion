# tests/agents/test_refinement_agent.py
import pytest
import json
from src.agents.Copywriter.refinement_agent import create_refinement_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_refinement_agent_with_context():
    llm = get_gemini_llm()
    agent = create_refinement_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Create a blog post about the benefits of meditation.",
        orchestrator_plan="1. Research meditation benefits. 2. Draft blog post. 3. Refine draft.",
        research_findings={"text_results": ["Meditation reduces stress.", "Meditation improves focus."]},
        specific_instruction="Refine the following draft to be more engaging and less robotic: 'Meditation is good. It helps you relax. You should do it.'",
        pitfalls_to_avoid="Do not make it too spiritual. Keep it secular."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert len(result["output"]) > len("Meditation is good. It helps you relax. You should do it.")
