# tests/integration/test_workers_spy_agent.py
"""
Integration tests for the Workers-Spy agent.
"""

import pytest
from src.agents.WorkersSpy.workers_spy_agent import create_workers_spy_agent
from src.utils.llm_loader import get_gemini_llm


@pytest.mark.asyncio
async def test_workers_spy_agent_creation():
    """Test that the Workers-Spy agent can be created."""
    llm_flash = get_gemini_llm(model_tier='flash')
    agent = create_workers_spy_agent(llm_flash)
    assert agent is not None
    assert hasattr(agent, 'ainvoke')


@pytest.mark.asyncio
async def test_workers_spy_agent_has_required_tools():
    """Test that the Workers-Spy agent has the required tools."""
    llm_flash = get_gemini_llm(model_tier='flash')
    agent = create_workers_spy_agent(llm_flash)
    
    # Get the tools from the agent
    tools = agent.tools
    
    # Check that the agent has the required tools
    tool_names = [tool.name for tool in tools]
    assert "mcp_slack" in tool_names
    assert "mcp_jira" in tool_names
    assert "confirm_action" in tool_names