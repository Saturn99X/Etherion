# tests/agents/test_ideation_agent.py
import pytest
import json
from src.agents.Copywriter.ideation_agent import create_ideation_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_ideation_agent_with_context():
    llm = get_gemini_llm()
    agent = create_ideation_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Launch a new line of eco-friendly sneakers.",
        orchestrator_plan="1. Brainstorm campaign concepts. 2. Draft ad copy for each concept.",
        research_findings={"text_results": ["Consumers are looking for stylish and sustainable footwear."]},
        specific_instruction="Brainstorm 3-5 creative concepts for a social media campaign for our new eco-friendly sneakers.",
        pitfalls_to_avoid="Avoid greenwashing cliches."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "Concept Name:" in result["output"]
    assert "Core Idea/Angle:" in result["output"]
    assert "Example Headline(s):" in result["output"]
