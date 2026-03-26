"""
Tests for MCP tools with real API integration and confirm_action functionality.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.mcp.mcp_slack import MCPSlackTool
from src.tools.mcp.mcp_email import MCPEmailTool
from src.tools.confirm_action_tool import ConfirmActionTool
from src.tools.mcp.base_mcp_tool import MCPToolResult, InvalidCredentialsError, RateLimitError


class TestMCPSlackTool:
    """Test MCP Slack tool with real API integration."""
    
    @pytest.fixture
    def slack_tool(self):
        return MCPSlackTool()
    
    @pytest.fixture
    def mock_secrets_manager(self):
        with patch('src.tools.mcp.mcp_slack.TenantSecretsManager') as mock:
            mock_instance = AsyncMock()
            mock_instance.get_secret.return_value = "xoxb-test-token"
            mock.return_value = mock_instance
            yield mock_instance
    
    @pytest.mark.asyncio
    async def test_get_channel_history_success(self, slack_tool):
        """Test successful channel history retrieval."""
        # Mock successful API response
        mock_response_data = {
            "ok": True,
            "messages": [
                {
                    "ts": "1512085950.000216",
                    "type": "message",
                    "user": "U012AB3CD",
                    "text": "Hello team!"
                }
            ],
            "has_more": False
        }
        
        # Mock the secrets manager instance method
        slack_tool.secrets_manager.get_secret = AsyncMock(return_value="xoxb-test-token")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await slack_tool.execute({
                "tenant_id": "test_tenant",
                "action": "get_channel_history",
                "channel_id": "C012AB3CD",
                "limit": 100
            })
            
            assert result.success is True
            assert "messages" in result.data
            assert result.data["channel_id"] == "C012AB3CD"
    
    @pytest.mark.asyncio
    async def test_get_channel_history_missing_credentials(self, slack_tool):
        """Test channel history with missing credentials."""
        with patch('src.tools.mcp.mcp_slack.TenantSecretsManager') as mock:
            mock_instance = AsyncMock()
            mock_instance.get_secret.return_value = None
            mock.return_value = mock_instance
            
            result = await slack_tool.execute({
                "tenant_id": "test_tenant",
                "action": "get_channel_history",
                "channel_id": "C012AB3CD"
            })
            
            assert result.success is False
            assert "MISSING_CREDENTIALS" in result.error_code
    
    @pytest.mark.asyncio
    async def test_get_channel_history_rate_limit(self, slack_tool, mock_secrets_manager):
        """Test channel history with rate limit error."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.text = "Rate limited"
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await slack_tool.execute({
                "tenant_id": "test_tenant",
                "action": "get_channel_history",
                "channel_id": "C012AB3CD"
            })
            
            assert result.success is False
            assert "RATE_LIMIT_EXCEEDED" in result.error_code
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, slack_tool, mock_secrets_manager):
        """Test successful message sending."""
        mock_response_data = {
            "ok": True,
            "message": {"text": "Test message"},
            "channel": "C012AB3CD",
            "ts": "1512085950.000216"
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            result = await slack_tool.execute({
                "tenant_id": "test_tenant",
                "action": "send_message",
                "channel_id": "C012AB3CD",
                "message": "Test message"
            })
            
            assert result.success is True
            assert "message" in result.data
            assert result.data["channel"] == "C012AB3CD"
    
    @pytest.mark.asyncio
    async def test_input_sanitization(self, slack_tool, mock_secrets_manager):
        """Test input sanitization for security."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True, "messages": []}
            mock_response.raise_for_status.return_value = None
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            # Test with potentially malicious input
            result = await slack_tool.execute({
                "tenant_id": "<script>alert('xss')</script>",
                "action": "get_channel_history",
                "channel_id": "C012AB3CD"
            })
            
            # Should sanitize the tenant_id
            assert result.success is True
            # The sanitized tenant_id should not contain script tags
            mock_secrets_manager.get_secret.assert_called_once()
            call_args = mock_secrets_manager.get_secret.call_args
            assert "<script>" not in str(call_args)


class TestMCPEmailTool:
    """Test MCP Email tool with real API integration."""
    
    @pytest.fixture
    def email_tool(self):
        return MCPEmailTool()
    
    @pytest.fixture
    def mock_secrets_manager(self):
        with patch('src.tools.mcp.mcp_email.TenantSecretsManager') as mock:
            mock_instance = AsyncMock()
            mock_instance.get_secret.return_value = "test-api-key"
            mock.return_value = mock_instance
            yield mock_instance
    
    @pytest.mark.asyncio
    async def test_send_email_resend_success(self, email_tool, mock_secrets_manager):
        """Test successful email sending via Resend."""
        mock_response_data = {
            "id": "test-message-id",
            "to": ["test@example.com"],
            "from": "noreply@resend.dev"
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            result = await email_tool.execute({
                "tenant_id": "test_tenant",
                "action": "send_email",
                "to": "test@example.com",
                "subject": "Test Subject",
                "body": "Test message body"
            })
            
            assert result.success is True
            assert "message_id" in result.data
            assert result.data["service"] == "resend"
    
    @pytest.mark.asyncio
    async def test_send_email_sendgrid_success(self, email_tool):
        """Test successful email sending via SendGrid."""
        with patch('src.tools.mcp.mcp_email.TenantSecretsManager') as mock:
            mock_instance = AsyncMock()
            mock_instance.get_secret.side_effect = lambda tenant_id, service_name, key_type: (
                "test-sendgrid-key" if service_name == "sendgrid" else None
            )
            mock.return_value = mock_instance
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 202  # SendGrid returns 202 for accepted
                mock_response.headers = {"X-Message-Id": "test-message-id"}
                mock_response.raise_for_status.return_value = None
                
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                
                result = await email_tool.execute({
                    "tenant_id": "test_tenant",
                    "action": "send_email",
                    "to": "test@example.com",
                    "subject": "Test Subject",
                    "body": "Test message body"
                })
                
                assert result.success is True
                assert "message_id" in result.data
                assert result.data["service"] == "sendgrid"
    
    @pytest.mark.asyncio
    async def test_email_validation(self, email_tool, mock_secrets_manager):
        """Test email address validation."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "test-message-id"}
            mock_response.raise_for_status.return_value = None
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            # Test with invalid email
            result = await email_tool.execute({
                "tenant_id": "test_tenant",
                "action": "send_email",
                "to": "invalid-email",
                "subject": "Test Subject",
                "body": "Test message body"
            })
            
            assert result.success is False
            assert "MISSING_FIELD" in result.error_code or "Invalid email format" in result.error_message
    
    @pytest.mark.asyncio
    async def test_email_sanitization(self, email_tool, mock_secrets_manager):
        """Test email content sanitization."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "test-message-id"}
            mock_response.raise_for_status.return_value = None
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            # Test with potentially malicious content
            result = await email_tool.execute({
                "tenant_id": "test_tenant",
                "action": "send_email",
                "to": "test@example.com",
                "subject": "<script>alert('xss')</script>",
                "body": "Test message body"
            })
            
            assert result.success is True
            # The subject should be sanitized (HTML escaped)
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            payload = call_args[1]["json"]
            assert "&lt;script&gt;" in payload["subject"]


class TestConfirmActionTool:
    """Test confirm_action tool functionality."""
    
    @pytest.fixture
    def confirm_tool(self):
        return ConfirmActionTool()
    
    @pytest.mark.asyncio
    async def test_confirm_action_success(self, confirm_tool):
        """Test successful action confirmation."""
        result = await confirm_tool.execute({
            "action_description": "Send email to marketing team",
            "action_parameters": {
                "to": "marketing@company.com",
                "subject": "Campaign Update"
            },
            "urgency_level": "medium",
            "tenant_id": "test_tenant",
            "user_id": "test_user"
        })
        
        assert result.success is True
        assert "confirmed" in result.data
        assert "confirmation_timestamp" in result.data
        assert result.data["tenant_id"] == "test_tenant"
        assert result.data["user_id"] == "test_user"
    
    @pytest.mark.asyncio
    async def test_confirm_action_missing_description(self, confirm_tool):
        """Test confirmation with missing action description."""
        result = await confirm_tool.execute({
            "action_parameters": {"to": "test@example.com"},
            "urgency_level": "medium"
        })
        
        assert result.success is False
        assert "MISSING_FIELD" in result.error_code
    
    @pytest.mark.asyncio
    async def test_confirm_action_sanitization(self, confirm_tool):
        """Test input sanitization in confirm_action."""
        result = await confirm_tool.execute({
            "action_description": "<script>alert('xss')</script>Send email",
            "action_parameters": {
                "to": "test@example.com",
                "subject": "<script>alert('xss')</script>Test"
            },
            "urgency_level": "medium"
        })
        
        assert result.success is True
        # Check that the description is sanitized
        assert "&lt;script&gt;" in result.data["action_description"]
        # Check that parameters are sanitized
        assert "&lt;script&gt;" in result.data["action_parameters"]["subject"]
    
    @pytest.mark.asyncio
    async def test_confirm_action_urgency_levels(self, confirm_tool):
        """Test different urgency levels."""
        # Test high urgency (should be approved)
        result_high = await confirm_tool.execute({
            "action_description": "High priority action",
            "urgency_level": "high"
        })
        assert result_high.success is True
        assert result_high.data["confirmed"] is True
        
        # Test medium urgency (should be approved)
        result_medium = await confirm_tool.execute({
            "action_description": "Medium priority action",
            "urgency_level": "medium"
        })
        assert result_medium.success is True
        assert result_medium.data["confirmed"] is True
        
        # Test low urgency (should be rejected in simulation)
        result_low = await confirm_tool.execute({
            "action_description": "Low priority action",
            "urgency_level": "low"
        })
        assert result_low.success is True
        assert result_low.data["confirmed"] is False
    
    @pytest.mark.asyncio
    async def test_confirm_action_invalid_urgency(self, confirm_tool):
        """Test with invalid urgency level."""
        result = await confirm_tool.execute({
            "action_description": "Test action",
            "urgency_level": "invalid"
        })
        
        assert result.success is True
        # Should default to medium urgency
        assert result.data["urgency_level"] == "medium"


class TestMCPToolIntegration:
    """Test integration between MCP tools and confirm_action."""
    
    @pytest.mark.asyncio
    async def test_slack_send_message_with_confirmation(self):
        """Test Slack message sending with confirmation workflow."""
        slack_tool = MCPSlackTool()
        confirm_tool = ConfirmActionTool()
        
        with patch('src.tools.mcp.mcp_slack.TenantSecretsManager') as mock_secrets:
            mock_instance = AsyncMock()
            mock_instance.get_secret.return_value = "xoxb-test-token"
            mock_secrets.return_value = mock_instance
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "ok": True,
                    "message": {"text": "Test message"},
                    "channel": "C012AB3CD",
                    "ts": "1512085950.000216"
                }
                mock_response.raise_for_status.return_value = None
                
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                
                # Step 1: Get confirmation
                confirm_result = await confirm_tool.execute({
                    "action_description": "Send message to #general channel",
                    "action_parameters": {
                        "channel_id": "C012AB3CD",
                        "message": "Hello team!"
                    },
                    "urgency_level": "medium",
                    "tenant_id": "test_tenant",
                    "user_id": "test_user"
                })
                
                assert confirm_result.success is True
                assert confirm_result.data["confirmed"] is True
                
                # Step 2: Execute the action if confirmed
                if confirm_result.data["confirmed"]:
                    slack_result = await slack_tool.execute({
                        "tenant_id": "test_tenant",
                        "action": "send_message",
                        "channel_id": "C012AB3CD",
                        "message": "Hello team!"
                    })
                    
                    assert slack_result.success is True
                    assert "message" in slack_result.data
    
    @pytest.mark.asyncio
    async def test_email_send_with_confirmation(self):
        """Test email sending with confirmation workflow."""
        email_tool = MCPEmailTool()
        confirm_tool = ConfirmActionTool()
        
        with patch('src.tools.mcp.mcp_email.TenantSecretsManager') as mock_secrets:
            mock_instance = AsyncMock()
            mock_instance.get_secret.return_value = "test-api-key"
            mock_secrets.return_value = mock_instance
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"id": "test-message-id"}
                mock_response.raise_for_status.return_value = None
                
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                
                # Step 1: Get confirmation
                confirm_result = await confirm_tool.execute({
                    "action_description": "Send email to marketing team",
                    "action_parameters": {
                        "to": "marketing@company.com",
                        "subject": "Campaign Update",
                        "body": "Here's the latest update..."
                    },
                    "urgency_level": "high",
                    "tenant_id": "test_tenant",
                    "user_id": "test_user"
                })
                
                assert confirm_result.success is True
                assert confirm_result.data["confirmed"] is True
                
                # Step 2: Execute the action if confirmed
                if confirm_result.data["confirmed"]:
                    email_result = await email_tool.execute({
                        "tenant_id": "test_tenant",
                        "action": "send_email",
                        "to": "marketing@company.com",
                        "subject": "Campaign Update",
                        "body": "Here's the latest update..."
                    })
                    
                    assert email_result.success is True
                    assert "message_id" in email_result.data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
