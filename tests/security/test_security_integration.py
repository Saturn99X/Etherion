# tests/security/test_security_integration.py
"""
Integration tests for the complete security system.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from src.middleware.security_integration import (
    SecurityManager,
    initialize_security_system,
    secure_request_handler,
    security_manager,
    log_authentication_event,
    log_authorization_event,
    log_security_violation_event
)


class TestSecurityIntegration:
    """Test complete security system integration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = FastAPI()
        
        @self.app.get("/public")
        async def public_endpoint():
            return {"message": "public"}
        
        @self.app.post("/protected")
        async def protected_endpoint():
            return {"message": "protected"}
        
        @self.app.post("/api/test")
        async def api_endpoint():
            return {"message": "api test"}
        
        # Add security middleware
        self.app.middleware("http")(secure_request_handler)
        
        self.client = TestClient(self.app)
    
    def test_security_manager_initialization(self):
        """Test security manager initialization."""
        manager = SecurityManager()
        
        assert manager.rate_limiting_enabled is True
        assert manager.authorization_enabled is True
        assert manager.audit_logging_enabled is True
        assert manager.csrf_protection_enabled is True
        assert manager.security_headers_enabled is True
    
    def test_security_manager_configuration(self):
        """Test security manager configuration."""
        manager = SecurityManager()
        
        manager.configure_security(
            rate_limiting=False,
            authorization=False,
            audit_logging=False,
            csrf_protection=False,
            security_headers=False
        )
        
        assert manager.rate_limiting_enabled is False
        assert manager.authorization_enabled is False
        assert manager.audit_logging_enabled is False
        assert manager.csrf_protection_enabled is False
        assert manager.security_headers_enabled is False
    
    def test_security_system_initialization(self):
        """Test security system initialization."""
        secret_key = "test-secret-key"
        
        # Should not raise an exception
        initialize_security_system(secret_key)
        
        # Verify CSRF protection is initialized
        from src.middleware.csrf_protection import get_csrf_protection
        csrf_protection = get_csrf_protection()
        assert csrf_protection is not None
    
    def test_security_headers_present(self):
        """Test that security headers are present on all responses."""
        response = self.client.get("/public")
        
        assert response.status_code == 200
        
        # Check for key security headers
        expected_headers = [
            "content-security-policy",
            "x-frame-options",
            "x-content-type-options",
            "x-xss-protection",
            "referrer-policy",
            "permissions-policy"
        ]
        
        for header in expected_headers:
            assert header in response.headers
            assert response.headers[header] is not None
            assert len(response.headers[header]) > 0
    
    def test_cors_headers_for_api_endpoints(self):
        """Test that API endpoints get CORS headers."""
        response = self.client.post("/api/test")
        
        assert response.status_code == 200
        
        # Check for CORS headers
        cors_headers = [
            "access-control-allow-origin",
            "access-control-allow-methods",
            "access-control-allow-headers",
            "access-control-max-age"
        ]
        
        for header in cors_headers:
            assert header in response.headers
    
    @patch('src.middleware.rate_limiter.check_rate_limit')
    async def test_rate_limiting_integration(self, mock_rate_limit):
        """Test rate limiting integration."""
        mock_rate_limit.return_value = True
        
        # Test that rate limiting is applied
        response = self.client.post("/protected")
        
        # Should not be rate limited
        assert response.status_code in [200, 403]  # 403 for CSRF or auth
    
    @patch('src.middleware.csrf_protection.get_csrf_protection')
    async def test_csrf_protection_integration(self, mock_csrf):
        """Test CSRF protection integration."""
        mock_csrf_instance = Mock()
        mock_csrf_instance.validate_csrf_token.return_value = False
        mock_csrf.return_value = mock_csrf_instance
        
        # Test that CSRF protection is applied
        response = self.client.post("/protected")
        
        # Should be blocked by CSRF protection
        assert response.status_code == 403


class TestSecurityLogging:
    """Test security event logging integration."""
    
    @pytest.mark.asyncio
    async def test_log_authentication_event_success(self):
        """Test logging successful authentication events."""
        with patch('src.core.security.audit_logger.log_authentication_success') as mock_log:
            mock_log.return_value = None
            
            await log_authentication_event(
                success=True,
                user_id="test-user",
                tenant_id="test-tenant",
                details={"method": "oauth"}
            )
            
            mock_log.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_log_authentication_event_failure(self):
        """Test logging failed authentication events."""
        with patch('src.core.security.audit_logger.log_authentication_failure') as mock_log:
            mock_log.return_value = None
            
            await log_authentication_event(
                success=False,
                user_id="test-user",
                tenant_id="test-tenant",
                error_message="Invalid credentials"
            )
            
            mock_log.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_log_authorization_event(self):
        """Test logging authorization events."""
        with patch('src.core.security.audit_logger.log_authorization_failure') as mock_log:
            mock_log.return_value = None
            
            await log_authorization_event(
                success=False,
                user_id="test-user",
                tenant_id="test-tenant",
                endpoint="/protected",
                method="POST",
                error_message="Insufficient permissions"
            )
            
            mock_log.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_log_security_violation_event(self):
        """Test logging security violation events."""
        with patch('src.core.security.audit_logger.log_security_violation') as mock_log:
            mock_log.return_value = None
            
            await log_security_violation_event(
                violation_type="sql_injection_attempt",
                user_id="test-user",
                tenant_id="test-tenant",
                details={"input": "'; DROP TABLE users; --"}
            )
            
            mock_log.assert_called_once()


