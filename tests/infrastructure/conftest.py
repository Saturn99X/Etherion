"""
Configuration and fixtures for infrastructure tests.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timedelta

# Global test configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client for testing."""
    redis_mock = AsyncMock()
    redis_mock.setex = AsyncMock()
    redis_mock.get = AsyncMock()
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.sadd = AsyncMock()
    redis_mock.expire = AsyncMock()
    redis_mock.smembers = AsyncMock(return_value=set())
    redis_mock.ttl = AsyncMock(return_value=3600)
    redis_mock.srem = AsyncMock()
    redis_mock.incr = AsyncMock()
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.info = AsyncMock(return_value={
        "redis_version": "6.2.0",
        "used_memory": 1024000,
        "connected_clients": 5,
        "total_commands_processed": 1000
    })
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.memory_purge = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_database_session():
    """Create a mock database session for testing."""
    session_mock = Mock()
    session_mock.query.return_value.filter.return_value.first.return_value = None
    session_mock.query.return_value.filter.return_value.count.return_value = 0
    session_mock.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    session_mock.execute.return_value.fetchone.return_value = (1,)
    session_mock.commit = Mock()
    session_mock.add = Mock()
    session_mock.delete = Mock()
    session_mock.refresh = Mock()
    return session_mock


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user_mock = Mock()
    user_mock.user_id = "test_user_123"
    user_mock.email = "test@example.com"
    user_mock.name = "Test User"
    user_mock.is_active = True
    user_mock.is_admin = False
    user_mock.tenant_id = 1
    user_mock.created_at = datetime.utcnow()
    user_mock.updated_at = datetime.utcnow()
    return user_mock


@pytest.fixture
def mock_tenant():
    """Create a mock tenant for testing."""
    tenant_mock = Mock()
    tenant_mock.id = 1
    tenant_mock.name = "Test Tenant"
    tenant_mock.subdomain = "test"
    tenant_mock.is_active = True
    tenant_mock.created_at = datetime.utcnow()
    tenant_mock.updated_at = datetime.utcnow()
    return tenant_mock


@pytest.fixture
def mock_job():
    """Create a mock job for testing."""
    job_mock = Mock()
    job_mock.job_id = "test_job_123"
    job_mock.tenant_id = 1
    job_mock.user_id = "test_user_123"
    job_mock.status = "running"
    job_mock.created_at = datetime.utcnow()
    job_mock.started_at = datetime.utcnow()
    job_mock.completed_at = None
    job_mock.error_message = None
    job_mock.trace_data_uri = None
    job_mock.update_status = Mock()
    job_mock.get_output_data = Mock(return_value={"output": "test"})
    job_mock.set_output_data = Mock()
    return job_mock


@pytest.fixture
def mock_cache():
    """Create a mock cache for testing."""
    cache_mock = AsyncMock()
    cache_mock.set = AsyncMock()
    cache_mock.get = AsyncMock()
    cache_mock.delete = AsyncMock(return_value=True)
    cache_mock.clear_tenant = AsyncMock(return_value={"total_evicted": 5})
    cache_mock.get_stats = AsyncMock(return_value={
        "l1": {"size": 100, "hits": 50, "misses": 10},
        "l2": {"size": 200, "hits": 30, "misses": 5}
    })
    
    # Mock L1 cache
    cache_mock.l1_cache = Mock()
    cache_mock.l1_cache._cache = {}
    cache_mock.l1_cache._access_order = {}
    cache_mock.l1_cache.max_size = 100
    cache_mock.l1_cache.delete = Mock(return_value=True)
    
    # Mock L2 cache
    cache_mock.l2_cache = Mock()
    cache_mock.l2_cache.redis_client = AsyncMock()
    cache_mock.l2_cache.redis_client.memory_purge = AsyncMock()
    
    # Mock L3 cache
    cache_mock.l3_cache = None
    
    return cache_mock


@pytest.fixture
def mock_celery_app():
    """Create a mock Celery app for testing."""
    celery_mock = Mock()
    
    # Mock inspect
    inspect_mock = Mock()
    inspect_mock.active.return_value = {
        "worker1@host": ["task1", "task2"],
        "worker2@host": ["task3"]
    }
    inspect_mock.stats.return_value = {
        "worker1@host": {"total": {"task1": 10, "task2": 5}},
        "worker2@host": {"total": {"task3": 8}}
    }
    inspect_mock.registered.return_value = {
        "worker1@host": ["task1", "task2", "task3"],
        "worker2@host": ["task1", "task2", "task3"]
    }
    
    celery_mock.control.inspect.return_value = inspect_mock
    return celery_mock


