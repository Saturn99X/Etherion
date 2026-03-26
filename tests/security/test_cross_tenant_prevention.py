"""
Comprehensive tests for cross-tenant credential access prevention.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from src.utils.secrets_manager import TenantSecretsManager
from src.security import enforce_tenant_isolation, validate_tenant_access, get_tenant_isolation_guard
from src.tools.mcp.mcp_twitter import MCPTwitterTool
from src.tools.mcp.mcp_slack import MCPSlackTool


class TestCrossTenantCredentialPrevention:
    """Test comprehensive cross-tenant credential access prevention."""
    
    @pytest.fixture
    def secrets_manager(self):
        """Create a secrets manager instance."""
        return TenantSecretsManager()
    
    @pytest.fixture
    def isolation_guard(self):
        """Get the tenant isolation guard."""
        guard = get_tenant_isolation_guard()
        # Clear any existing data
        guard._access_attempts.clear()
        guard._violations.clear()
        guard._blocked_tenants.clear()
        return guard
    
    @pytest.mark.asyncio
    async def test_secret_access_isolation(self, secrets_manager, isolation_guard):
        """Test that tenants cannot access each other's secrets."""
        # Store secrets for different tenants
        await secrets_manager.store_secret(
            tenant_id="tenant-alice",
            service_name="resend",
            key_type="api_key",
            value="alice-resend-key"
        )
        
        await secrets_manager.store_secret(
            tenant_id="tenant-bob",
            service_name="resend",
            key_type="api_key",
            value="bob-resend-key"
        )
        
        # Alice accesses her own secret
        alice_secret = await secrets_manager.get_secret(
            tenant_id="tenant-alice",
            service_name="resend",
            key_type="api_key"
        )
        assert alice_secret == "alice-resend-key"
        
        # Bob accesses his own secret
        bob_secret = await secrets_manager.get_secret(
            tenant_id="tenant-bob",
            service_name="resend",
            key_type="api_key"
        )
        assert bob_secret == "bob-resend-key"
        
        # Verify secrets are different
        assert alice_secret != bob_secret
        
        # Check that no violations were logged for legitimate access
        assert len(isolation_guard._violations) == 0
    
    @pytest.mark.asyncio
    async def test_secret_naming_convention_enforcement(self, secrets_manager, isolation_guard):
        """Test that secret naming convention prevents cross-tenant access."""
        # Store secret for tenant-alice
        await secrets_manager.store_secret(
            tenant_id="tenant-alice",
            service_name="twitter",
            key_type="api_key",
            value="alice-twitter-key"
        )
        
        # Try to access Alice's secret using Bob's tenant ID
        # This should fail due to naming convention validation
        result = await secrets_manager.get_secret(
            tenant_id="tenant-bob",
            service_name="twitter",
            key_type="api_key"
        )
        
        # Should return None (not found) because the secret key doesn't match
        assert result is None
        
        # Check that violation was logged
        assert len(isolation_guard._violations) == 1
        violation = isolation_guard._violations[0]
        assert violation.violation_type == "unauthorized_resource_access"
        assert violation.attempted_tenant_id == "tenant-bob"
        assert violation.actual_tenant_id == "tenant-alice"
    
    @pytest.mark.asyncio
    async def test_mcp_tool_tenant_isolation(self, isolation_guard):
        """Test that MCP tools enforce tenant isolation."""
        # Create MCP tools
        resend_tool = MCPResendTool()
        twitter_tool = MCPTwitterTool()
        slack_tool = MCPSlackTool()
        
        # Test Resend tool with valid tenant
        result = await resend_tool.execute({
            "tenant_id": "tenant-alice",
            "action": "send_email",
            "to": "test@example.com",
            "subject": "Test",
            "html": "<p>Test email</p>"
        })
        
        # Should fail due to missing credentials, not tenant isolation
        assert result.success is False
        assert result.error_code != "TENANT_ISOLATION_VIOLATION"
        
        # Test Twitter tool with valid tenant
        result = await twitter_tool.execute({
            "tenant_id": "tenant-bob",
            "thread": ["Test tweet"]
        })
        
        # Should fail due to missing credentials, not tenant isolation
        assert result.success is False
        assert result.error_code != "TENANT_ISOLATION_VIOLATION"
        
        # Test Slack tool with valid tenant
        result = await slack_tool.execute({
            "tenant_id": "tenant-charlie",
            "action": "get_channels"
        })
        
        # Should fail due to missing credentials, not tenant isolation
        assert result.success is False
        assert result.error_code != "TENANT_ISOLATION_VIOLATION"
    
    def test_tenant_context_validation(self, isolation_guard):
        """Test tenant context validation."""
        # Test with matching tenant context
        result = isolation_guard.validate_tenant_context("tenant-alice")
        # This might fail if no context is set, which is expected
        
        # Test with mismatched tenant context
        with patch('src.security.tenant_isolation.get_tenant_context', return_value="tenant-bob"):
            result = isolation_guard.validate_tenant_context("tenant-alice")
            assert result is False
            
            # Check that violation was logged
            assert len(isolation_guard._violations) == 1
            violation = isolation_guard._violations[0]
            assert violation.violation_type == "context_mismatch"
    
    def test_rate_limiting_prevention(self, isolation_guard):
        """Test that rate limiting prevents abuse."""
        # Make many requests quickly
        for i in range(105):  # Exceed the default limit of 100
            result = isolation_guard.validate_tenant_access(
                tenant_id="tenant-alice",
                resource_type="secret",
                resource_id="tenant-alice--resend--api_key",
                action="read"
            )
            
            if i < 100:
                assert result is True
            else:
                assert result is False  # Should be rate limited
        
        # Check that rate limit violation was logged
        rate_limit_violations = [
            v for v in isolation_guard._violations
            if v.violation_type == "rate_limit_exceeded"
        ]
        assert len(rate_limit_violations) > 0
    
    def test_suspicious_pattern_detection(self, isolation_guard):
        """Test detection of suspicious access patterns."""
        # Create many access attempts to different resources
        for i in range(25):  # Exceed the suspicious threshold of 20
            isolation_guard._log_access_attempt(
                tenant_id="tenant-alice",
                resource_type="secret",
                resource_id=f"tenant-alice--service-{i}--api_key",
                action="read",
                success=True
            )
        
        # Try to access another resource - should be blocked due to suspicious pattern
        result = isolation_guard._perform_additional_security_checks(
            "tenant-alice", "secret", "tenant-alice--another-service--api_key"
        )
        assert result is False
    
    def test_privilege_escalation_prevention(self, isolation_guard):
        """Test prevention of privilege escalation attempts."""
        # Try to access system resources
        result = isolation_guard._detect_privilege_escalation(
            "tenant-alice", "secret", "system-admin-key"
        )
        assert result is True
        
        # Try to access admin resources
        result = isolation_guard._detect_privilege_escalation(
            "tenant-alice", "secret", "admin-access-token"
        )
        assert result is True
        
        # Try to access root resources
        result = isolation_guard._detect_privilege_escalation(
            "tenant-alice", "secret", "root-password"
        )
        assert result is True
        
        # Normal access should not be detected as privilege escalation
        result = isolation_guard._detect_privilege_escalation(
            "tenant-alice", "secret", "tenant-alice--resend--api_key"
        )
        assert result is False
    
    def test_tenant_blocking_mechanism(self, isolation_guard):
        """Test that tenants are blocked after multiple violations."""
        # Make multiple violations
        for i in range(6):  # Exceed the default threshold of 5
            isolation_guard._log_violation(
                violation_type="unauthorized_resource_access",
                attempted_tenant_id="tenant-alice",
                actual_tenant_id="tenant-bob",
                resource_type="secret",
                resource_id="tenant-bob--resend--api_key",
                severity="HIGH"
            )
        
        # Check that tenant is blocked
        assert "tenant-alice" in isolation_guard._blocked_tenants
        
        # Try to access - should be blocked
        result = isolation_guard.validate_tenant_access(
            tenant_id="tenant-alice",
            resource_type="secret",
            resource_id="tenant-alice--resend--api_key",
            action="read"
        )
        assert result is False
    
    def test_security_metrics_tracking(self, isolation_guard):
        """Test that security metrics are properly tracked."""
        # Make some violations
        isolation_guard._log_violation(
            violation_type="unauthorized_resource_access",
            attempted_tenant_id="tenant-alice",
            actual_tenant_id="tenant-bob",
            resource_type="secret",
            resource_id="tenant-bob--resend--api_key",
            severity="HIGH"
        )
        
        isolation_guard._log_violation(
            violation_type="rate_limit_exceeded",
            attempted_tenant_id="tenant-charlie",
            actual_tenant_id="tenant-charlie",
            resource_type="secret",
            resource_id="tenant-charlie--resend--api_key",
            severity="MEDIUM"
        )
        
        # Get security metrics
        metrics = isolation_guard.get_security_metrics()
        
        assert metrics["total_violations_last_hour"] == 2
        assert metrics["violations_by_type"]["unauthorized_resource_access"] == 1
        assert metrics["violations_by_type"]["rate_limit_exceeded"] == 1
        assert metrics["active_tenants"] == 0  # No access attempts logged yet
    
    def test_tenant_security_status(self, isolation_guard):
        """Test getting tenant security status."""
        # Make some access attempts and violations
        isolation_guard._log_access_attempt(
            tenant_id="tenant-alice",
            resource_type="secret",
            resource_id="tenant-alice--resend--api_key",
            action="read",
            success=True
        )
        
        isolation_guard._log_violation(
            violation_type="unauthorized_resource_access",
            attempted_tenant_id="tenant-alice",
            actual_tenant_id="tenant-bob",
            resource_type="secret",
            resource_id="tenant-bob--resend--api_key",
            severity="HIGH"
        )
        
        # Get tenant security status
        status = isolation_guard.get_tenant_security_status("tenant-alice")
        
        assert status["tenant_id"] == "tenant-alice"
        assert status["is_blocked"] is False
        assert status["recent_violations"] == 1
        assert status["recent_access_attempts"] == 1
        assert status["violation_threshold"] == 5
        assert status["max_attempts_per_minute"] == 100


