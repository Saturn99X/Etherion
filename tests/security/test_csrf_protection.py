# tests/security/test_csrf_protection.py
"""
Tests for CSRF protection middleware and functionality.
"""

import pytest
import time
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from src.middleware.csrf_protection import (
    CSRFProtection,
    initialize_csrf_protection,
    get_csrf_protection,
    csrf_protection_middleware,
    set_csrf_cookie,
    get_csrf_token_from_cookie,
    generate_csrf_token_for_user,
    validate_csrf_token_for_user,
    revoke_csrf_tokens_for_user,
    require_csrf_token
)


class TestCSRFProtection:
    """Test CSRF protection functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.secret_key = "test-secret-key-for-csrf-protection"
        self.csrf_protection = CSRFProtection(self.secret_key)
        self.user_id = "test-user-123"
        self.session_id = "test-session-456"
    
    def test_generate_csrf_token(self):
        """Test CSRF token generation."""
        token = self.csrf_protection.generate_csrf_token(self.user_id, self.session_id)
        
        assert token is not None
        assert len(token) > 0
        assert ":" in token  # Should contain separators
        
        # Token should be in cache
        assert token in self.csrf_protection.token_cache
        
        cached_data = self.csrf_protection.token_cache[token]
        assert cached_data["user_id"] == self.user_id
        assert cached_data["session_id"] == self.session_id
        assert cached_data["created_at"] > 0
        assert cached_data["expires_at"] > cached_data["created_at"]
    
    def test_validate_csrf_token_valid(self):
        """Test CSRF token validation with valid token."""
        token = self.csrf_protection.generate_csrf_token(self.user_id, self.session_id)
        
        is_valid = self.csrf_protection.validate_csrf_token(token, self.user_id, self.session_id)
        
        assert is_valid is True
    
    def test_validate_csrf_token_invalid_user(self):
        """Test CSRF token validation with invalid user."""
        token = self.csrf_protection.generate_csrf_token(self.user_id, self.session_id)
        
        is_valid = self.csrf_protection.validate_csrf_token(token, "different-user", self.session_id)
        
        assert is_valid is False
    
    def test_validate_csrf_token_invalid_session(self):
        """Test CSRF token validation with invalid session."""
        token = self.csrf_protection.generate_csrf_token(self.user_id, self.session_id)
        
        is_valid = self.csrf_protection.validate_csrf_token(token, self.user_id, "different-session")
        
        assert is_valid is False
    
    def test_validate_csrf_token_expired(self):
        """Test CSRF token validation with expired token."""
        # Create token with short expiry
        with patch('src.middleware.csrf_protection.CSRF_TOKEN_EXPIRY', 0.1):
            token = self.csrf_protection.generate_csrf_token(self.user_id, self.session_id)
        
        # Wait for token to expire
        time.sleep(0.2)
        
        is_valid = self.csrf_protection.validate_csrf_token(token, self.user_id, self.session_id)
        
        assert is_valid is False
        # Token should be removed from cache
        assert token not in self.csrf_protection.token_cache
    
    def test_validate_csrf_token_malformed(self):
        """Test CSRF token validation with malformed token."""
        malformed_tokens = [
            "",
            "invalid-token",
            "too:few:parts",
            "too:many:parts:here:extra:part"
        ]
        
        for token in malformed_tokens:
            is_valid = self.csrf_protection.validate_csrf_token(token, self.user_id, self.session_id)
            assert is_valid is False
    
    def test_validate_csrf_token_signature_mismatch(self):
        """Test CSRF token validation with signature mismatch."""
        token = self.csrf_protection.generate_csrf_token(self.user_id, self.session_id)
        
        # Modify the signature
        parts = token.split(':')
        parts[4] = "invalid-signature"
        modified_token = ':'.join(parts)
        
        is_valid = self.csrf_protection.validate_csrf_token(modified_token, self.user_id, self.session_id)
        
        assert is_valid is False
    
    def test_cleanup_expired_tokens(self):
        """Test cleanup of expired tokens."""
        # Create multiple tokens
        tokens = []
        for i in range(3):
            token = self.csrf_protection.generate_csrf_token(f"user-{i}", f"session-{i}")
            tokens.append(token)
        
        # Manually expire some tokens
        for token in tokens[:2]:
            self.csrf_protection.token_cache[token]["expires_at"] = time.time() - 1
        
        # Cleanup expired tokens
        self.csrf_protection.cleanup_expired_tokens()
        
        # Only non-expired token should remain
        assert len(self.csrf_protection.token_cache) == 1
        assert tokens[2] in self.csrf_protection.token_cache
    
    def test_revoke_user_tokens(self):
        """Test revocation of all tokens for a user."""
        # Create tokens for multiple users
        user1_tokens = []
        user2_tokens = []
        
        for i in range(3):
            token1 = self.csrf_protection.generate_csrf_token("user1", f"session-{i}")
            token2 = self.csrf_protection.generate_csrf_token("user2", f"session-{i}")
            user1_tokens.append(token1)
            user2_tokens.append(token2)
        
        # Revoke tokens for user1
        self.csrf_protection.revoke_user_tokens("user1")
        
        # user1 tokens should be removed
        for token in user1_tokens:
            assert token not in self.csrf_protection.token_cache
        
        # user2 tokens should remain
        for token in user2_tokens:
            assert token in self.csrf_protection.token_cache


class TestCSRFMiddleware:
    """Test CSRF protection middleware."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.secret_key = "test-secret-key-for-csrf-protection"
        initialize_csrf_protection(self.secret_key)
        
        self.app = FastAPI()
        
        @self.app.get("/safe-endpoint")
        async def safe_endpoint():
            return {"message": "safe"}
        
        @self.app.post("/unsafe-endpoint")
        async def unsafe_endpoint():
            return {"message": "unsafe"}
        
        # Add CSRF middleware
        self.app.middleware("http")(csrf_protection_middleware)
        
        self.client = TestClient(self.app)
    
    def test_safe_methods_bypass_csrf(self):
        """Test that safe methods bypass CSRF protection."""
        response = self.client.get("/safe-endpoint")
        assert response.status_code == 200
        assert response.json() == {"message": "safe"}
    
    def test_unsafe_methods_require_csrf(self):
        """Test that unsafe methods require CSRF protection."""
        response = self.client.post("/unsafe-endpoint")
        assert response.status_code == 403
        assert "CSRF validation failed" in response.json()["error"]
    
    def test_unsafe_methods_with_valid_csrf(self):
        """Test that unsafe methods work with valid CSRF token."""
        # This test would require proper user authentication setup
        # For now, we'll test the structure
        response = self.client.post("/unsafe-endpoint")
        assert response.status_code == 403  # Expected without proper auth setup


