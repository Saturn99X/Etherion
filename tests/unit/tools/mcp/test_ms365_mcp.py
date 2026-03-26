"""
Unit tests for Microsoft 365 MCP Tool.

Tests all Microsoft 365 operations with mocked Microsoft Graph API responses.
Uses VCR.py compatible fixtures for integration testing.

Author: Etherion AI Platform Team
Date: January 15, 2025
Version: 1.0.0
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.tools.mcp.mcp_ms365 import MCPMS365Tool, MS365Credentials
from src.tools.mcp.base_mcp_tool import (
    MCPToolResult,
    InvalidCredentialsError,
    RateLimitError,
    ValidationError,
    NetworkError,
    QuotaExceededError
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def ms365_tool():
    """Create Microsoft 365 MCP tool instance."""
    return MCPMS365Tool()


@pytest.fixture
def mock_credentials():
    """Create mock Microsoft 365 credentials."""
    return MS365Credentials(
        access_token="eyJ0eXAiOiJKV1QiLCJub25jZSI6...",
        refresh_token="0.AXoA1...",
        token_type="Bearer",
        expires_at=datetime.utcnow() + timedelta(hours=1),
        expires_in=3600,
        scope="User.Read Mail.Read Calendars.ReadWrite Files.ReadWrite.All",
        client_id="abc-123-def-456",
        client_secret="secret~value",
        tenant_id="common"
    )


@pytest.fixture
def mock_graph_response():
    """Create mock Microsoft Graph API response."""
    return {
        "value": [
            {
                "id": "msg_1",
                "subject": "Test Message 1",
                "from": {"emailAddress": {"address": "sender@example.com"}},
                "receivedDateTime": "2025-01-15T10:00:00Z"
            },
            {
                "id": "msg_2",
                "subject": "Test Message 2",
                "from": {"emailAddress": {"address": "sender2@example.com"}},
                "receivedDateTime": "2025-01-15T11:00:00Z"
            }
        ],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/messages?$skip=2"
    }


# ============================================================================
# CREDENTIALS TESTS
# ============================================================================


class TestMS365Credentials:
    """Test Microsoft 365 credentials handling."""
    
    def test_credentials_creation(self):
        """Test credentials creation from dict."""
        data = {
            "access_token": "eyJ0eXAiOiJKV1QiLCJub25jZSI6...",
            "refresh_token": "0.AXoA1...",
            "token_type": "Bearer",
            "expires_at": "2025-01-15T12:00:00Z",
            "expires_in": 3600,
            "scope": "User.Read Mail.Read",
            "client_id": "abc-123-def-456",
            "client_secret": "secret~value",
            "tenant_id": "common"
        }
        
        creds = MS365Credentials.from_dict(data)
        assert creds.access_token == "eyJ0eXAiOiJKV1QiLCJub25jZSI6..."
        assert creds.refresh_token == "0.AXoA1..."
        assert creds.client_id == "abc-123-def-456"
        assert creds.tenant_id == "common"
    
    def test_credentials_needs_refresh(self, mock_credentials):
        """Test token refresh detection."""
        # Token expires in 30 minutes - should need refresh
        mock_credentials.expires_at = datetime.utcnow() + timedelta(minutes=30)
        assert mock_credentials.needs_refresh() is True
        
        # Token expires in 2 hours - should not need refresh
        mock_credentials.expires_at = datetime.utcnow() + timedelta(hours=2)
        assert mock_credentials.needs_refresh() is False
    
    def test_credentials_is_expired(self, mock_credentials):
        """Test token expiration detection."""
        # Expired token
        mock_credentials.expires_at = datetime.utcnow() - timedelta(hours=1)
        assert mock_credentials.is_expired() is True
        
        # Valid token
        mock_credentials.expires_at = datetime.utcnow() + timedelta(hours=1)
        assert mock_credentials.is_expired() is False
    
    def test_credentials_to_dict(self, mock_credentials):
        """Test credentials serialization."""
        data = mock_credentials.to_dict()
        assert data["access_token"] == mock_credentials.access_token
        assert data["refresh_token"] == mock_credentials.refresh_token
        assert data["client_id"] == mock_credentials.client_id


# ============================================================================
# MICROSOFT 365 TOOL TESTS
# ============================================================================


class TestMCPMS365Tool:
    """Test Microsoft 365 MCP tool operations."""
    
    @pytest.mark.asyncio
    async def test_get_user_profile(self, ms365_tool, mock_credentials):
        """Test getting user profile."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "id": "user_123",
                    "displayName": "Test User",
                    "mail": "test@example.com"
                }
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_get_user_profile(
                    {"Authorization": "Bearer token"},
                    {}
                )
                
                assert result.success is True
                assert 'user' in result.data
                assert result.data['user']['displayName'] == "Test User"
    
    @pytest.mark.asyncio
    async def test_list_messages(self, ms365_tool, mock_graph_response):
        """Test listing messages."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_graph_response
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_list_messages(
                    {"Authorization": "Bearer token"},
                    {'folder': 'inbox', 'top': 10}
                )
                
                assert result.success is True
                assert 'messages' in result.data
                assert len(result.data['messages']) == 2
                assert result.data['count'] == 2
    
    @pytest.mark.asyncio
    async def test_get_message(self, ms365_tool):
        """Test getting specific message."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "id": "msg_1",
                    "subject": "Test Message",
                    "body": {"content": "Test content"}
                }
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_get_message(
                    {"Authorization": "Bearer token"},
                    {'message_id': 'msg_1'}
                )
                
                assert result.success is True
                assert 'message' in result.data
                assert result.data['message']['id'] == 'msg_1'
    
    @pytest.mark.asyncio
    async def test_send_mail(self, ms365_tool):
        """Test sending email."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.status = 202
                mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_send_mail(
                    {"Authorization": "Bearer token"},
                    {
                        'subject': 'Test Subject',
                        'body': 'Test body',
                        'to_recipients': ['recipient@example.com']
                    }
                )
                
                assert result.success is True
                assert result.data['status'] == 202
    
    @pytest.mark.asyncio
    async def test_list_events(self, ms365_tool):
        """Test listing calendar events."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "value": [
                        {
                            "id": "event_1",
                            "subject": "Meeting 1",
                            "start": {"dateTime": "2025-01-15T10:00:00Z"},
                            "end": {"dateTime": "2025-01-15T11:00:00Z"}
                        }
                    ]
                }
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_list_events(
                    {"Authorization": "Bearer token"},
                    {'start_date': '2025-01-15T00:00:00Z', 'end_date': '2025-01-15T23:59:59Z'}
                )
                
                assert result.success is True
                assert 'events' in result.data
                assert len(result.data['events']) == 1
                assert result.data['count'] == 1
    
    @pytest.mark.asyncio
    async def test_create_event(self, ms365_tool):
        """Test creating calendar event."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "id": "event_1",
                    "subject": "New Meeting",
                    "start": {"dateTime": "2025-01-15T10:00:00Z"},
                    "end": {"dateTime": "2025-01-15T11:00:00Z"}
                }
                mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_create_event(
                    {"Authorization": "Bearer token"},
                    {
                        'subject': 'New Meeting',
                        'start_datetime': '2025-01-15T10:00:00Z',
                        'end_datetime': '2025-01-15T11:00:00Z',
                        'attendees': ['attendee@example.com']
                    }
                )
                
                assert result.success is True
                assert 'event' in result.data
                assert result.data['event']['subject'] == 'New Meeting'
    
    @pytest.mark.asyncio
    async def test_list_drive_items(self, ms365_tool):
        """Test listing OneDrive items."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "value": [
                        {
                            "id": "file_1",
                            "name": "document.pdf",
                            "size": 1024,
                            "lastModifiedDateTime": "2025-01-15T10:00:00Z"
                        }
                    ]
                }
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_list_drive_items(
                    {"Authorization": "Bearer token"},
                    {'folder_id': 'root'}
                )
                
                assert result.success is True
                assert 'items' in result.data
                assert len(result.data['items']) == 1
                assert result.data['count'] == 1
    
    @pytest.mark.asyncio
    async def test_upload_file(self, ms365_tool):
        """Test uploading file to OneDrive."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "id": "file_1",
                    "name": "uploaded.txt",
                    "size": 100
                }
                mock_session.return_value.__aenter__.return_value.put.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_upload_file(
                    {"Authorization": "Bearer token"},
                    {
                        'file_path': 'uploaded.txt',
                        'content': b'Test content',
                        'content_type': 'text/plain'
                    }
                )
                
                assert result.success is True
                assert 'file' in result.data
                assert result.data['file']['name'] == 'uploaded.txt'
    
    @pytest.mark.asyncio
    async def test_list_teams(self, ms365_tool):
        """Test listing user's teams."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "value": [
                        {
                            "id": "team_1",
                            "displayName": "Test Team",
                            "description": "Test team description"
                        }
                    ]
                }
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_list_teams(
                    {"Authorization": "Bearer token"},
                    {}
                )
                
                assert result.success is True
                assert 'teams' in result.data
                assert len(result.data['teams']) == 1
                assert result.data['count'] == 1
    
    @pytest.mark.asyncio
    async def test_send_team_message(self, ms365_tool):
        """Test sending Teams message."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "id": "msg_1",
                    "body": {"content": "Test message"},
                    "createdDateTime": "2025-01-15T10:00:00Z"
                }
                mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_send_team_message(
                    {"Authorization": "Bearer token"},
                    {
                        'team_id': 'team_1',
                        'channel_id': 'channel_1',
                        'message_content': 'Test message'
                    }
                )
                
                assert result.success is True
                assert 'message' in result.data
                assert result.data['message']['id'] == 'msg_1'
    
    @pytest.mark.asyncio
    async def test_list_sharepoint_sites(self, ms365_tool):
        """Test listing SharePoint sites."""
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "value": [
                        {
                            "id": "site_1",
                            "displayName": "Test Site",
                            "webUrl": "https://example.sharepoint.com/sites/test"
                        }
                    ]
                }
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                
                result = await ms365_tool._handle_list_sharepoint_sites(
                    {"Authorization": "Bearer token"},
                    {}
                )
                
                assert result.success is True
                assert 'sites' in result.data
                assert len(result.data['sites']) == 1
                assert result.data['count'] == 1


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestMS365ErrorHandling:
    """Test Microsoft 365 error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_authentication_error(self, ms365_tool):
        """Test authentication error handling."""
        import aiohttp
        
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=401,
            message="Unauthorized"
        )
        
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.side_effect = error
                
                with pytest.raises(InvalidCredentialsError):
                    await ms365_tool._handle_get_user_profile(
                        {"Authorization": "Bearer token"},
                        {}
                    )
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, ms365_tool):
        """Test rate limit error handling."""
        import aiohttp
        
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=429,
            message="Too Many Requests",
            headers={'Retry-After': '60'}
        )
        
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.side_effect = error
                
                with pytest.raises(RateLimitError):
                    await ms365_tool._handle_get_user_profile(
                        {"Authorization": "Bearer token"},
                        {}
                    )
    
    @pytest.mark.asyncio
    async def test_quota_exceeded_error(self, ms365_tool):
        """Test quota exceeded error handling."""
        import aiohttp
        
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=403,
            message="Forbidden"
        )
        
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.side_effect = error
                
                with pytest.raises(QuotaExceededError):
                    await ms365_tool._handle_get_user_profile(
                        {"Authorization": "Bearer token"},
                        {}
                    )
    
    @pytest.mark.asyncio
    async def test_network_error(self, ms365_tool):
        """Test network error handling."""
        import aiohttp
        
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=500,
            message="Internal Server Error"
        )
        
        with patch.object(ms365_tool, '_get_graph_headers', return_value={"Authorization": "Bearer token"}):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.side_effect = error
                
                with pytest.raises(NetworkError):
                    await ms365_tool._handle_get_user_profile(
                        {"Authorization": "Bearer token"},
                        {}
                    )