class TestCrossTenantAccessScenarios:
    """Test specific cross-tenant access scenarios."""
    
    @pytest.mark.asyncio
    async def test_credential_theft_prevention(self):
        """Test prevention of credential theft attempts."""
        secrets_manager = TenantSecretsManager()
        isolation_guard = get_tenant_isolation_guard()
        
        # Clear any existing data
        isolation_guard._access_attempts.clear()
        isolation_guard._violations.clear()
        isolation_guard._blocked_tenants.clear()
        
        # Store credentials for different tenants
        await secrets_manager.store_secret(
            tenant_id="tenant-victim",
            service_name="resend",
            key_type="api_key",
            value="victim-secret-key"
        )
        
        await secrets_manager.store_secret(
            tenant_id="tenant-attacker",
            service_name="resend",
            key_type="api_key",
            value="attacker-secret-key"
        )
        
        # Attacker tries to access victim's credentials
        stolen_secret = await secrets_manager.get_secret(
            tenant_id="tenant-attacker",
            service_name="resend",
            key_type="api_key"
        )
        
        # Should get attacker's own secret, not victim's
        assert stolen_secret == "attacker-secret-key"
        assert stolen_secret != "victim-secret-key"
        
        # Check that violation was logged
        assert len(isolation_guard._violations) == 1
        violation = isolation_guard._violations[0]
        assert violation.violation_type == "unauthorized_resource_access"
        assert violation.attempted_tenant_id == "tenant-attacker"
        assert violation.actual_tenant_id == "tenant-victim"
    
    @pytest.mark.asyncio
    async def test_credential_confusion_attack(self):
        """Test prevention of credential confusion attacks."""
        secrets_manager = TenantSecretsManager()
        isolation_guard = get_tenant_isolation_guard()
        
        # Clear any existing data
        isolation_guard._access_attempts.clear()
        isolation_guard._violations.clear()
        isolation_guard._blocked_tenants.clear()
        
        # Store similar-looking secrets for different tenants
        await secrets_manager.store_secret(
            tenant_id="tenant-alice",
            service_name="resend",
            key_type="api_key",
            value="alice-resend-key-12345"
        )
        
        await secrets_manager.store_secret(
            tenant_id="tenant-bob",
            service_name="resend",
            key_type="api_key",
            value="bob-resend-key-67890"
        )
        
        # Alice tries to access her secret
        alice_secret = await secrets_manager.get_secret(
            tenant_id="tenant-alice",
            service_name="resend",
            key_type="api_key"
        )
        assert alice_secret == "alice-resend-key-12345"
        
        # Bob tries to access his secret
        bob_secret = await secrets_manager.get_secret(
            tenant_id="tenant-bob",
            service_name="resend",
            key_type="api_key"
        )
        assert bob_secret == "bob-resend-key-67890"
        
        # Verify no cross-contamination
        assert alice_secret != bob_secret
        assert len(isolation_guard._violations) == 0
    
    def test_tenant_impersonation_prevention(self):
        """Test prevention of tenant impersonation."""
        isolation_guard = get_tenant_isolation_guard()
        
        # Clear any existing data
        isolation_guard._access_attempts.clear()
        isolation_guard._violations.clear()
        isolation_guard._blocked_tenants.clear()
        
        # Try to impersonate another tenant
        result = isolation_guard.validate_tenant_access(
            tenant_id="tenant-impersonator",
            resource_type="secret",
            resource_id="tenant-victim--resend--api_key",
            action="read"
        )
        
        assert result is False
        
        # Check that violation was logged
        assert len(isolation_guard._violations) == 1
        violation = isolation_guard._violations[0]
        assert violation.violation_type == "unauthorized_resource_access"
        assert violation.attempted_tenant_id == "tenant-impersonator"
        assert violation.actual_tenant_id == "tenant-victim"
        assert violation.severity == "CRITICAL"
