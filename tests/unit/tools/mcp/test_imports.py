# tests/unit/tools/mcp/test_imports.py
"""
Test that the new MCP tools can be imported correctly.
"""

def test_mcp_slack_import():
    """Test that the MCP Slack tool can be imported."""
    from src.tools.mcp.mcp_slack import MCPSlackTool
    assert MCPSlackTool is not None


def test_mcp_jira_import():
    """Test that the MCP Jira tool can be imported."""
    from src.tools.mcp.mcp_jira import MCPJiraTool
    assert MCPJiraTool is not None


def test_mcp_ms365_import():
    """Test that the MCP MS365 tool can be imported."""
    from src.tools.mcp.mcp_ms365 import MCPMS365Tool
    assert MCPMS365Tool is not None


def test_mcp_salesforce_import():
    """Test that the MCP Salesforce tool can be imported."""
    from src.tools.mcp.mcp_salesforce import MCPSalesforceTool
    assert MCPSalesforceTool is not None


def test_file_generation_tools_import():
    """Test that file generation tools can be imported."""
    import importlib

    m = importlib.import_module("src.tools.file_generation_tools")
    assert getattr(m, "generate_pdf_file", None) is not None