# tests/unit/tools/mcp/test_base_mcp_tool.py
"""
Unit tests for the base MCP tool.
"""

import pytest
from src.tools.mcp.base_mcp_tool import BaseMCPTool, MCPToolResult, MCPToolError, InvalidCredentialsError, RateLimitError


class ConcreteMCPTool(BaseMCPTool):
    """Concrete implementation of BaseMCPTool for testing."""
    
    async def execute(self, params):
        """Execute the tool with given parameters."""
        return MCPToolResult(success=True, data={"test": "data"})


class TestBaseMCPTool:
    """Test the BaseMCPTool class."""

    def test_initialization(self):
        """Test that the base MCP tool can be initialized."""
        tool = ConcreteMCPTool("test_tool", "A test tool")
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"

    def test_mcp_tool_result_initialization(self):
        """Test that the MCPToolResult can be initialized."""
        result = MCPToolResult(success=True, data={"key": "value"}, error_message=None, error_code=None)
        assert result.success == True
        assert result.data == {"key": "value"}
        assert result.error_message == None
        assert result.error_code == None

    def test_mcp_tool_exceptions(self):
        """Test that the MCP tool exceptions can be raised."""
        # Test base exception
        with pytest.raises(MCPToolError):
            raise MCPToolError("Test error")

        # Test invalid credentials exception
        with pytest.raises(InvalidCredentialsError):
            raise InvalidCredentialsError("Invalid credentials")

        # Test rate limit exception
        with pytest.raises(RateLimitError):
            raise RateLimitError("Rate limit exceeded")