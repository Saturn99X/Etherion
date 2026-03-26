"""
Unit tests for Gmail MCP Tool.

Tests all Gmail operations with mocked Gmail API responses.
Uses VCR.py compatible fixtures for integration testing.

Author: Etherion AI Platform Team
Date: January 15, 2025
Version: 1.0.0
"""

import asyncio
import base64
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.tools.mcp.mcp_gmail import MCPGmailTool, GmailCredentials
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
def gmail_tool():
    """Create Gmail MCP tool instance."""
    return MCPGmailTool()


@pytest.fixture
def mock_credentials():
    """Create mock Gmail credentials."""
    return GmailCredentials(
        access_token="ya29.a0AfH6...",
        refresh_token="1//0gJx...",
        client_id="123456789.apps.googleusercontent.com",
        client_secret="GOCSPX-...",
        expiry=datetime.utcnow() + timedelta(hours=1)
    )


@pytest.fixture
def mock_gmail_service():
    """Create mock Gmail service."""
    service = MagicMock()
    
    # Mock users().messages().list()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        'messages': [
            {'id': 'msg_1', 'threadId': 'thread_1'},
            {'id': 'msg_2', 'threadId': 'thread_2'}
        ],
        'nextPageToken': 'next_token',
        'resultSizeEstimate': 2
    }
    
    # Mock users().messages().get()
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        'id': 'msg_1',
        'threadId': 'thread_1',
        'labelIds': ['INBOX', 'UNREAD'],
        'snippet': 'Test message',
        'payload': {
            'headers': [
                {'name': 'From', 'value': 'test@example.com'},
                {'name': 'To', 'value': 'user@example.com'},
                {'name': 'Subject', 'value': 'Test Subject'}
            ]
        }
    }
    
    # Mock users().messages().send()
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        'id': 'sent_msg_1',
        'threadId': 'thread_1',
        'labelIds': ['SENT']
    }
    
    # Mock users().labels().list()
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        'labels': [
            {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
            {'id': 'SENT', 'name': 'SENT', 'type': 'system'},
            {'id': 'UNREAD', 'name': 'UNREAD', 'type': 'system'}
        ]
    }
    
    # Mock users().getProfile()
    service.users.return_value.getProfile.return_value.execute.return_value = {
        'emailAddress': 'user@example.com',
        'messagesTotal': 1000,
        'threadsTotal': 500,
        'historyId': '12345'
    }
    
    return service


# ============================================================================
# CREDENTIALS TESTS
# ============================================================================


class TestGmailCredentials:
    """Test Gmail credentials handling."""
    
    def test_credentials_creation(self):
        """Test credentials creation from dict."""
        data = {
            "access_token": "ya29.a0AfH6...",
            "refresh_token": "1//0gJx...",
            "client_id": "123456789.apps.googleusercontent.com",
            "client_secret": "GOCSPX-...",
            "expiry": "2025-01-15T12:00:00Z"
        }
        
        creds = GmailCredentials.from_dict(data)
        assert creds.access_token == "ya29.a0AfH6..."
        assert creds.refresh_token == "1//0gJx..."
        assert creds.client_id == "123456789.apps.googleusercontent.com"
    
    def test_credentials_needs_refresh(self, mock_credentials):
        """Test token refresh detection."""
        # Token expires in 30 minutes - should need refresh
        mock_credentials.expiry = datetime.utcnow() + timedelta(minutes=30)
        assert mock_credentials.needs_refresh() is True
        
        # Token expires in 2 hours - should not need refresh
        mock_credentials.expiry = datetime.utcnow() + timedelta(hours=2)
        assert mock_credentials.needs_refresh() is False
    
    def test_credentials_is_expired(self, mock_credentials):
        """Test token expiration detection."""
        # Expired token
        mock_credentials.expiry = datetime.utcnow() - timedelta(hours=1)
        assert mock_credentials.is_expired() is True
        
        # Valid token
        mock_credentials.expiry = datetime.utcnow() + timedelta(hours=1)
        assert mock_credentials.is_expired() is False
    
    def test_credentials_to_dict(self, mock_credentials):
        """Test credentials serialization."""
        data = mock_credentials.to_dict()
        assert data["access_token"] == mock_credentials.access_token
        assert data["refresh_token"] == mock_credentials.refresh_token
        assert data["client_id"] == mock_credentials.client_id


# ============================================================================
# GMAIL TOOL TESTS
# ============================================================================


