# tests/integration/mcp/test_mcp_jira.py
"""
Integration tests for the MCP Jira tool.
"""

import pytest
from src.tools.mcp.mcp_jira import MCPJiraTool
from src.tools.mcp.base_mcp_tool import MCPToolResult


@pytest.mark.asyncio
async def test_mcp_jira_initialization():
    """Test that the MCP Jira tool can be initialized."""
    tool = MCPJiraTool()
    assert tool.name == "mcp_jira"
    assert tool.description == "Access Jira sprint tickets and project information"


@pytest.mark.asyncio
async def test_mcp_jira_execute_missing_tenant_id():
    """Test that the MCP Jira tool handles missing tenant_id parameter."""
    tool = MCPJiraTool()
    params = {"action": "get_projects"}
    result = await tool.execute(params)
    assert isinstance(result, MCPToolResult)
    assert result.success == False
    assert result.error_code == "MISSING_FIELD"
    assert "tenant_id" in result.error_message


@pytest.mark.asyncio
async def test_mcp_jira_execute_missing_action():
    """Test that the MCP Jira tool handles missing action parameter."""
    tool = MCPJiraTool()
    params = {"tenant_id": "test-tenant"}
    result = await tool.execute(params)
    assert isinstance(result, MCPToolResult)
    assert result.success == False
    assert result.error_code == "MISSING_FIELD"
    assert "action" in result.error_message


# Note: The following tests would require mocking the secrets manager to provide test credentials
# Since we don't have credentials in the test environment, these tests will fail
# In a real implementation, we would mock the secrets manager to provide test credentials