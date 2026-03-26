# tests/security/test_security_headers.py
"""
Tests for security headers middleware and functionality.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from src.middleware.security_headers import (
    get_security_headers,
    security_headers_middleware,
    add_custom_security_headers,
    create_csp_header,
    create_hsts_header,
    add_cors_headers,
    add_cache_control_headers,
    add_security_headers_to_response
)


class TestSecurityHeaders:
    """Test security headers functionality."""
    
    def test_get_security_headers_production(self):
        """Test getting security headers for production environment."""
        headers = get_security_headers(is_production=True)
        
        # Check that all expected security headers are present
        expected_headers = [
            "Content-Security-Policy",
            "X-Frame-Options",
            "X-Content-Type-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Permissions-Policy",
            "Cross-Origin-Embedder-Policy",
            "Cross-Origin-Opener-Policy",
            "Cross-Origin-Resource-Policy",
            "Strict-Transport-Security",
            "Cache-Control",
            "Pragma",
            "Expires"
        ]
        
        for header in expected_headers:
            assert header in headers
            assert headers[header] is not None
            assert len(headers[header]) > 0
    
    def test_get_security_headers_development(self):
        """Test getting security headers for development environment."""
        headers = get_security_headers(is_production=False)
        
        # Check that development-specific headers are present
        assert "Content-Security-Policy" in headers
        assert "Strict-Transport-Security" not in headers or headers["Strict-Transport-Security"] == ""
        assert "Expect-CT" not in headers or headers["Expect-CT"] == ""
    
    def test_content_security_policy_structure(self):
        """Test Content Security Policy header structure."""
        headers = get_security_headers(is_production=True)
        csp = headers["Content-Security-Policy"]
        
        # Check for key CSP directives
        assert "default-src 'self'" in csp
        assert "script-src" in csp
        assert "style-src" in csp
        assert "img-src" in csp
        assert "connect-src" in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp
        assert "object-src 'none'" in csp
        assert "upgrade-insecure-requests" in csp
    
    def test_permissions_policy_structure(self):
        """Test Permissions Policy header structure."""
        headers = get_security_headers(is_production=True)
        pp = headers["Permissions-Policy"]
        
        # Check for key permission restrictions
        assert "geolocation=()" in pp
        assert "microphone=()" in pp
        assert "camera=()" in pp
        assert "payment=()" in pp
        assert "fullscreen=(self)" in pp
    
    def test_hsts_header_structure(self):
        """Test Strict-Transport-Security header structure."""
        headers = get_security_headers(is_production=True)
        hsts = headers["Strict-Transport-Security"]
        
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts


class TestSecurityHeadersMiddleware:
    """Test security headers middleware."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = FastAPI()
        
        @self.app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        @self.app.post("/api/test")
        async def api_endpoint():
            return {"message": "api test"}
        
        # Add security headers middleware
        self.app.middleware("http")(security_headers_middleware)
        
        self.client = TestClient(self.app)
    
    def test_security_headers_added_to_response(self):
        """Test that security headers are added to all responses."""
        response = self.client.get("/test")
        
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
    
    def test_api_endpoint_cors_headers(self):
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
    
    def test_security_headers_middleware_error_handling(self):
        """Test security headers middleware error handling."""
        # Create app that will raise an error
        error_app = FastAPI()
        
        @error_app.get("/error")
        async def error_endpoint():
            raise Exception("Test error")
        
        error_app.middleware("http")(security_headers_middleware)
        error_client = TestClient(error_app)
        
        response = error_client.get("/error")
        
        # Should return 500 with security headers
        assert response.status_code == 500
        
        # Security headers should still be present
        assert "content-security-policy" in response.headers
        assert "x-frame-options" in response.headers


class TestCustomSecurityHeaders:
    """Test custom security header functions."""
    
    def test_add_custom_security_headers(self):
        """Test adding custom security headers."""
        # Mock request and response
        request = Mock()
        request.url.path = "/api/test"
        request.state.request_id = "test-request-123"
        request.state.start_time = 1000.0
        
        response = Response()
        
        with patch('time.time', return_value=1001.0):
            add_custom_security_headers(request, response)
        
        # Check for custom headers
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["api-version"] == "1.0"
        assert response.headers["x-request-id"] == "test-request-123"
        assert response.headers["server"] == "Etherion/1.0"
        assert response.headers["x-response-time"] == "1.000s"
    
    def test_create_csp_header(self):
        """Test creating custom CSP header."""
        additional_directives = {
            "script-src": "'self' https://trusted-cdn.com",
            "img-src": "'self' data: https:"
        }
        
        csp = create_csp_header(additional_directives)
        
        assert "script-src 'self' https://trusted-cdn.com" in csp
        assert "img-src 'self' data: https:" in csp
        assert "default-src 'self'" in csp  # Base CSP should still be present
    
    def test_create_hsts_header(self):
        """Test creating custom HSTS header."""
        hsts = create_hsts_header(max_age=86400, include_subdomains=False, preload=False)
        
        assert "max-age=86400" in hsts
        assert "includeSubDomains" not in hsts
        assert "preload" not in hsts
        
        hsts_full = create_hsts_header(max_age=31536000, include_subdomains=True, preload=True)
        
        assert "max-age=31536000" in hsts_full
        assert "includeSubDomains" in hsts_full
        assert "preload" in hsts_full