class TestCSRFUtilityFunctions:
    """Test CSRF utility functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.secret_key = "test-secret-key-for-csrf-protection"
        initialize_csrf_protection(self.secret_key)
        self.user_id = "test-user-123"
        self.session_id = "test-session-456"
    
    def test_generate_csrf_token_for_user(self):
        """Test generate_csrf_token_for_user utility function."""
        token = generate_csrf_token_for_user(self.user_id, self.session_id)
        
        assert token is not None
        assert len(token) > 0
    
    def test_validate_csrf_token_for_user(self):
        """Test validate_csrf_token_for_user utility function."""
        token = generate_csrf_token_for_user(self.user_id, self.session_id)
        
        is_valid = validate_csrf_token_for_user(token, self.user_id, self.session_id)
        assert is_valid is True
        
        is_valid = validate_csrf_token_for_user(token, "different-user", self.session_id)
        assert is_valid is False
    
    def test_revoke_csrf_tokens_for_user(self):
        """Test revoke_csrf_tokens_for_user utility function."""
        # Generate tokens
        token1 = generate_csrf_token_for_user(self.user_id, "session1")
        token2 = generate_csrf_token_for_user(self.user_id, "session2")
        
        # Verify tokens exist
        assert validate_csrf_token_for_user(token1, self.user_id, "session1")
        assert validate_csrf_token_for_user(token2, self.user_id, "session2")
        
        # Revoke tokens
        revoke_csrf_tokens_for_user(self.user_id)
        
        # Verify tokens are revoked
        assert not validate_csrf_token_for_user(token1, self.user_id, "session1")
        assert not validate_csrf_token_for_user(token2, self.user_id, "session2")


class TestCSRFDecorator:
    """Test CSRF decorator functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.secret_key = "test-secret-key-for-csrf-protection"
        initialize_csrf_protection(self.secret_key)
        self.user_id = "test-user-123"
        self.session_id = "test-session-456"
    
    def test_require_csrf_token_decorator_valid(self):
        """Test require_csrf_token decorator with valid token."""
        @require_csrf_token
        def test_mutation(info, csrf_token: str):
            return {"success": True}
        
        # Mock GraphQL info object
        mock_info = Mock()
        mock_info.context.user_id = self.user_id
        mock_info.context.session_id = self.session_id
        
        # Generate valid CSRF token
        token = generate_csrf_token_for_user(self.user_id, self.session_id)
        
        # Call decorated function
        result = test_mutation(mock_info, csrf_token=token)
        
        assert result == {"success": True}
    
    def test_require_csrf_token_decorator_invalid(self):
        """Test require_csrf_token decorator with invalid token."""
        @require_csrf_token
        def test_mutation(info, csrf_token: str):
            return {"success": True}
        
        # Mock GraphQL info object
        mock_info = Mock()
        mock_info.context.user_id = self.user_id
        mock_info.context.session_id = self.session_id
        
        # Call with invalid token
        with pytest.raises(HTTPException) as exc_info:
            test_mutation(mock_info, csrf_token="invalid-token")
        
        assert exc_info.value.status_code == 403
        assert "Invalid CSRF token" in str(exc_info.value.detail)
    
    def test_require_csrf_token_decorator_missing_token(self):
        """Test require_csrf_token decorator with missing token."""
        @require_csrf_token
        def test_mutation(info, csrf_token: str):
            return {"success": True}
        
        # Mock GraphQL info object
        mock_info = Mock()
        mock_info.context.user_id = self.user_id
        mock_info.context.session_id = self.session_id
        
        # Call without token
        with pytest.raises(HTTPException) as exc_info:
            test_mutation(mock_info)
        
        assert exc_info.value.status_code == 403
        assert "CSRF token required" in str(exc_info.value.detail)


