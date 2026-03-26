"""
Tests for authentication system functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import json

from src.auth.jwt import (
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_access_token,
    decode_refresh_token,
    generate_password_reset_token,
    verify_password_reset_token,
    generate_mfa_token,
    verify_mfa_token
)
from src.auth.models import TokenData, UserAuth, SessionData, MFAChallenge
from src.auth.session_manager import SessionManager, SessionInfo
from src.auth.mfa import MFAManager, MFAConfig
from src.auth.password_reset import PasswordResetManager, PasswordResetInfo
from src.auth.middleware import AuthMiddleware, get_current_user


class TestJWTFunctionality:
    """Test JWT token functionality."""
    
    def test_create_access_token(self):
        """Test creating access token."""
        data = {"sub": "user123", "email": "test@example.com", "tenant_id": 1}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_refresh_token(self):
        """Test creating refresh token."""
        data = {"sub": "user123", "email": "test@example.com", "tenant_id": 1}
        token = create_refresh_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_token_pair(self):
        """Test creating token pair."""
        data = {"sub": "user123", "email": "test@example.com", "tenant_id": 1}
        tokens = create_token_pair(data)
        
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert "token_type" in tokens
        assert tokens["token_type"] == "bearer"
    
    def test_decode_access_token(self):
        """Test decoding access token."""
        data = {"sub": "user123", "email": "test@example.com", "tenant_id": 1}
        token = create_access_token(data)
        
        decoded = decode_access_token(token)
        
        assert isinstance(decoded, TokenData)
        assert decoded.user_id == "user123"
        assert decoded.email == "test@example.com"
        assert decoded.tenant_id == 1
    
    def test_decode_refresh_token(self):
        """Test decoding refresh token."""
        data = {"sub": "user123", "email": "test@example.com", "tenant_id": 1}
        token = create_refresh_token(data)
        
        decoded = decode_refresh_token(token)
        
        assert isinstance(decoded, TokenData)
        assert decoded.user_id == "user123"
        assert decoded.email == "test@example.com"
        assert decoded.tenant_id == 1
    
    def test_token_expiration(self):
        """Test token expiration."""
        data = {"sub": "user123", "email": "test@example.com"}
        # Create token with very short expiration
        token = create_access_token(data, expires_delta=timedelta(seconds=1))
        
        # Should work immediately
        decoded = decode_access_token(token)
        assert decoded.user_id == "user123"
        
        # Wait for expiration
        import time
        time.sleep(2)
        
        # Should fail after expiration
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token(token)
    
    def test_password_reset_token(self):
        """Test password reset token generation and verification."""
        email = "test@example.com"
        token = generate_password_reset_token(email)
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Verify token
        verified_email = verify_password_reset_token(token)
        assert verified_email == email
        
        # Test invalid token
        invalid_email = verify_password_reset_token("invalid_token")
        assert invalid_email is None
    
    def test_mfa_token(self):
        """Test MFA token generation and verification."""
        user_id = "user123"
        tenant_id = 1
        token = generate_mfa_token(user_id, tenant_id)
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Verify token
        verified_data = verify_mfa_token(token)
        assert verified_data is not None
        assert verified_data.user_id == user_id
        assert verified_data.tenant_id == tenant_id
        
        # Test invalid token
        invalid_data = verify_mfa_token("invalid_token")
        assert invalid_data is None


class TestSessionManager:
    """Test session management functionality."""
    
    @pytest.fixture
    def session_manager(self):
        """Create session manager instance."""
        return SessionManager()
    
    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis_mock = AsyncMock()
        redis_mock.setex = AsyncMock()
        redis_mock.get = AsyncMock()
        redis_mock.delete = AsyncMock(return_value=1)
        redis_mock.sadd = AsyncMock()
        redis_mock.expire = AsyncMock()
        redis_mock.smembers = AsyncMock(return_value=set())
        redis_mock.ttl = AsyncMock(return_value=3600)
        redis_mock.srem = AsyncMock()
        return redis_mock
    
    @pytest.mark.asyncio
    async def test_create_session(self, session_manager, mock_redis):
        """Test creating a new session."""
        with patch('src.auth.session_manager.get_session') as mock_get_session:
            # Mock database session
            mock_db_session = Mock()
            mock_user = Mock()
            mock_user.user_id = "user123"
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            
            # Mock Redis
            session_manager.redis_client = mock_redis
            
            from src.auth.models import SessionCreate
            session_data = SessionCreate(
                user_id="user123",
                tenant_id=1,
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
                expires_in_hours=24
            )
            
            session_info = await session_manager.create_session(session_data)
            
            assert isinstance(session_info, SessionInfo)
            assert session_info.user_id == "user123"
            assert session_info.tenant_id == 1
            assert session_info.ip_address == "192.168.1.1"
            assert session_info.is_active is True
            
            # Verify Redis operations
            mock_redis.setex.assert_called()
            mock_redis.sadd.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_session(self, session_manager, mock_redis):
        """Test getting session information."""
        # Mock Redis response
        session_data = {
            "session_id": "test_session",
            "user_id": "user123",
            "tenant_id": 1,
            "created_at": datetime.utcnow().isoformat(),
            "last_accessed": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "is_active": True
        }
        mock_redis.get.return_value = json.dumps(session_data)
        
        session_manager.redis_client = mock_redis
        
        session_info = await session_manager.get_session("test_session")
        
        assert session_info is not None
        assert session_info.session_id == "test_session"
        assert session_info.user_id == "user123"
        assert session_info.tenant_id == 1
    
    @pytest.mark.asyncio
    async def test_delete_session(self, session_manager, mock_redis):
        """Test deleting a session."""
        # Mock get_session to return session info
        session_info = SessionInfo(
            session_id="test_session",
            user_id="user123",
            tenant_id=1,
            created_at=datetime.utcnow(),
            last_accessed=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            is_active=True
        )
        
        with patch.object(session_manager, 'get_session', return_value=session_info):
            session_manager.redis_client = mock_redis
            
            result = await session_manager.delete_session("test_session")
            
            assert result is True
            mock_redis.delete.assert_called()
            mock_redis.srem.assert_called()


class TestMFAManager:
    """Test MFA functionality."""
    
    @pytest.fixture
    def mfa_manager(self):
        """Create MFA manager instance."""
        return MFAManager()
    
    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis_mock = AsyncMock()
        redis_mock.setex = AsyncMock()
        redis_mock.get = AsyncMock()
        redis_mock.delete = AsyncMock()
        redis_mock.set = AsyncMock()
        return redis_mock
    
    @pytest.mark.asyncio
    async def test_setup_totp(self, mfa_manager, mock_redis):
        """Test TOTP setup."""
        with patch('src.auth.mfa.get_session') as mock_get_session:
            # Mock database session
            mock_db_session = Mock()
            mock_user = Mock()
            mock_user.email = "test@example.com"
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            
            # Mock Redis
            mfa_manager.redis_client = mock_redis
            
            result = await mfa_manager.setup_totp("user123")
            
            assert "secret" in result
            assert "provisioning_uri" in result
            assert "qr_code" in result
            assert "backup_codes" in result
            assert len(result["backup_codes"]) == 10
            
            # Verify Redis operations
            mock_redis.setex.assert_called()
    
    @pytest.mark.asyncio
    async def test_verify_totp_setup(self, mfa_manager, mock_redis):
        """Test TOTP setup verification."""
        # Mock Redis response with temporary secret
        mock_redis.get.return_value = "test_secret"
        mock_redis.delete = AsyncMock()
        
        mfa_manager.redis_client = mock_redis
        
        # Mock TOTP verification (this would need actual TOTP implementation)
        with patch('src.auth.mfa.pyotp.TOTP') as mock_totp_class:
            mock_totp = Mock()
            mock_totp.verify.return_value = True
            mock_totp_class.return_value = mock_totp
            
            result = await mfa_manager.verify_totp_setup("user123", "123456")
            
            assert result is True
            mock_redis.set.assert_called()
            mock_redis.delete.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_challenge(self, mfa_manager, mock_redis):
        """Test creating MFA challenge."""
        # Mock get_mfa_config
        config = MFAConfig(
            user_id="user123",
            totp_secret="test_secret",
            is_enabled=True
        )
        
        with patch.object(mfa_manager, 'get_mfa_config', return_value=config):
            mfa_manager.redis_client = mock_redis
            
            challenge = await mfa_manager.create_challenge("user123", "totp")
            
            assert isinstance(challenge, MFAChallenge)
            assert challenge.user_id == "user123"
            assert challenge.method == "totp"
            assert challenge.secret == "test_secret"
            assert challenge.is_verified is False
            
            # Verify Redis operations
            mock_redis.setex.assert_called()
    
    @pytest.mark.asyncio
    async def test_verify_challenge(self, mfa_manager, mock_redis):
        """Test verifying MFA challenge."""
        # Mock Redis response
        challenge_data = {
            "challenge_id": "test_challenge",
            "user_id": "user123",
            "method": "totp",
            "secret": "test_secret",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
            "attempts": 0,
            "max_attempts": 3,
            "is_verified": False
        }
        mock_redis.get.return_value = json.dumps(challenge_data)
        
        mfa_manager.redis_client = mock_redis
        
        # Mock TOTP verification
        with patch('src.auth.mfa.pyotp.TOTP') as mock_totp_class:
            mock_totp = Mock()
            mock_totp.verify.return_value = True
            mock_totp_class.return_value = mock_totp
            
            result = await mfa_manager.verify_challenge("test_challenge", "123456")
            
            assert result is True
            mock_redis.setex.assert_called()


class TestPasswordResetManager:
    """Test password reset functionality."""
    
    @pytest.fixture
    def password_reset_manager(self):
        """Create password reset manager instance."""
        return PasswordResetManager()
    
    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock()
        redis_mock.setex = AsyncMock()
        redis_mock.incr = AsyncMock()
        redis_mock.expire = AsyncMock()
        redis_mock.delete = AsyncMock()
        return redis_mock
    
    @pytest.mark.asyncio
    async def test_request_password_reset(self, password_reset_manager, mock_redis):
        """Test password reset request."""
        with patch('src.auth.password_reset.get_session') as mock_get_session:
            # Mock database session
            mock_db_session = Mock()
            mock_user = Mock()
            mock_user.user_id = "user123"
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            
            # Mock Redis
            password_reset_manager.redis_client = mock_redis
            
            result = await password_reset_manager.request_password_reset(
                "test@example.com", "192.168.1.1", "Mozilla/5.0"
            )
            
            assert result["success"] is True
            assert "message" in result
            assert "reset_token" in result  # Only in development
            assert "reset_link" in result   # Only in development
            
            # Verify Redis operations
            mock_redis.setex.assert_called()
            mock_redis.incr.assert_called()
    
    @pytest.mark.asyncio
    async def test_verify_reset_token(self, password_reset_manager, mock_redis):
        """Test password reset token verification."""
        # Mock Redis response
        reset_data = {
            "token": "test_token",
            "email": "test@example.com",
            "user_id": "user123",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            "used": False,
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        }
        mock_redis.get.return_value = json.dumps(reset_data)
        
        password_reset_manager.redis_client = mock_redis
        
        # Mock JWT verification
        with patch('src.auth.password_reset.verify_password_reset_token', return_value="test@example.com"):
            result = await password_reset_manager.verify_reset_token("test_token")
            
            assert result is not None
            assert isinstance(result, PasswordResetInfo)
            assert result.email == "test@example.com"
            assert result.user_id == "user123"
            assert result.used is False
    
    @pytest.mark.asyncio
    async def test_reset_password(self, password_reset_manager, mock_redis):
        """Test password reset."""
        with patch('src.auth.password_reset.get_session') as mock_get_session, \
             patch.object(password_reset_manager, 'verify_reset_token') as mock_verify:
            
            # Mock reset info
            reset_info = PasswordResetInfo(
                token="test_token",
                email="test@example.com",
                user_id="user123",
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=1),
                used=False
            )
            mock_verify.return_value = reset_info
            
            # Mock database session
            mock_db_session = Mock()
            mock_user = Mock()
            mock_user.user_id = "user123"
            mock_user.password_hash = None
            mock_user.updated_at = None
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            
            # Mock Redis
            password_reset_manager.redis_client = mock_redis
            
            result = await password_reset_manager.reset_password("test_token", "newpassword123")
            
            assert result["success"] is True
            assert "message" in result
            
            # Verify user password was updated
            assert mock_user.password_hash is not None
            assert mock_user.updated_at is not None
            mock_db_session.commit.assert_called_once()


class TestAuthMiddleware:
    """Test authentication middleware."""
    
    @pytest.fixture
    def auth_middleware(self):
        """Create auth middleware instance."""
        return AuthMiddleware(Mock(), exclude_paths=["/health"])
    
    def test_extract_token_from_header(self, auth_middleware):
        """Test extracting token from Authorization header."""
        from fastapi import Request
        
        # Mock request with Authorization header
        request = Mock(spec=Request)
        request.headers = {"Authorization": "Bearer test_token"}
        request.cookies = {}
        
        token = auth_middleware._extract_token(request)
        
        assert token == "test_token"
    
    def test_extract_token_from_cookie(self, auth_middleware):
        """Test extracting token from cookie."""
        from fastapi import Request
        
        # Mock request with cookie
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {"access_token": "test_token"}
        
        token = auth_middleware._extract_token(request)
        
        assert token == "test_token"
    
    def test_extract_token_none(self, auth_middleware):
        """Test extracting token when none present."""
        from fastapi import Request
        
        # Mock request without token
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {}
        
        token = auth_middleware._extract_token(request)
        
        assert token is None


@pytest.mark.asyncio
async def test_integration_auth_flow():
    """Integration test for complete authentication flow."""
    # This would test the complete authentication flow from login to session management
    pass


@pytest.mark.asyncio
async def test_integration_mfa_flow():
    """Integration test for MFA flow."""
    # This would test the complete MFA flow from setup to verification
    pass

