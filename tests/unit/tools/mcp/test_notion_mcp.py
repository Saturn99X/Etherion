"""
Unit tests for Notion MCP Tool.

This module provides comprehensive test coverage for the Notion MCP tool
with VCR.py compatibility for integration testing.

Author: Etherion AI Platform Team
Date: 2025-01-15
Version: 3.0.0
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from src.tools.mcp.mcp_notion import MCPNotionTool, NotionCredentials
from src.tools.mcp.base_mcp_tool import (
    InvalidCredentialsError,
    RateLimitError,
    ValidationError,
    MCPToolResult,
)


class TestNotionCredentials:
    """Test NotionCredentials class."""

    def test_credentials_creation(self):
        """Test credential creation."""
        creds = NotionCredentials(
            access_token="test_token",
            refresh_token="refresh_token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
            workspace_id="workspace_123",
            bot_id="bot_456",
        )
        
        assert creds.access_token == "test_token"
        assert creds.refresh_token == "refresh_token"
        assert creds.workspace_id == "workspace_123"
        assert creds.bot_id == "bot_456"

    def test_needs_refresh(self):
        """Test token refresh detection."""
        # Token expires in 1 hour - should not need refresh
        creds = NotionCredentials(
            access_token="test_token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert not creds.needs_refresh()

        # Token expires in 2 minutes - should need refresh
        creds = NotionCredentials(
            access_token="test_token",
            expires_at=datetime.utcnow() + timedelta(minutes=2),
        )
        assert creds.needs_refresh()

        # No expiry time - should not need refresh
        creds = NotionCredentials(access_token="test_token")
        assert not creds.needs_refresh()

    def test_to_dict(self):
        """Test credential serialization."""
        creds = NotionCredentials(
            access_token="test_token",
            refresh_token="refresh_token",
            expires_at=datetime(2025, 1, 15, 12, 0, 0),
            workspace_id="workspace_123",
        )
        
        data = creds.to_dict()
        assert data["access_token"] == "test_token"
        assert data["refresh_token"] == "refresh_token"
        assert data["workspace_id"] == "workspace_123"
        assert data["expires_at"] == "2025-01-15T12:00:00"

    def test_from_dict(self):
        """Test credential deserialization."""
        data = {
            "access_token": "test_token",
            "refresh_token": "refresh_token",
            "expires_at": "2025-01-15T12:00:00",
            "workspace_id": "workspace_123",
            "bot_id": "bot_456",
        }
        
        creds = NotionCredentials.from_dict(data)
        assert creds.access_token == "test_token"
        assert creds.refresh_token == "refresh_token"
        assert creds.workspace_id == "workspace_123"
        assert creds.bot_id == "bot_456"


class TestMCPNotionTool:
    """Test MCPNotionTool class."""

    @pytest.fixture
    def tool(self):
        """Create tool instance for testing."""
        return MCPNotionTool()

    @pytest.fixture
    def mock_credentials(self):
        """Create mock credentials."""
        return NotionCredentials(
            access_token="test_token",
            refresh_token="refresh_token",
            expires_at=datetime.utcnow() + timedelta(hours=1),
            workspace_id="workspace_123",
            bot_id="bot_456",
            client_id="client_123",
            client_secret="secret_456",
        )

    @pytest.fixture
    def mock_client(self):
        """Create mock Notion client."""
        client = AsyncMock()
        client.databases = AsyncMock()
        client.pages = AsyncMock()
        client.blocks = AsyncMock()
        client.users = AsyncMock()
        client.search = AsyncMock()
        client.comments = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_notion_client_new(self, tool, mock_credentials):
        """Test getting new Notion client."""
        with patch.object(tool.secrets_manager, 'get_secret', return_value=mock_credentials.to_dict()):
            with patch('notion_client.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                client = await tool._get_notion_client("tenant_123")
                
                assert client == mock_client
                mock_client_class.assert_called_once_with(
                    auth="test_token",
                    notion_version="2022-06-28"
                )

    @pytest.mark.asyncio
    async def test_get_notion_client_cached(self, tool, mock_client):
        """Test getting cached Notion client."""
        tool._clients["tenant_123"] = mock_client
        
        client = await tool._get_notion_client("tenant_123")
        assert client == mock_client

    @pytest.mark.asyncio
    async def test_get_notion_client_missing_credentials(self, tool):
        """Test error when credentials are missing."""
        with patch.object(tool.secrets_manager, 'get_secret', return_value=None):
            with pytest.raises(InvalidCredentialsError):
                await tool._get_notion_client("tenant_123")

    @pytest.mark.asyncio
    async def test_refresh_notion_token(self, tool, mock_credentials):
        """Test token refresh."""
        with patch.object(tool, '_get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "access_token": "new_token",
                "refresh_token": "new_refresh_token",
                "expires_in": 3600
            })
            mock_session.post.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session
            
            new_creds = await tool._refresh_notion_token("tenant_123", mock_credentials)
            
            assert new_creds.access_token == "new_token"
            assert new_creds.refresh_token == "new_refresh_token"

    @pytest.mark.asyncio
    async def test_refresh_notion_token_failure(self, tool, mock_credentials):
        """Test token refresh failure."""
        with patch.object(tool, '_get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 400
            mock_response.text = AsyncMock(return_value="Invalid refresh token")
            mock_session.post.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session
            
            with pytest.raises(InvalidCredentialsError):
                await tool._refresh_notion_token("tenant_123", mock_credentials)

    def test_get_idempotency_key(self, tool):
        """Test idempotency key generation."""
        params = {"database_id": "db_123", "title": "Test"}
        key = asyncio.run(tool._get_idempotency_key("tenant_123", "create_database", params))
        
        # Should be deterministic
        key2 = asyncio.run(tool._get_idempotency_key("tenant_123", "create_database", params))
        assert key == key2
        
        # Different params should generate different key
        params2 = {"database_id": "db_456", "title": "Test"}
        key3 = asyncio.run(tool._get_idempotency_key("tenant_123", "create_database", params2))
        assert key != key3

    @pytest.mark.asyncio
    async def test_store_idempotency_result(self, tool):
        """Test storing idempotency result."""
        result = {"id": "page_123", "title": "Test Page"}
        await tool._store_idempotency_result("tenant_123", "key_456", result)
        
        # Check that result was stored
        cache_key = "tenant_123:key_456"
        assert cache_key in tool._idempotency_cache
        assert tool._idempotency_cache[cache_key]["result"] == result

    def test_verify_webhook_signature(self, tool):
        """Test webhook signature verification."""
        payload = b'{"type": "page.created", "object": "page"}'
        secret = "test_secret"
        
        # Generate valid signature
        import hmac
        import hashlib
        expected_sig = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        
        assert tool.verify_webhook_signature(payload, expected_sig, secret)
        assert not tool.verify_webhook_signature(payload, "invalid_sig", secret)

    def test_get_operation_schema(self, tool):
        """Test operation schema retrieval."""
        schema = tool._get_operation_schema("query_database")
        assert schema is not None
        assert "database_id" in schema
        assert schema["database_id"]["required"] is True
        
        # Test non-existent operation
        schema = tool._get_operation_schema("non_existent")
        assert schema is None

    @pytest.mark.asyncio
    async def test_handle_webhook_success(self, tool):
        """Test successful webhook handling."""
        payload = b'{"type": "page.created", "object": "page"}'
        secret = "test_secret"
        
        # Generate valid signature
        import hmac
        import hashlib
        signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        
        with patch.object(tool.secrets_manager, 'get_secret', return_value=secret):
            result = await tool.handle_webhook("tenant_123", payload, signature)
            
            assert result.success is True
            assert result.data["type"] == "page.created"
            assert result.metadata["webhook_verified"] is True

    @pytest.mark.asyncio
    async def test_handle_webhook_invalid_signature(self, tool):
        """Test webhook handling with invalid signature."""
        payload = b'{"type": "page.created", "object": "page"}'
        signature = "invalid_signature"
        
        with patch.object(tool.secrets_manager, 'get_secret', return_value="test_secret"):
            result = await tool.handle_webhook("tenant_123", payload, signature)
            
            assert result.success is False
            assert result.error_code == "INVALID_SIGNATURE"

    @pytest.mark.asyncio
    async def test_handle_webhook_missing_secret(self, tool):
        """Test webhook handling with missing secret."""
        payload = b'{"type": "page.created", "object": "page"}'
        signature = "test_signature"
        
        with patch.object(tool.secrets_manager, 'get_secret', return_value=None):
            result = await tool.handle_webhook("tenant_123", payload, signature)
            
            assert result.success is False
            assert result.error_code == "MISSING_SECRET"

    @pytest.mark.asyncio
    async def test_execute_operation_success(self, tool, mock_client):
        """Test successful operation execution."""
        tool._clients["tenant_123"] = mock_client
        
        # Mock the handler
        with patch.object(tool, '_handle_query_database', return_value={"results": []}):
            result = await tool._execute_operation(
                "tenant_123",
                "query_database",
                {"database_id": "db_123"}
            )
            
            assert result.success is True
            assert result.data == {"results": []}

    @pytest.mark.asyncio
    async def test_execute_operation_unsupported(self, tool, mock_client):
        """Test unsupported operation."""
        tool._clients["tenant_123"] = mock_client
        
        result = await tool._execute_operation(
            "tenant_123",
            "unsupported_operation",
            {}
        )
        
        assert result.success is False
        assert result.error_code == "UNSUPPORTED_OPERATION"

    @pytest.mark.asyncio
    async def test_execute_operation_with_idempotency(self, tool, mock_client):
        """Test operation execution with idempotency."""
        tool._clients["tenant_123"] = mock_client
        
        # Mock the handler
        with patch.object(tool, '_handle_create_page', return_value={"id": "page_123"}):
            # First call
            result1 = await tool._execute_operation(
                "tenant_123",
                "create_page",
                {"parent": {"page_id": "parent_123"}, "properties": {"title": "Test"}}
            )
            
            # Second call with same params should return cached result
            result2 = await tool._execute_operation(
                "tenant_123",
                "create_page",
                {"parent": {"page_id": "parent_123"}, "properties": {"title": "Test"}}
            )
            
            assert result1.success is True
            assert result2.success is True
            assert result2.metadata["cached"] is True

    @pytest.mark.asyncio
    async def test_close(self, tool):
        """Test tool cleanup."""
        # Add some mock clients and cache entries
        tool._clients["tenant_123"] = AsyncMock()
        tool._idempotency_cache["tenant_123:key_456"] = {"result": {}, "timestamp": time.time()}
        
        await tool.close()
        
        assert len(tool._clients) == 0
        assert len(tool._idempotency_cache) == 0


class TestNotionOperations:
    """Test individual Notion operations."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return MCPNotionTool()

    @pytest.fixture
    def mock_client(self):
        """Create mock client."""
        client = AsyncMock()
        client.databases = AsyncMock()
        client.pages = AsyncMock()
        client.blocks = AsyncMock()
        client.users = AsyncMock()
        client.search = AsyncMock()
        client.comments = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_handle_query_database(self, tool, mock_client):
        """Test database query operation."""
        mock_response = {
            "results": [{"id": "page_1", "properties": {"title": "Test"}}],
            "has_more": False,
            "next_cursor": None
        }
        mock_client.databases.query.return_value = mock_response
        
        params = {
            "database_id": "db_123",
            "filter": {"property": "Status", "select": {"equals": "Done"}},
            "sorts": [{"property": "Created", "direction": "descending"}],
            "page_size": 50
        }
        
        result = await tool._handle_query_database(mock_client, params)
        
        assert result == mock_response
        mock_client.databases.query.assert_called_once_with(
            database_id="db_123",
            filter=params["filter"],
            sorts=params["sorts"],
            start_cursor=None,
            page_size=50
        )

    @pytest.mark.asyncio
    async def test_handle_create_database(self, tool, mock_client):
        """Test database creation operation."""
        mock_response = {"id": "db_123", "title": [{"text": {"content": "Test DB"}}]}
        mock_client.databases.create.return_value = mock_response
        
        params = {
            "parent": {"page_id": "page_123"},
            "title": [{"text": {"content": "Test DB"}}],
            "properties": {
                "Name": {"title": {}},
                "Status": {"select": {"options": [{"name": "Todo"}, {"name": "Done"}]}}
            }
        }
        
        result = await tool._handle_create_database(mock_client, params)
        
        assert result == mock_response
        mock_client.databases.create.assert_called_once_with(
            parent=params["parent"],
            title=params["title"],
            properties=params["properties"],
            icon=None,
            cover=None
        )

    @pytest.mark.asyncio
    async def test_handle_create_page(self, tool, mock_client):
        """Test page creation operation."""
        mock_response = {"id": "page_123", "properties": {"title": "Test Page"}}
        mock_client.pages.create.return_value = mock_response
        
        params = {
            "parent": {"database_id": "db_123"},
            "properties": {"Name": {"title": [{"text": {"content": "Test Page"}}]}},
            "children": [{"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Content"}}]}}]
        }
        
        result = await tool._handle_create_page(mock_client, params)
        
        assert result == mock_response
        mock_client.pages.create.assert_called_once_with(
            parent=params["parent"],
            properties=params["properties"],
            children=params["children"],
            icon=None,
            cover=None
        )

    @pytest.mark.asyncio
    async def test_handle_search(self, tool, mock_client):
        """Test search operation."""
        mock_response = {
            "results": [{"id": "page_1", "object": "page"}],
            "has_more": False,
            "next_cursor": None
        }
        mock_client.search.return_value = mock_response
        
        params = {
            "query": "test query",
            "filter": {"property": "object", "value": "page"},
            "sort": {"direction": "ascending", "timestamp": "last_edited_time"},
            "page_size": 25
        }
        
        result = await tool._handle_search(mock_client, params)
        
        assert result == mock_response
        mock_client.search.assert_called_once_with(
            query="test query",
            filter=params["filter"],
            sort=params["sort"],
            start_cursor=None,
            page_size=25
        )

    @pytest.mark.asyncio
    async def test_handle_get_comments(self, tool, mock_client):
        """Test get comments operation."""
        mock_response = {
            "results": [{"id": "comment_1", "text": "Test comment"}],
            "has_more": False,
            "next_cursor": None
        }
        mock_client.comments.list.return_value = mock_response
        
        params = {
            "page_id": "page_123",
            "page_size": 50
        }
        
        result = await tool._handle_get_comments(mock_client, params)
        
        assert result == mock_response
        mock_client.comments.list.assert_called_once_with(
            block_id=None,
            page_id="page_123",
            start_cursor=None,
            page_size=50
        )

    @pytest.mark.asyncio
    async def test_handle_get_comments_missing_params(self, tool, mock_client):
        """Test get comments with missing required params."""
        with pytest.raises(ValidationError, match="Either block_id or page_id must be provided"):
            await tool._handle_get_comments(mock_client, {})


# VCR.py integration tests (to be run with real API calls)
class TestNotionIntegration:
    """Integration tests with VCR.py for real API calls."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return MCPNotionTool()

    @pytest.mark.asyncio
    @pytest.mark.vcr
    async def test_real_query_database(self, tool):
        """Test real database query (requires VCR cassette)."""
        # This test would use VCR.py to record real API calls
        # and replay them in subsequent test runs
        pass

    @pytest.mark.asyncio
    @pytest.mark.vcr
    async def test_real_create_page(self, tool):
        """Test real page creation (requires VCR cassette)."""
        # This test would use VCR.py to record real API calls
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
