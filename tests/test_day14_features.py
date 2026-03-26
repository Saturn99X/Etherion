import pytest
from src.tools.mcp.mcp_shopify import MCPShopifyTool
from src.tools.save_to_gcs_tool import SaveToGCSTool
from src.tools.mcp.base_mcp_tool import MCPToolResult


def test_mcp_shopify_tool_initialization():
    """Test that MCPShopifyTool initializes correctly."""
    tool = MCPShopifyTool()
    assert tool.name == "mcp_shopify"
    assert tool.description == "Manage Shopify store including abandoned cart recovery, customer data retrieval, and discount code creation"


def test_save_to_gcs_tool_initialization():
    """Test that SaveToGCSTool initializes correctly."""
    tool = SaveToGCSTool()
    assert tool.name == "save_to_gcs"
    assert tool.description == "Save documents to tenant-specific Google Cloud Storage buckets"


if __name__ == "__main__":
    pytest.main([__file__])