class TestMCPGmailTool:
    """Test Gmail MCP tool operations."""
    
    @pytest.mark.asyncio
    async def test_list_messages(self, gmail_tool, mock_gmail_service):
        """Test listing messages."""
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_list_messages(
                mock_gmail_service,
                {'query': 'is:unread', 'max_results': 10}
            )
            
            assert result.success is True
            assert 'messages' in result.data
            assert len(result.data['messages']) == 2
            assert result.data['next_page_token'] == 'next_token'
    
    @pytest.mark.asyncio
    async def test_get_message(self, gmail_tool, mock_gmail_service):
        """Test getting message details."""
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_get_message(
                mock_gmail_service,
                {'message_id': 'msg_1', 'format': 'full'}
            )
            
            assert result.success is True
            assert 'message' in result.data
            assert result.data['message']['id'] == 'msg_1'
    
    @pytest.mark.asyncio
    async def test_send_message(self, gmail_tool, mock_gmail_service):
        """Test sending message."""
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            params = {
                'to': 'test@example.com',
                'subject': 'Test Subject',
                'text_body': 'Test message body',
                'html_body': '<p>Test message body</p>'
            }
            
            result = await gmail_tool._handle_send_message(mock_gmail_service, params)
            
            assert result.success is True
            assert 'message_id' in result.data
            assert result.data['message_id'] == 'sent_msg_1'
    
    @pytest.mark.asyncio
    async def test_send_message_with_attachments(self, gmail_tool, mock_gmail_service):
        """Test sending message with attachments."""
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            params = {
                'to': 'test@example.com',
                'subject': 'Test Subject',
                'text_body': 'Test message body',
                'attachments': [
                    {
                        'filename': 'test.txt',
                        'content_type': 'text/plain',
                        'data': b'Test attachment content'
                    }
                ]
            }
            
            result = await gmail_tool._handle_send_message(mock_gmail_service, params)
            
            assert result.success is True
            assert 'message_id' in result.data
    
    @pytest.mark.asyncio
    async def test_search_messages(self, gmail_tool, mock_gmail_service):
        """Test searching messages."""
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_search_messages(
                mock_gmail_service,
                {'query': 'from:test@example.com', 'max_results': 5}
            )
            
            assert result.success is True
            assert 'messages' in result.data
            assert len(result.data['messages']) == 2
    
    @pytest.mark.asyncio
    async def test_get_thread(self, gmail_tool, mock_gmail_service):
        """Test getting email thread."""
        # Mock thread response
        mock_gmail_service.users.return_value.threads.return_value.get.return_value.execute.return_value = {
            'id': 'thread_1',
            'messages': [
                {'id': 'msg_1', 'threadId': 'thread_1'},
                {'id': 'msg_2', 'threadId': 'thread_1'}
            ]
        }
        
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_get_thread(
                mock_gmail_service,
                {'thread_id': 'thread_1', 'format': 'full'}
            )
            
            assert result.success is True
            assert 'thread' in result.data
            assert result.data['thread']['id'] == 'thread_1'
    
    @pytest.mark.asyncio
    async def test_modify_message(self, gmail_tool, mock_gmail_service):
        """Test modifying message (adding/removing labels)."""
        # Mock modify response
        mock_gmail_service.users.return_value.messages.return_value.modify.return_value.execute.return_value = {
            'id': 'msg_1',
            'threadId': 'thread_1',
            'labelIds': ['INBOX', 'STARRED']
        }
        
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_modify_message(
                mock_gmail_service,
                {
                    'message_id': 'msg_1',
                    'add_labels': ['STARRED'],
                    'remove_labels': ['UNREAD']
                }
            )
            
            assert result.success is True
            assert 'message_id' in result.data
            assert result.data['message_id'] == 'msg_1'
    
    @pytest.mark.asyncio
    async def test_get_labels(self, gmail_tool, mock_gmail_service):
        """Test getting Gmail labels."""
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_get_labels(mock_gmail_service, {})
            
            assert result.success is True
            assert 'labels' in result.data
            assert len(result.data['labels']) == 3
    
    @pytest.mark.asyncio
    async def test_create_label(self, gmail_tool, mock_gmail_service):
        """Test creating new label."""
        # Mock create label response
        mock_gmail_service.users.return_value.labels.return_value.create.return_value.execute.return_value = {
            'id': 'label_1',
            'name': 'Test Label',
            'type': 'user'
        }
        
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_create_label(
                mock_gmail_service,
                {'name': 'Test Label'}
            )
            
            assert result.success is True
            assert 'label' in result.data
            assert result.data['label']['name'] == 'Test Label'
    
    @pytest.mark.asyncio
    async def test_get_profile(self, gmail_tool, mock_gmail_service):
        """Test getting Gmail profile."""
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_get_profile(mock_gmail_service, {})
            
            assert result.success is True
            assert 'profile' in result.data
            assert result.data['profile']['emailAddress'] == 'user@example.com'
    
    @pytest.mark.asyncio
    async def test_get_attachment(self, gmail_tool, mock_gmail_service):
        """Test getting message attachment."""
        # Mock attachment response
        attachment_data = base64.urlsafe_b64encode(b'Test attachment content').decode()
        mock_gmail_service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.return_value = {
            'size': 20,
            'data': attachment_data
        }
        
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            result = await gmail_tool._handle_get_attachment(
                mock_gmail_service,
                {
                    'message_id': 'msg_1',
                    'attachment_id': 'att_1',
                    'filename': 'test.txt'
                }
            )
            
            assert result.success is True
            assert 'data' in result.data
            assert result.data['size'] == 20
            assert result.data['filename'] == 'test.txt'


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestGmailErrorHandling:
    """Test Gmail error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, gmail_tool, mock_gmail_service):
        """Test rate limit error handling."""
        from googleapiclient.errors import HttpError
        
        # Mock 429 response
        error = HttpError(
            resp=MagicMock(status=429),
            content=b'Rate limit exceeded'
        )
        mock_gmail_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = error
        
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            with pytest.raises(RateLimitError):
                await gmail_tool._handle_list_messages(mock_gmail_service, {})
    
    @pytest.mark.asyncio
    async def test_quota_exceeded_error(self, gmail_tool, mock_gmail_service):
        """Test quota exceeded error handling."""
        from googleapiclient.errors import HttpError
        
        # Mock 403 quota error
        error = HttpError(
            resp=MagicMock(status=403),
            content=b'Quota exceeded'
        )
        mock_gmail_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = error
        
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            with pytest.raises(QuotaExceededError):
                await gmail_tool._handle_list_messages(mock_gmail_service, {})
    
    @pytest.mark.asyncio
    async def test_network_error(self, gmail_tool, mock_gmail_service):
        """Test network error handling."""
        from googleapiclient.errors import HttpError
        
        # Mock 500 error
        error = HttpError(
            resp=MagicMock(status=500),
            content=b'Internal server error'
        )
        mock_gmail_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = error
        
        with patch.object(gmail_tool, '_get_gmail_service', return_value=mock_gmail_service):
            with pytest.raises(NetworkError):
                await gmail_tool._handle_list_messages(mock_gmail_service, {})


# ============================================================================
# VALIDATION TESTS
# ============================================================================


class TestGmailValidation:
    """Test Gmail parameter validation."""
    
    def test_validate_operation_params_list_messages(self, gmail_tool):
        """Test parameter validation for list_messages."""
        params = {'max_results': 1000}  # Should be capped at 500
        validated = gmail_tool._validate_operation_params('list_messages', params)
        assert validated['max_results'] == 500
    
    def test_validate_operation_params_send_message(self, gmail_tool):
        """Test parameter validation for send_message."""
        # Missing required fields
        with pytest.raises(ValidationError):
            gmail_tool._validate_operation_params('send_message', {})
        
        # Invalid email
        with pytest.raises(ValidationError):
            gmail_tool._validate_operation_params('send_message', {
                'to': 'invalid-email',
                'subject': 'Test'
            })
    
    def test_validate_operation_params_get_message(self, gmail_tool):
        """Test parameter validation for get_message."""
        # Missing message_id
        with pytest.raises(ValidationError):
            gmail_tool._validate_operation_params('get_message', {})
    
    def test_validate_operation_params_create_label(self, gmail_tool):
        """Test parameter validation for create_label."""
        # Missing name
        with pytest.raises(ValidationError):
            gmail_tool._validate_operation_params('create_label', {})


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestGmailIntegration:
    """Test Gmail tool integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, gmail_tool, mock_credentials):
        """Test complete Gmail workflow."""
        # Mock secrets manager
        with patch.object(gmail_tool.secrets_manager, 'get_secret', return_value=mock_credentials.to_dict()):
            # Mock Gmail service
            with patch.object(gmail_tool, '_get_gmail_service') as mock_get_service:
                mock_service = MagicMock()
                mock_get_service.return_value = mock_service
                
                # Mock list messages
                mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
                    'messages': [{'id': 'msg_1', 'threadId': 'thread_1'}]
                }
                
                # Execute workflow
                result = await gmail_tool.execute(
                    tenant_id="tenant_123",
                    operation="list_messages",
                    params={'query': 'is:unread'}
                )
                
                assert result.success is True
                assert 'messages' in result.data
    
    @pytest.mark.asyncio
    async def test_credential_refresh_workflow(self, gmail_tool, mock_credentials):
        """Test credential refresh workflow."""
        # Set credentials to need refresh
        mock_credentials.expiry = datetime.utcnow() - timedelta(hours=1)
        
        # Mock secrets manager
        with patch.object(gmail_tool.secrets_manager, 'get_secret', return_value=mock_credentials.to_dict()):
            with patch.object(gmail_tool.secrets_manager, 'set_secret') as mock_set_secret:
                with patch.object(gmail_tool, '_refresh_gmail_token') as mock_refresh:
                    # Mock refreshed credentials
                    refreshed_creds = GmailCredentials(
                        access_token="new_token",
                        refresh_token=mock_credentials.refresh_token,
                        client_id=mock_credentials.client_id,
                        client_secret=mock_credentials.client_secret,
                        expiry=datetime.utcnow() + timedelta(hours=1)
                    )
                    mock_refresh.return_value = refreshed_creds
                    
                    # Mock Gmail service
                    with patch.object(gmail_tool, '_get_gmail_service') as mock_get_service:
                        mock_service = MagicMock()
                        mock_get_service.return_value = mock_service
                        
                        # Execute operation
                        result = await gmail_tool.execute(
                            tenant_id="tenant_123",
                            operation="get_profile",
                            params={}
                        )
                        
                        # Verify refresh was called
                        mock_refresh.assert_called_once()
                        mock_set_secret.assert_called_once()
                        assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__])
