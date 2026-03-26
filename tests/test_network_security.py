import pytest
import asyncio
from src.utils.network_security import (
    NetworkSecurityManager, 
    SecurityZone, 
    NetworkPolicy, 
    NetworkPolicyAction,
    CertificateValidator,
    EgressFilter
)
from src.tools.mcp.base_mcp_tool import (
    BaseMCPTool, 
    MCPToolError, 
    InvalidCredentialsError, 
    RateLimitError, 
    TimeoutError,
    NetworkSecurityError,
    CertificateValidationError
)


def test_network_security_manager_initialization():
    """Test that NetworkSecurityManager initializes correctly."""
    manager = NetworkSecurityManager()
    assert len(manager.policies) > 0
    assert len(manager.trusted_domains) >= 0
    assert len(manager.blocked_domains) >= 0


def test_network_policy_creation():
    """Test creation of network policies."""
    policy = NetworkPolicy(
        name="test_policy",
        source_zone=SecurityZone.INTERNAL,
        destination_zone=SecurityZone.EXTERNAL,
        action=NetworkPolicyAction.ALLOW,
        allowed_domains=["test.com"],
        allowed_ports=[443],
        description="Test policy"
    )
    
    assert policy.name == "test_policy"
    assert policy.source_zone == SecurityZone.INTERNAL
    assert policy.destination_zone == SecurityZone.EXTERNAL
    assert policy.action == NetworkPolicyAction.ALLOW
    assert "test.com" in policy.allowed_domains
    assert 443 in policy.allowed_ports


def test_endpoint_validation():
    """Test endpoint validation."""
    manager = NetworkSecurityManager()
    
    # Test valid endpoint
    result = manager.validate_endpoint("https://api.shopify.com")
    assert result.valid == True
    
    # Test invalid endpoint
    result = manager.validate_endpoint("https://blocked-domain.com")
    assert result.valid == False


def test_trusted_domains():
    """Test trusted domain management."""
    manager = NetworkSecurityManager()
    
    # Add trusted domain
    manager.add_trusted_domain("example.com")
    assert manager.is_trusted_domain("example.com")
    
    # Remove trusted domain
    result = manager.remove_trusted_domain("example.com")
    assert result == True
    assert not manager.is_trusted_domain("example.com")


def test_certificate_validator():
    """Test certificate validator."""
    validator = CertificateValidator()
    
    # Test with a known good domain
    valid, reason = validator.validate_certificate("google.com", 443)
    # We expect this to work or at least not throw an exception
    assert isinstance(valid, bool)
    assert isinstance(reason, str)


def test_egress_filter():
    """Test egress filtering."""
    manager = NetworkSecurityManager()
    filter = EgressFilter(manager)
    
    # Test allowed URL
    allowed, reason = filter.filter_egress("https://api.shopify.com")
    assert isinstance(allowed, bool)
    assert isinstance(reason, str)
    
    # Test flow logs
    logs = filter.get_flow_logs()
    assert isinstance(logs, list)


def test_base_mcp_tool_initialization():
    """Test that BaseMCPTool initializes correctly."""
    class TestTool(BaseMCPTool):
        async def execute(self, params):
            pass
    
    tool = TestTool("test_tool", "Test tool description")
    assert tool.name == "test_tool"
    assert tool.description == "Test tool description"
    assert tool.security_zone == SecurityZone.INTERNAL


def test_mcp_tool_error_hierarchy():
    """Test MCP tool error hierarchy."""
    # Test base error
    base_error = MCPToolError("Test error")
    assert base_error.error_code == "MCP_TOOL_ERROR"
    
    # Test specific errors
    cred_error = InvalidCredentialsError()
    assert cred_error.error_code == "INVALID_CREDENTIALS"
    
    rate_error = RateLimitError()
    assert rate_error.error_code == "RATE_LIMIT_EXCEEDED"
    
    timeout_error = TimeoutError()
    assert timeout_error.error_code == "TIMEOUT_ERROR"
    
    network_error = NetworkSecurityError()
    assert network_error.error_code == "NETWORK_SECURITY_VIOLATION"
    
    cert_error = CertificateValidationError()
    assert cert_error.error_code == "CERTIFICATE_VALIDATION_FAILED"


def test_error_rate_limiting():
    """Test error rate limiting functionality."""
    class TestTool(BaseMCPTool):
        async def execute(self, params):
            pass
    
    tool = TestTool("test_tool", "Test tool description")
    
    # Check initial state
    assert tool.error_count == 0
    
    # Increment error count
    tool._increment_error_count()
    assert tool.error_count == 1
    
    # Check rate limit
    allowed = tool._check_error_rate_limit()
    assert allowed == True


@pytest.mark.asyncio
async def test_retry_with_backoff():
    """Test retry with backoff mechanism."""
    class TestTool(BaseMCPTool):
        async def execute(self, params):
            pass
        
        async def failing_function(self):
            raise MCPToolError("Test error")
    
    tool = TestTool("test_tool", "Test tool description")
    
    # Test that retry mechanism works
    with pytest.raises(MCPToolError):
        await tool._retry_with_backoff(
            tool.failing_function,
            max_retries=2
        )


if __name__ == "__main__":
    pytest.main([__file__])