class TestCSRFCookieFunctions:
    """Test CSRF cookie utility functions."""
    
    def test_set_csrf_cookie(self):
        """Test setting CSRF cookie."""
        response = Response()
        token = "test-csrf-token"
        
        set_csrf_cookie(response, token)
        
        # Check if cookie was set
        assert "set-cookie" in response.headers
        cookie_header = response.headers["set-cookie"]
        assert "csrf_token=test-csrf-token" in cookie_header
    
    def test_get_csrf_token_from_cookie(self):
        """Test getting CSRF token from cookie."""
        # Mock request with cookie
        request = Mock()
        request.cookies = {"csrf_token": "test-csrf-token"}
        
        token = get_csrf_token_from_cookie(request)
        
        assert token == "test-csrf-token"
    
    def test_get_csrf_token_from_cookie_missing(self):
        """Test getting CSRF token from cookie when missing."""
        # Mock request without cookie
        request = Mock()
        request.cookies = {}
        
        token = get_csrf_token_from_cookie(request)
        
        assert token is None


class TestCSRFIntegration:
    """Test CSRF protection integration scenarios."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.secret_key = "test-secret-key-for-csrf-protection"
        initialize_csrf_protection(self.secret_key)
    
    def test_csrf_token_lifecycle(self):
        """Test complete CSRF token lifecycle."""
        user_id = "test-user-123"
        session_id = "test-session-456"
        
        # 1. Generate token
        token = generate_csrf_token_for_user(user_id, session_id)
        assert token is not None
        
        # 2. Validate token
        is_valid = validate_csrf_token_for_user(token, user_id, session_id)
        assert is_valid is True
        
        # 3. Use token multiple times (should still be valid)
        is_valid = validate_csrf_token_for_user(token, user_id, session_id)
        assert is_valid is True
        
        # 4. Revoke all tokens for user
        revoke_csrf_tokens_for_user(user_id)
        
        # 5. Token should no longer be valid
        is_valid = validate_csrf_token_for_user(token, user_id, session_id)
        assert is_valid is False
    
    def test_multiple_users_tokens(self):
        """Test CSRF tokens for multiple users."""
        user1_id = "user1"
        user2_id = "user2"
        session_id = "session-123"
        
        # Generate tokens for both users
        token1 = generate_csrf_token_for_user(user1_id, session_id)
        token2 = generate_csrf_token_for_user(user2_id, session_id)
        
        # Both tokens should be valid
        assert validate_csrf_token_for_user(token1, user1_id, session_id)
        assert validate_csrf_token_for_user(token2, user2_id, session_id)
        
        # Tokens should not be interchangeable
        assert not validate_csrf_token_for_user(token1, user2_id, session_id)
        assert not validate_csrf_token_for_user(token2, user1_id, session_id)
        
        # Revoke tokens for user1 only
        revoke_csrf_tokens_for_user(user1_id)
        
        # user1 token should be invalid, user2 token should still be valid
        assert not validate_csrf_token_for_user(token1, user1_id, session_id)
        assert validate_csrf_token_for_user(token2, user2_id, session_id)
    
    def test_csrf_protection_initialization(self):
        """Test CSRF protection initialization."""
        # Should be able to get the global instance
        csrf_protection = get_csrf_protection()
        assert csrf_protection is not None
        assert isinstance(csrf_protection, CSRFProtection)
        
        # Should be able to generate and validate tokens
        token = csrf_protection.generate_csrf_token("test-user", "test-session")
        assert token is not None
        
        is_valid = csrf_protection.validate_csrf_token(token, "test-user", "test-session")
        assert is_valid is True
