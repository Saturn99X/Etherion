"""
Tests for tenant isolation and cross-tenant access prevention.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from src.security.tenant_isolation import (
    TenantIsolationGuard,
    TenantAccessAttempt,
    TenantIsolationViolation,
    get_tenant_isolation_guard,
    validate_tenant_access,
    enforce_tenant_isolation,
    set_request_context,
    clear_request_context
)


class TestTenantIsolationGuard:
    """Test the TenantIsolationGuard class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.guard = TenantIsolationGuard()
        # Clear any existing data
        self.guard._access_attempts.clear()
        self.guard._violations.clear()
        self.guard._blocked_tenants.clear()
    
    def test_validate_secret_ownership(self):
        """Test secret ownership validation."""
        # Valid secret ownership
        assert self.guard._validate_secret_ownership("tenant-123", "tenant-123--resend--api_key")
        assert self.guard._validate_secret_ownership("tenant-456", "tenant-456--twitter--access_token")
        
        # Invalid secret ownership
        assert not self.guard._validate_secret_ownership("tenant-123", "tenant-456--resend--api_key")
        assert not self.guard._validate_secret_ownership("tenant-123", "other-tenant--resend--api_key")
        assert not self.guard._validate_secret_ownership("tenant-123", "invalid-secret-format")
    
    def test_validate_database_ownership(self):
        """Test database resource ownership validation."""
        # Valid database ownership
        assert self.guard._validate_database_ownership("tenant-123", "tenant-123-projects")
        assert self.guard._validate_database_ownership("tenant-456", "tenant-456-jobs")
        
        # Invalid database ownership
        assert not self.guard._validate_database_ownership("tenant-123", "tenant-456-projects")
        assert not self.guard._validate_database_ownership("tenant-123", "other-table")
    
    def test_validate_api_ownership(self):
        """Test API resource ownership validation."""
        # Valid API ownership
        assert self.guard._validate_api_ownership("tenant-123", "tenant-123-api-endpoint")
        assert self.guard._validate_api_ownership("tenant-456", "tenant-456-webhook")
        
        # Invalid API ownership
        assert not self.guard._validate_api_ownership("tenant-123", "tenant-456-api-endpoint")
        assert not self.guard._validate_api_ownership("tenant-123", "public-api")
    
    def test_validate_tenant_access_success(self):
        """Test successful tenant access validation."""
        # Valid access
        result = self.guard.validate_tenant_access(
            tenant_id="tenant-123",
            resource_type="secret",
            resource_id="tenant-123--resend--api_key",
            action="read"
        )
        assert result is True
    
    def test_validate_tenant_access_unauthorized(self):
        """Test unauthorized tenant access validation."""
        # Unauthorized access - wrong tenant
        result = self.guard.validate_tenant_access(
            tenant_id="tenant-123",
            resource_type="secret",
            resource_id="tenant-456--resend--api_key",
            action="read"
        )
        assert result is False
        
        # Check that violation was logged
        assert len(self.guard._violations) == 1
        violation = self.guard._violations[0]
        assert violation.violation_type == "unauthorized_resource_access"
        assert violation.attempted_tenant_id == "tenant-123"
        assert violation.actual_tenant_id == "tenant-456"
    
    def test_validate_tenant_access_blocked_tenant(self):
        """Test access validation for blocked tenant."""
        # Block a tenant
        from datetime import datetime, timedelta
        self.guard._blocked_tenants["tenant-123"] = datetime.utcnow() + timedelta(minutes=15)
        
        # Try to access
        result = self.guard.validate_tenant_access(
            tenant_id="tenant-123",
            resource_type="secret",
            resource_id="tenant-123--resend--api_key",
            action="read"
        )
        assert result is False
        
        # Check that violation was logged
        assert len(self.guard._violations) == 1
        violation = self.guard._violations[0]
        assert violation.violation_type == "blocked_tenant_access"
    
    def test_rate_limit_enforcement(self):
        """Test rate limit enforcement."""
        # Make many requests quickly
        for i in range(105):  # Exceed the default limit of 100
            result = self.guard.validate_tenant_access(
                tenant_id="tenant-123",
                resource_type="secret",
                resource_id="tenant-123--resend--api_key",
                action="read"
            )
            if i < 100:
                assert result is True
            else:
                assert result is False  # Should be rate limited
    
    def test_violation_threshold_blocking(self):
        """Test that tenants are blocked after exceeding violation threshold."""
        # Make multiple violations
        for i in range(6):  # Exceed the default threshold of 5
            self.guard._log_violation(
                violation_type="unauthorized_resource_access",
                attempted_tenant_id="tenant-123",
                actual_tenant_id="tenant-456",
                resource_type="secret",
                resource_id="tenant-456--resend--api_key",
                severity="HIGH"
            )
        
        # Check that tenant is blocked
        assert "tenant-123" in self.guard._blocked_tenants
    
    def test_detect_suspicious_patterns(self):
        """Test detection of suspicious access patterns."""
        # Create many access attempts to different resources
        for i in range(25):  # Exceed the suspicious threshold of 20
            self.guard._log_access_attempt(
                tenant_id="tenant-123",
                resource_type="secret",
                resource_id=f"tenant-123--service-{i}--api_key",
                action="read",
                success=True
            )
        
        # Try to access another resource - should be blocked due to suspicious pattern
        result = self.guard._detect_suspicious_patterns(
            "tenant-123", "secret", "tenant-123--another-service--api_key"
        )
        assert result is True
    
    def test_detect_privilege_escalation(self):
        """Test detection of privilege escalation attempts."""
        # Try to access system resources
        result = self.guard._detect_privilege_escalation(
            "tenant-123", "secret", "system-admin-key"
        )
        assert result is True
        
        # Try to access admin resources
        result = self.guard._detect_privilege_escalation(
            "tenant-123", "secret", "admin-access-token"
        )
        assert result is True
        
        # Normal access should not be detected as privilege escalation
        result = self.guard._detect_privilege_escalation(
            "tenant-123", "secret", "tenant-123--resend--api_key"
        )
        assert result is False
    
    def test_get_tenant_security_status(self):
        """Test getting tenant security status."""
        # Make some access attempts and violations
        self.guard._log_access_attempt(
            tenant_id="tenant-123",
            resource_type="secret",
            resource_id="tenant-123--resend--api_key",
            action="read",
            success=True
        )
        
        self.guard._log_violation(
            violation_type="unauthorized_resource_access",
            attempted_tenant_id="tenant-123",
            actual_tenant_id="tenant-456",
            resource_type="secret",
            resource_id="tenant-456--resend--api_key",
            severity="HIGH"
        )
        
        status = self.guard.get_tenant_security_status("tenant-123")
        
        assert status["tenant_id"] == "tenant-123"
        assert status["is_blocked"] is False
        assert status["recent_violations"] == 1
        assert status["recent_access_attempts"] == 1
    
    def test_get_security_metrics(self):
        """Test getting overall security metrics."""
        # Make some violations
        self.guard._log_violation(
            violation_type="unauthorized_resource_access",
            attempted_tenant_id="tenant-123",
            actual_tenant_id="tenant-456",
            resource_type="secret",
            resource_id="tenant-456--resend--api_key",
            severity="HIGH"
        )
        
        self.guard._log_violation(
            violation_type="rate_limit_exceeded",
            attempted_tenant_id="tenant-789",
            actual_tenant_id="tenant-789",
            resource_type="secret",
            resource_id="tenant-789--resend--api_key",
            severity="MEDIUM"
        )
        
        metrics = self.guard.get_security_metrics()
        
        assert metrics["total_violations_last_hour"] == 2
        assert metrics["violations_by_type"]["unauthorized_resource_access"] == 1
        assert metrics["violations_by_type"]["rate_limit_exceeded"] == 1
        assert metrics["active_tenants"] == 0  # No access attempts logged yet