@pytest.fixture
def mock_gcs_client():
    """Create a mock GCS client for testing."""
    gcs_mock = Mock()
    gcs_mock.upload_file.return_value = "gs://bucket/path/file.json"
    gcs_mock.download_file = AsyncMock()
    gcs_mock.delete_file = AsyncMock()
    gcs_mock.list_files = AsyncMock(return_value=[])
    return gcs_mock


@pytest.fixture
def mock_knowledge_base_manager():
    """Create a mock knowledge base manager for testing."""
    kb_mock = Mock()
    kb_mock.add_user_feedback = Mock()
    kb_mock.add_execution_trace = Mock()
    kb_mock.add_document = Mock()
    kb_mock.search = AsyncMock(return_value=[])
    kb_mock.get_stats = Mock(return_value={"total_documents": 100})
    return kb_mock


@pytest.fixture
def sample_token_data():
    """Create sample token data for testing."""
    return {
        "sub": "test_user_123",
        "email": "test@example.com",
        "tenant_id": 1,
        "exp": datetime.utcnow() + timedelta(minutes=30)
    }


@pytest.fixture
def sample_session_data():
    """Create sample session data for testing."""
    return {
        "session_id": "test_session_123",
        "user_id": "test_user_123",
        "tenant_id": 1,
        "created_at": datetime.utcnow(),
        "last_accessed": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=24),
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0",
        "is_active": True
    }


@pytest.fixture
def sample_mfa_challenge():
    """Create sample MFA challenge for testing."""
    return {
        "challenge_id": "test_challenge_123",
        "user_id": "test_user_123",
        "method": "totp",
        "secret": "test_secret",
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=5),
        "attempts": 0,
        "max_attempts": 3,
        "is_verified": False
    }


@pytest.fixture
def sample_password_reset_info():
    """Create sample password reset info for testing."""
    return {
        "token": "test_reset_token_123",
        "email": "test@example.com",
        "user_id": "test_user_123",
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=1),
        "used": False,
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0"
    }


@pytest.fixture
def sample_health_check():
    """Create sample health check for testing."""
    return {
        "name": "test_service",
        "status": "healthy",
        "message": "Service is operational",
        "response_time_ms": 100.0,
        "timestamp": datetime.utcnow(),
        "details": {
            "version": "1.0.0",
            "uptime": 3600
        }
    }


@pytest.fixture
def sample_request_metrics():
    """Create sample request metrics for testing."""
    return {
        "method": "GET",
        "path": "/api/test",
        "status_code": 200,
        "response_time_ms": 150.0,
        "timestamp": datetime.utcnow(),
        "user_id": "test_user_123",
        "tenant_id": 1
    }


@pytest.fixture
def sample_system_metrics():
    """Create sample system metrics for testing."""
    return {
        "timestamp": datetime.utcnow(),
        "total_requests": 1000,
        "successful_requests": 950,
        "failed_requests": 50,
        "average_response_time_ms": 200.0,
        "active_jobs": 10,
        "completed_jobs": 500,
        "failed_jobs": 20,
        "cache_hit_rate": 0.85,
        "memory_usage_mb": 1024.0,
        "cpu_usage_percent": 45.0
    }


# Test utilities
class TestUtils:
    """Utility functions for tests."""
    
    @staticmethod
    def create_mock_request(method="GET", path="/api/test", headers=None, cookies=None):
        """Create a mock request for testing."""
        request_mock = Mock()
        request_mock.method = method
        request_mock.url.path = path
        request_mock.headers = headers or {}
        request_mock.cookies = cookies or {}
        request_mock.state = Mock()
        request_mock.state.user = None
        request_mock.state.tenant = None
        return request_mock
    
    @staticmethod
    def create_mock_response(status_code=200, body=None):
        """Create a mock response for testing."""
        response_mock = Mock()
        response_mock.status_code = status_code
        response_mock.body = (body or '{"message": "test"}').encode()
        return response_mock
    
    @staticmethod
    def assert_health_check_valid(check):
        """Assert that a health check is valid."""
        assert hasattr(check, 'name')
        assert hasattr(check, 'status')
        assert hasattr(check, 'message')
        assert hasattr(check, 'response_time_ms')
        assert hasattr(check, 'timestamp')
        assert check.response_time_ms >= 0
        assert check.timestamp is not None
    
    @staticmethod
    def assert_metrics_valid(metrics):
        """Assert that metrics are valid."""
        assert isinstance(metrics, dict)
        assert "timestamp" in metrics
        assert isinstance(metrics["timestamp"], (str, datetime))


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    for item in items:
        # Add unit marker to all tests by default
        if not any(marker.name in ["slow", "integration"] for marker in item.iter_markers()):
            item.add_marker(pytest.mark.unit)
        
        # Add slow marker to tests that take longer
        if "integration" in item.name or "test_integration" in item.name:
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.integration)