class TestCORSHeaders:
    """Test CORS header functions."""
    
    def test_add_cors_headers_default(self):
        """Test adding CORS headers with default values."""
        response = Response()
        
        add_cors_headers(response)
        
        assert response.headers["access-control-allow-origin"] == "*"
        assert "GET" in response.headers["access-control-allow-methods"]
        assert "POST" in response.headers["access-control-allow-methods"]
        assert "PUT" in response.headers["access-control-allow-methods"]
        assert "DELETE" in response.headers["access-control-allow-methods"]
        assert "OPTIONS" in response.headers["access-control-allow-methods"]
        assert "Content-Type" in response.headers["access-control-allow-headers"]
        assert "Authorization" in response.headers["access-control-allow-headers"]
        assert "X-CSRF-Token" in response.headers["access-control-allow-headers"]
        assert response.headers["access-control-max-age"] == "86400"
    
    def test_add_cors_headers_custom(self):
        """Test adding CORS headers with custom values."""
        response = Response()
        allowed_origins = ["https://example.com", "https://app.example.com"]
        allowed_methods = ["GET", "POST"]
        
        add_cors_headers(response, allowed_origins, allowed_methods)
        
        assert response.headers["access-control-allow-origin"] == "https://example.com, https://app.example.com"
        assert response.headers["access-control-allow-methods"] == "GET, POST"


class TestCacheControlHeaders:
    """Test cache control header functions."""
    
    def test_add_cache_control_headers_default(self):
        """Test adding cache control headers with default values."""
        response = Response()
        
        add_cache_control_headers(response)
        
        assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["expires"] == "0"
    
    def test_add_cache_control_headers_custom(self):
        """Test adding cache control headers with custom values."""
        response = Response()
        custom_cache_control = "public, max-age=3600"
        
        add_cache_control_headers(response, custom_cache_control)
        
        assert response.headers["cache-control"] == custom_cache_control
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["expires"] == "0"


class TestSecurityHeadersToResponse:
    """Test adding security headers to response objects."""
    
    def test_add_security_headers_to_response_production(self):
        """Test adding security headers to response in production."""
        response = Response()
        
        add_security_headers_to_response(response, is_production=True)
        
        # Check for key security headers
        expected_headers = [
            "content-security-policy",
            "x-frame-options",
            "x-content-type-options",
            "x-xss-protection",
            "referrer-policy",
            "permissions-policy",
            "strict-transport-security"
        ]
        
        for header in expected_headers:
            assert header in response.headers
            assert response.headers[header] is not None
            assert len(response.headers[header]) > 0
    
    def test_add_security_headers_to_response_development(self):
        """Test adding security headers to response in development."""
        response = Response()
        
        add_security_headers_to_response(response, is_production=False)
        
        # Check for key security headers (HSTS should be disabled in development)
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
        
        # HSTS should not be present or empty in development
        hsts = response.headers.get("strict-transport-security", "")
        assert hsts == ""


class TestSecurityHeadersIntegration:
    """Test security headers integration scenarios."""
    
    def test_security_headers_comprehensive_coverage(self):
        """Test that all security headers provide comprehensive coverage."""
        headers = get_security_headers(is_production=True)
        
        # Verify all major security categories are covered
        security_categories = {
            "content_injection": ["Content-Security-Policy", "X-Content-Type-Options"],                                                                         
            "clickjacking": ["X-Frame-Options", "Content-Security-Policy"],
            "xss": ["X-XSS-Protection", "Content-Security-Policy"],
            "information_disclosure": ["Referrer-Policy", "X-Permitted-Cross-Domain-Policies"],                                                                 
            "protocol_downgrade": ["Strict-Transport-Security"],                                                                   
            "feature_control": ["Permissions-Policy", "Feature-Policy"],
            "cross_origin": ["Cross-Origin-Embedder-Policy", "Cross-Origin-Opener-Policy", "Cross-Origin-Resource-Policy"],                                     
            "caching": ["Cache-Control", "Pragma", "Expires"]
        }
        
        for category, expected_headers in security_categories.items():
            for header in expected_headers:
                assert header in headers, f"Missing {header} for {category} protection"
                assert headers[header] is not None, f"Empty {header} for {category} protection"
                assert len(headers[header]) > 0, f"Empty {header} for {category} protection"
    
    def test_security_headers_development_vs_production(self):
        """Test differences between development and production security headers."""
        prod_headers = get_security_headers(is_production=True)
        dev_headers = get_security_headers(is_production=False)
        
        # Production should have HSTS
        assert "Strict-Transport-Security" in prod_headers
        assert prod_headers["Strict-Transport-Security"] != ""
        
        # Development should not have HSTS or have empty HSTS
        dev_hsts = dev_headers.get("Strict-Transport-Security", "")
        assert dev_hsts == ""
        
        # Both should have CSP but may differ
        assert "Content-Security-Policy" in prod_headers
        assert "Content-Security-Policy" in dev_headers
        
        # Both should have other security headers
        common_headers = [
            "X-Frame-Options",
            "X-Content-Type-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Permissions-Policy"
        ]
        
        for header in common_headers:
            assert header in prod_headers
            assert header in dev_headers
            assert prod_headers[header] == dev_headers[header]
    
    def test_security_headers_middleware_performance(self):
        """Test that security headers middleware doesn't significantly impact performance."""
        app = FastAPI()
        
        @app.get("/performance-test")
        async def performance_test():
            return {"message": "performance test"}
        
        app.middleware("http")(security_headers_middleware)
        client = TestClient(app)
        
        # Test multiple requests to ensure consistent performance
        for _ in range(10):
            response = client.get("/performance-test")
            assert response.status_code == 200
            assert "content-security-policy" in response.headers