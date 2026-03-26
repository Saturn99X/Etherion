import asyncio
import json
import pytest
import hmac
import hashlib
from unittest.mock import AsyncMock, patch

from src.tools.mcp.mcp_jira import MCPJiraTool
from src.tools.mcp.base_mcp_tool import MCPToolResult, InvalidCredentialsError, ValidationError


@pytest.fixture
def tool():
    return MCPJiraTool()


@pytest.mark.asyncio
async def test_missing_credentials(tool):
    with patch.object(tool.secrets_manager, 'get_secret', return_value=None):
        with pytest.raises(InvalidCredentialsError):
            await tool.execute("tenant_1", "get_projects", {})


@pytest.mark.asyncio
async def test_get_projects_success(tool):
    async def fake_get_secret(tenant_id, service_name, key_type):
        if key_type == 'email':
            return 'user@example.com'
        if key_type == 'api_token':
            return 'ATATT3X...'
        if key_type == 'cloud_id':
            return 'abc123'
        return None

    with patch.object(tool.secrets_manager, 'get_secret', side_effect=fake_get_secret):
        with patch.object(tool, '_make_request', return_value={"values": []}) as mock_req:
            res = await tool.execute("tenant_1", "get_projects", {})
            assert isinstance(res, MCPToolResult)
            assert res.success is True
            mock_req.assert_called_once()


@pytest.mark.asyncio
async def test_get_issue_schema_validation(tool):
    # Missing required issue_key should raise ValidationError before any HTTP
    async def fake_get_secret(tenant_id, service_name, key_type):
        return 'x'  # ensure credentials exist so we reach validation first

    with patch.object(tool.secrets_manager, 'get_secret', side_effect=fake_get_secret):
        with pytest.raises(ValidationError):
            await tool.execute("tenant_1", "get_issue", {})


@pytest.mark.asyncio
async def test_create_issue_idempotency(tool):
    async def fake_get_secret(tenant_id, service_name, key_type):
        if key_type == 'email':
            return 'user@example.com'
        if key_type == 'api_token':
            return 'ATATT3X...'
        if key_type == 'cloud_id':
            return 'abc123'
        return None

    payload = {
        "project_key": "PRJ",
        "summary": "Create from test",
        "issue_type": "Task",
        "description": "Body",
    }

    with patch.object(tool.secrets_manager, 'get_secret', side_effect=fake_get_secret):
        with patch.object(tool, '_make_request', return_value={"id": "JIRA-1"}) as mock_req:
            res1 = await tool.execute("t1", "create_issue", payload)
            res2 = await tool.execute("t1", "create_issue", payload)
            assert res1.success and res2.success
            assert res2.metadata.get("cached") is True
            # Only the first call should hit HTTP
            assert mock_req.call_count == 1


@pytest.mark.asyncio
async def test_webhook_verification_success(tool):
    """Test successful webhook verification."""
    payload = b'{"webhookEvent": "jira:issue_updated", "issue": {"key": "JIRA-1"}}'
    secret = "test_webhook_secret"
    
    # Generate valid HMAC signature
    signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    
    with patch.object(tool.secrets_manager, 'get_secret', return_value=secret):
        result = await tool.handle_webhook("tenant_1", payload, signature)
        
        assert result.success is True
        assert result.data["webhookEvent"] == "jira:issue_updated"
        assert result.metadata["webhook_verified"] is True


@pytest.mark.asyncio
async def test_webhook_verification_invalid_signature(tool):
    """Test webhook verification with invalid signature."""
    payload = b'{"webhookEvent": "jira:issue_updated"}'
    secret = "test_webhook_secret"
    invalid_signature = "invalid_signature"
    
    with patch.object(tool.secrets_manager, 'get_secret', return_value=secret):
        result = await tool.handle_webhook("tenant_1", payload, invalid_signature)
        
        assert result.success is False
        assert result.error_code == "INVALID_SIGNATURE"


@pytest.mark.asyncio
async def test_webhook_verification_missing_secret(tool):
    """Test webhook verification with missing secret."""
    payload = b'{"webhookEvent": "jira:issue_updated"}'
    signature = "test_signature"
    
    with patch.object(tool.secrets_manager, 'get_secret', return_value=None):
        result = await tool.handle_webhook("tenant_1", payload, signature)
        
        assert result.success is False
        assert result.error_code == "MISSING_WEBHOOK_SECRET"


@pytest.mark.asyncio
async def test_webhook_verification_topic_filter(tool):
    """Test webhook verification with topic filtering."""
    payload = b'{"webhookEvent": "jira:issue_created", "issue": {"key": "JIRA-1"}}'
    secret = "test_webhook_secret"
    signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    
    with patch.object(tool.secrets_manager, 'get_secret', return_value=secret):
        # Test with matching topic
        result = await tool.handle_webhook("tenant_1", payload, signature, topic="jira:issue_created")
        assert result.success is True
        
        # Test with non-matching topic
        result = await tool.handle_webhook("tenant_1", payload, signature, topic="jira:issue_updated")
        assert result.success is False
        assert result.error_code == "TOPIC_MISMATCH"


@pytest.mark.asyncio
async def test_webhook_verification_invalid_json(tool):
    """Test webhook verification with invalid JSON."""
    payload = b'invalid json'
    secret = "test_webhook_secret"
    signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    
    with patch.object(tool.secrets_manager, 'get_secret', return_value=secret):
        result = await tool.handle_webhook("tenant_1", payload, signature)
        
        assert result.success is False
        assert result.error_code == "INVALID_JSON"