# ============================================================================
# VALIDATION TESTS
# ============================================================================


class TestMS365Validation:
    """Test Microsoft 365 parameter validation."""
    
    def test_validate_operation_params_list_messages(self, ms365_tool):
        """Test parameter validation for list_messages."""
        params = {'top': 1000}  # Should be capped at 100
        validated = ms365_tool._validate_operation_params('list_messages', params)
        assert validated['top'] == 100
    
    def test_validate_operation_params_send_mail(self, ms365_tool):
        """Test parameter validation for send_mail."""
        # Missing required fields
        with pytest.raises(ValidationError):
            ms365_tool._validate_operation_params('send_mail', {})
        
        # Invalid email
        with pytest.raises(ValidationError):
            ms365_tool._validate_operation_params('send_mail', {
                'subject': 'Test',
                'body': 'Test body',
                'to_recipients': ['invalid-email']
            })
    
    def test_validate_operation_params_create_event(self, ms365_tool):
        """Test parameter validation for create_event."""
        # Missing required fields
        with pytest.raises(ValidationError):
            ms365_tool._validate_operation_params('create_event', {})
        
        # Missing subject
        with pytest.raises(ValidationError):
            ms365_tool._validate_operation_params('create_event', {
                'start_datetime': '2025-01-15T10:00:00Z',
                'end_datetime': '2025-01-15T11:00:00Z'
            })
    
    def test_validate_operation_params_upload_file(self, ms365_tool):
        """Test parameter validation for upload_file."""
        # Missing required fields
        with pytest.raises(ValidationError):
            ms365_tool._validate_operation_params('upload_file', {})
        
        # Missing file_path
        with pytest.raises(ValidationError):
            ms365_tool._validate_operation_params('upload_file', {
                'content': b'test'
            })
    
    def test_validate_operation_params_teams_operations(self, ms365_tool):
        """Test parameter validation for Teams operations."""
        # Missing team_id
        with pytest.raises(ValidationError):
            ms365_tool._validate_operation_params('get_team', {})
        
        # Missing channel_id for send_team_message
        with pytest.raises(ValidationError):
            ms365_tool._validate_operation_params('send_team_message', {
                'team_id': 'team_1',
                'message_content': 'Test'
            })


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestMS365Integration:
    """Test Microsoft 365 tool integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, ms365_tool, mock_credentials):
        """Test complete Microsoft 365 workflow."""
        # Mock secrets manager
        with patch.object(ms365_tool.secrets_manager, 'get_secret', return_value=mock_credentials.to_dict()):
            # Mock Graph API response
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "id": "user_123",
                    "displayName": "Test User"
                }
                mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                
                # Execute workflow
                result = await ms365_tool.execute(
                    tenant_id="tenant_123",
                    operation="get_user_profile",
                    params={}
                )
                
                assert result.success is True
                assert 'user' in result.data
    
    @pytest.mark.asyncio
    async def test_credential_refresh_workflow(self, ms365_tool, mock_credentials):
        """Test credential refresh workflow."""
        # Set credentials to need refresh
        mock_credentials.expires_at = datetime.utcnow() - timedelta(hours=1)
        
        # Mock secrets manager
        with patch.object(ms365_tool.secrets_manager, 'get_secret', return_value=mock_credentials.to_dict()):
            with patch.object(ms365_tool.secrets_manager, 'set_secret') as mock_set_secret:
                with patch.object(ms365_tool, '_refresh_ms365_token') as mock_refresh:
                    # Mock refreshed credentials
                    refreshed_creds = MS365Credentials(
                        access_token="new_token",
                        refresh_token=mock_credentials.refresh_token,
                        expires_at=datetime.utcnow() + timedelta(hours=1),
                        client_id=mock_credentials.client_id,
                        client_secret=mock_credentials.client_secret,
                        tenant_id=mock_credentials.tenant_id
                    )
                    mock_refresh.return_value = refreshed_creds
                    
                    # Mock Graph API response
                    with patch('aiohttp.ClientSession') as mock_session:
                        mock_response = MagicMock()
                        mock_response.json.return_value = {"id": "user_123"}
                        mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
                        
                        # Execute operation
                        result = await ms365_tool.execute(
                            tenant_id="tenant_123",
                            operation="get_user_profile",
                            params={}
                        )
                        
                        # Verify refresh was called
                        mock_refresh.assert_called_once()
                        mock_set_secret.assert_called_once()
                        assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__])
