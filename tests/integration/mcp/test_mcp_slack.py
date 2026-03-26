# tests/integration/mcp/test_mcp_slack.py
"""
Integration tests for the MCP Slack tool.
"""

import pytest
from src.tools.mcp.mcp_slack import MCPSlackTool
from src.tools.mcp.base_mcp_tool import MCPToolResult


@pytest.mark.asyncio
async def test_mcp_slack_initialization():
    """Test that the MCP Slack tool can be initialized."""
    tool = MCPSlackTool()
    assert tool.name == "mcp_slack"
    assert tool.description == "Access Slack channel history and workspace information"


@pytest.mark.asyncio
async def test_mcp_slack_execute_missing_tenant_id():
    """Test that the MCP Slack tool handles missing tenant_id parameter."""
    tool = MCPSlackTool()
    params = {"action": "get_channels"}
    result = await tool.execute(params)
    assert isinstance(result, MCPToolResult)
    assert result.success == False
    assert result.error_code == "MISSING_FIELD"
    assert "tenant_id" in result.error_message


@pytest.mark.asyncio
async def test_mcp_slack_execute_missing_action():
    """Test that the MCP Slack tool handles missing action parameter."""
    tool = MCPSlackTool()
    params = {"tenant_id": "test-tenant"}
    result = await tool.execute(params)
    assert isinstance(result, MCPToolResult)
    assert result.success == False
    assert result.error_code == "MISSING_FIELD"
    assert "action" in result.error_message


# Note: The following tests would require mocking the secrets manager to provide test credentials
# Since we don't have credentials in the test environment, these tests will fail
# In a real implementation, we would mock the secrets manager to provide test credentials