class TestTenantIsolationFunctions:
    """Test the module-level functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Clear any existing data
        guard = get_tenant_isolation_guard()
        guard._access_attempts.clear()
        guard._violations.clear()
        guard._blocked_tenants.clear()
    
    def test_validate_tenant_access_function(self):
        """Test the validate_tenant_access function."""
        # Valid access
        result = validate_tenant_access(
            tenant_id="tenant-123",
            resource_type="secret",
            resource_id="tenant-123--resend--api_key",
            action="read"
        )
        assert result is True
        
        # Invalid access
        result = validate_tenant_access(
            tenant_id="tenant-123",
            resource_type="secret",
            resource_id="tenant-456--resend--api_key",
            action="read"
        )
        assert result is False
    
    def test_enforce_tenant_isolation_function(self):
        """Test the enforce_tenant_isolation function."""
        # Valid access
        result = enforce_tenant_isolation(
            tenant_id="tenant-123",
            resource_type="secret",
            resource_id="tenant-123--resend--api_key",
            action="read"
        )
        assert result is True
        
        # Invalid access
        result = enforce_tenant_isolation(
            tenant_id="tenant-123",
            resource_type="secret",
            resource_id="tenant-456--resend--api_key",
            action="read"
        )
        assert result is False
    
    def test_set_and_clear_request_context(self):
        """Test setting and clearing request context."""
        # Set context
        set_request_context("tenant-123", "req-456")
        
        # Clear context
        clear_request_context()
        
        # Context should be cleared
        from src.security.tenant_isolation import _request_tenant_context, _request_id
        assert _request_tenant_context.get() is None
        assert _request_id.get() is None


class TestTenantIsolationIntegration:
    """Integration tests for tenant isolation."""
    
    @pytest.mark.asyncio
    async def test_secrets_manager_integration(self):
        """Test integration with secrets manager."""
        from src.utils.secrets_manager import TenantSecretsManager
        
        # Create secrets manager
        secrets_manager = TenantSecretsManager()
        
        # Store secret for tenant A
        await secrets_manager.store_secret(
            tenant_id="tenant-a",
            service_name="resend",
            key_type="api_key",
            value="secret-a"
        )
        
        # Store secret for tenant B
        await secrets_manager.store_secret(
            tenant_id="tenant-b",
            service_name="resend",
            key_type="api_key",
            value="secret-b"
        )
        
        # Tenant A should access their own secret
        secret_a = await secrets_manager.get_secret(
            tenant_id="tenant-a",
            service_name="resend",
            key_type="api_key"
        )
        assert secret_a == "secret-a"
        
        # Tenant B should access their own secret
        secret_b = await secrets_manager.get_secret(
            tenant_id="tenant-b",
            service_name="resend",
            key_type="api_key"
        )
        assert secret_b == "secret-b"
        
        # Verify secrets are different
        assert secret_a != secret_b
    
    @pytest.mark.asyncio
    async def test_mcp_tool_integration(self):
        """Test integration with MCP tools."""
        
    
    def test_cross_tenant_access_prevention(self):
        """Test that cross-tenant access is prevented."""
        guard = get_tenant_isolation_guard()
        
        # Clear any existing data
        guard._access_attempts.clear()
        guard._violations.clear()
        guard._blocked_tenants.clear()
        
        # Tenant A tries to access Tenant B's secret
        result = guard.validate_tenant_access(
            tenant_id="tenant-a",
            resource_type="secret",
            resource_id="tenant-b--resend--api_key",
            action="read"
        )
        
        assert result is False
        
        # Check that violation was logged
        assert len(guard._violations) == 1
        violation = guard._violations[0]
        assert violation.violation_type == "unauthorized_resource_access"
        assert violation.attempted_tenant_id == "tenant-a"
        assert violation.actual_tenant_id == "tenant-b"
        assert violation.severity == "CRITICAL"
