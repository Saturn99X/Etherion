# tests/agents/test_brand_voice_agent.py
import pytest
import json
from src.agents.Copywriter.brand_voice_agent import create_brand_voice_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_brand_voice_agent_with_context():
    llm = get_gemini_llm()
    agent = create_brand_voice_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Draft an ad copy for our new product.",
        orchestrator_plan="1. Define brand voice. 2. Draft ad copy.",
        research_findings={},
        specific_instruction="Analyze the following text for brand voice adherence: 'Our new product is totally awesome and you should buy it now!'",
        pitfalls_to_avoid="Avoid overly casual language."
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    assert "adheres" in result["output"].lower()
    assert "confidence score" in result["output"].lower()
