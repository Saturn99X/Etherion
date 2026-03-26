# tests/security/test_rate_limiting.py
"""
Comprehensive tests for rate limiting functionality.
Tests rate limiting for authentication endpoints and GraphQL mutations.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi import Request, HTTPException
from fastapi.testclient import TestClient

from src.middleware.rate_limiter import (
    check_rate_limit,
    get_client_identifier,
    get_rate_limit_key,
    rate_limit_middleware,
    graphql_rate_limit_middleware,
    RATE_LIMIT_CONFIG
)


class TestRateLimiting:
    """Test cases for rate limiting functionality."""
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock request object."""
        request = Mock(spec=Request)
        request.client.host = "127.0.0.1"
        request.headers = {"user-agent": "test-agent"}
        request.url.path = "/test"
        return request
    
    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        # Create a proper async context manager mock
        class MockPipeline:
            def __init__(self):
                self.incr = AsyncMock(return_value=1)
                self.expire = AsyncMock(return_value=True)
                self.get = AsyncMock(return_value="1")
                self.execute = AsyncMock(return_value=[1, True, 1, True, "1", "1"])
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None
        
        redis_mock = AsyncMock()
        redis_mock.pipeline = Mock(return_value=MockPipeline())
        return redis_mock
    
    def test_get_client_identifier(self, mock_request):
        """Test client identifier generation."""
        identifier = get_client_identifier(mock_request)
        assert isinstance(identifier, str)
        assert len(identifier) == 16
        
        # Test with forwarded IP
        mock_request.headers["x-forwarded-for"] = "192.168.1.1, 127.0.0.1"
        identifier2 = get_client_identifier(mock_request)
        assert identifier2 != identifier
    
    def test_get_rate_limit_key(self):
        """Test rate limit key generation."""
        key = get_rate_limit_key("test_id", "auth_endpoints", "minute:123")
        expected = "rate_limit:auth_endpoints:test_id:minute:123"
        assert key == expected
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_success(self, mock_request, mock_redis):
        """Test successful rate limit check."""
        with patch('src.middleware.rate_limiter.get_redis_client', return_value=mock_redis):
            result = await check_rate_limit(mock_request, "default")
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded_minute(self, mock_request, mock_redis):
        """Test rate limit exceeded for per-minute limit."""
        # Mock Redis pipeline to return count exceeding limit (default is 60/minute)
        pipeline_mock = mock_redis.pipeline.return_value
        pipeline_mock.execute = AsyncMock(return_value=[1, True, 1, True, "61", "1"])  # minute count exceeds limit
        
        with patch('src.middleware.rate_limiter.get_redis_client', return_value=mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(mock_request, "default")
            
            assert exc_info.value.status_code == 429
            assert "Rate limit exceeded" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded_hour(self, mock_request, mock_redis):
        """Test rate limit exceeded for per-hour limit."""
        # Mock Redis pipeline to return count exceeding limit (default is 1000/hour)
        pipeline_mock = mock_redis.pipeline.return_value
        pipeline_mock.execute = AsyncMock(return_value=[1, True, 1, True, "1", "1001"])  # hour count exceeds limit
        
        with patch('src.middleware.rate_limiter.get_redis_client', return_value=mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(mock_request, "default")
            
            assert exc_info.value.status_code == 429
            assert "Rate limit exceeded" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_failure(self, mock_request):
        """Test rate limiting when Redis fails."""
        mock_redis = AsyncMock()
        mock_redis.pipeline.side_effect = Exception("Redis connection failed")
        
        with patch('src.middleware.rate_limiter.get_redis_client', return_value=mock_redis):
            # Should allow request when Redis fails
            result = await check_rate_limit(mock_request, "default")
            assert result is True
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_auth_endpoint(self, mock_request):
        """Test rate limiting middleware for auth endpoints."""
        mock_request.url.path = "/auth/login"
        
        async def mock_call_next(request):
            return Mock()
        
        with patch('src.middleware.rate_limiter.check_rate_limit') as mock_check:
            mock_check.return_value = True
            response = await rate_limit_middleware(mock_request, mock_call_next)
            mock_check.assert_called_once_with(mock_request, "auth_endpoints")
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_graphql_endpoint(self, mock_request):
        """Test rate limiting middleware for GraphQL endpoints."""
        mock_request.url.path = "/graphql"
        
        async def mock_call_next(request):
            return Mock()
        
        with patch('src.middleware.rate_limiter.check_rate_limit') as mock_check:
            mock_check.return_value = True
            response = await rate_limit_middleware(mock_request, mock_call_next)
            mock_check.assert_called_once_with(mock_request, "graphql_queries")
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_429_response(self, mock_request):
        """Test rate limiting middleware returns 429 when limit exceeded."""
        async def mock_call_next(request):
            return Mock()
        
        with patch('src.middleware.rate_limiter.check_rate_limit') as mock_check:
            mock_check.side_effect = HTTPException(status_code=429, detail="Rate limit exceeded")
            response = await rate_limit_middleware(mock_request, mock_call_next)
            assert response.status_code == 429
    
    def test_get_graphql_operation_type_mutation(self):
        """Test GraphQL operation type detection for mutations."""
        from src.middleware.rate_limiter import get_graphql_operation_type
        
        request_body = '{"query": "mutation { createProject { id } }"}'
        operation_type = get_graphql_operation_type(request_body)
        assert operation_type == "graphql_mutations"
    
    def test_get_graphql_operation_type_query(self):
        """Test GraphQL operation type detection for queries."""
        from src.middleware.rate_limiter import get_graphql_operation_type
        
        request_body = '{"query": "query { projects { id name } }"}'
        operation_type = get_graphql_operation_type(request_body)
        assert operation_type == "graphql_queries"
    
    def test_get_graphql_operation_type_subscription(self):
        """Test GraphQL operation type detection for subscriptions."""
        from src.middleware.rate_limiter import get_graphql_operation_type
        
        request_body = '{"query": "subscription { jobUpdates { id status } }"}'
        operation_type = get_graphql_operation_type(request_body)
        assert operation_type == "graphql_subscriptions"
    
    def test_get_graphql_operation_type_invalid_json(self):
        """Test GraphQL operation type detection with invalid JSON."""
        from src.middleware.rate_limiter import get_graphql_operation_type
        
        request_body = "invalid json"
        operation_type = get_graphql_operation_type(request_body)
        assert operation_type == "graphql_queries"  # Default fallback
    
    @pytest.mark.asyncio
    async def test_graphql_rate_limit_middleware(self, mock_request):
        """Test GraphQL-specific rate limiting middleware."""
        mock_request.body = AsyncMock(return_value=b'{"query": "mutation { test }"}')
        
        async def mock_call_next(request):
            return Mock()
        
        with patch('src.middleware.rate_limiter.check_rate_limit') as mock_check:
            mock_check.return_value = True
            response = await graphql_rate_limit_middleware(mock_request, mock_call_next)
            mock_check.assert_called_once_with(mock_request, "graphql_mutations")
    
    def test_rate_limit_config(self):
        """Test rate limit configuration."""
        assert "auth_endpoints" in RATE_LIMIT_CONFIG
        assert "graphql_mutations" in RATE_LIMIT_CONFIG
        assert "graphql_queries" in RATE_LIMIT_CONFIG
        assert "default" in RATE_LIMIT_CONFIG
        
        # Check auth endpoints have stricter limits
        auth_config = RATE_LIMIT_CONFIG["auth_endpoints"]
        default_config = RATE_LIMIT_CONFIG["default"]
        assert auth_config["requests_per_minute"] < default_config["requests_per_minute"]
        assert auth_config["requests_per_hour"] < default_config["requests_per_hour"]
    
    @pytest.mark.asyncio
    async def test_custom_rate_limits(self, mock_request, mock_redis):
        """Test custom rate limits."""
        custom_limits = {
            "requests_per_minute": 5,
            "requests_per_hour": 50
        }
        
        with patch('src.middleware.rate_limiter.get_redis_client', return_value=mock_redis):
            result = await check_rate_limit(mock_request, "default", custom_limits)
            assert result is True
    
    @pytest.mark.asyncio
    async def test_rate_limit_headers(self, mock_request, mock_redis):
        """Test that rate limit headers are properly set."""
        # Mock Redis pipeline to return count exceeding limit (default is 60/minute)
        pipeline_mock = mock_redis.pipeline.return_value
        pipeline_mock.execute = AsyncMock(return_value=[1, True, 1, True, "61", "1"])  # minute count exceeds limit
        
        with patch('src.middleware.rate_limiter.get_redis_client', return_value=mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(mock_request, "default")
            
            # Check that headers are set
            headers = exc_info.value.headers
            assert "Retry-After" in headers
            assert "X-RateLimit-Limit" in headers
            assert "X-RateLimit-Remaining" in headers
            assert "X-RateLimit-Reset" in headers
