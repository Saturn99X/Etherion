# tests/agents/test_sentiment_analysis_agent.py
import pytest
import json
from src.agents.Support.sentiment_analysis_agent import create_sentiment_analysis_agent
from src.utils.llm_loader import get_gemini_llm
from src.utils.data_models import SpecialistAgentInput

@pytest.mark.asyncio
async def test_sentiment_analysis_agent_with_context():
    llm = get_gemini_llm()
    agent = create_sentiment_analysis_agent(llm)

    test_input = SpecialistAgentInput(
        original_user_goal="Analyze customer feedback.",
        orchestrator_plan="1. Analyze sentiment. 2. Draft response.",
        research_findings={},
        specific_instruction="Analyze the sentiment of the following text: 'Your product is amazing! I love it so much.'",
        pitfalls_to_avoid=""
    )
    
    result = await agent.ainvoke({"input": test_input.model_dump_json()})
    
    assert isinstance(result, dict)
    assert "output" in result
    output = json.loads(result["output"])
    assert "sentiment" in output
    assert "urgency" in output
    assert output["sentiment"] == "positive"