class TestSecurityMiddlewareOrder:
    """Test that security middleware is applied in the correct order."""
    
    def test_security_middleware_order(self):
        """Test that security middleware is applied in the correct order."""
        app = FastAPI()
        
        middleware_order = []
        
        @app.middleware("http")
        async def track_middleware_order(request: Request, call_next):
            middleware_order.append("security")
            response = await call_next(request)
            return response
        
        @app.middleware("http")
        async def other_middleware(request: Request, call_next):
            middleware_order.append("other")
            response = await call_next(request)
            return response
        
        # Add security middleware first
        app.middleware("http")(secure_request_handler)
        
        client = TestClient(app)
        response = client.get("/")
        
        # Security middleware should be applied first
        assert middleware_order[0] == "security"


class TestSecurityErrorHandling:
    """Test security error handling and recovery."""
    
    def test_security_middleware_error_handling(self):
        """Test that security middleware handles errors gracefully."""
        app = FastAPI()
        
        @app.middleware("http")
        async def error_middleware(request: Request, call_next):
            raise Exception("Test error")
        
        # Add security middleware
        app.middleware("http")(secure_request_handler)
        
        client = TestClient(app)
        
        # Should handle errors gracefully
        response = client.get("/")
        assert response.status_code == 500
        
        # Security headers should still be present
        assert "content-security-policy" in response.headers
    
    def test_security_middleware_timeout_handling(self):
        """Test that security middleware handles timeouts gracefully."""
        app = FastAPI()
        
        @app.middleware("http")
        async def timeout_middleware(request: Request, call_next):
            import asyncio
            await asyncio.sleep(10)  # Simulate timeout
            return await call_next(request)
        
        # Add security middleware
        app.middleware("http")(secure_request_handler)
        
        client = TestClient(app)
        
        # Should handle timeouts gracefully
        response = client.get("/", timeout=1)
        assert response.status_code == 500


class TestSecurityPerformance:
    """Test security middleware performance impact."""
    
    def test_security_middleware_performance(self):
        """Test that security middleware doesn't significantly impact performance."""
        app = FastAPI()
        
        @app.get("/performance-test")
        async def performance_test():
            return {"message": "performance test"}
        
        # Add security middleware
        app.middleware("http")(secure_request_handler)
        
        client = TestClient(app)
        
        # Test multiple requests to ensure consistent performance
        import time
        start_time = time.time()
        
        for _ in range(10):
            response = client.get("/performance-test")
            assert response.status_code == 200
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete within reasonable time (less than 5 seconds for 10 requests)
        assert duration < 5.0


class TestSecurityConfiguration:
    """Test security configuration and customization."""
    
    def test_security_configuration_customization(self):
        """Test that security configuration can be customized."""
        manager = SecurityManager()
        
        # Test individual feature configuration
        manager.configure_security(rate_limiting=False)
        assert manager.rate_limiting_enabled is False
        assert manager.authorization_enabled is True  # Should remain unchanged
        
        manager.configure_security(authorization=False)
        assert manager.authorization_enabled is False
        assert manager.audit_logging_enabled is True  # Should remain unchanged
        
        manager.configure_security(audit_logging=False)
        assert manager.audit_logging_enabled is False
        assert manager.csrf_protection_enabled is True  # Should remain unchanged
        
        manager.configure_security(csrf_protection=False)
        assert manager.csrf_protection_enabled is False
        assert manager.security_headers_enabled is True  # Should remain unchanged
        
        manager.configure_security(security_headers=False)
        assert manager.security_headers_enabled is False
    
    def test_security_configuration_reset(self):
        """Test that security configuration can be reset to defaults."""
        manager = SecurityManager()
        
        # Disable all features
        manager.configure_security(
            rate_limiting=False,
            authorization=False,
            audit_logging=False,
            csrf_protection=False,
            security_headers=False
        )
        
        # Reset to defaults
        manager.configure_security()
        
        assert manager.rate_limiting_enabled is True
        assert manager.authorization_enabled is True
        assert manager.audit_logging_enabled is True
        assert manager.csrf_protection_enabled is True
        assert manager.security_headers_enabled is True


class TestSecurityGlobalInstance:
    """Test global security manager instance."""
    
    def test_global_security_manager(self):
        """Test that global security manager instance works correctly."""
        from src.middleware.security_integration import security_manager
        
        assert security_manager is not None
        assert isinstance(security_manager, SecurityManager)
        
        # Test configuration
        original_rate_limiting = security_manager.rate_limiting_enabled
        security_manager.configure_security(rate_limiting=False)
        assert security_manager.rate_limiting_enabled is False
        
        # Reset
        security_manager.configure_security(rate_limiting=original_rate_limiting)
        assert security_manager.rate_limiting_enabled == original_rate_limiting
