"""
Tests for monitoring and metrics functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from collections import deque

from src.middleware.monitoring import (
    MetricsMiddleware,
    MonitoringRouter,
    LoggingMiddleware,
    ErrorHandlingMiddleware,
    RequestMetrics,
    SystemMetrics,
    _metrics_storage,
    _request_times,
    _error_counts
)


class TestRequestMetrics:
    """Test request metrics data structure."""
    
    def test_request_metrics_creation(self):
        """Test creating request metrics."""
        metrics = RequestMetrics(
            method="GET",
            path="/api/test",
            status_code=200,
            response_time_ms=150.0,
            timestamp=datetime.utcnow(),
            user_id="user123",
            tenant_id=1
        )
        
        assert metrics.method == "GET"
        assert metrics.path == "/api/test"
        assert metrics.status_code == 200
        assert metrics.response_time_ms == 150.0
        assert metrics.user_id == "user123"
        assert metrics.tenant_id == 1


class TestSystemMetrics:
    """Test system metrics data structure."""
    
    def test_system_metrics_creation(self):
        """Test creating system metrics."""
        metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            total_requests=1000,
            successful_requests=950,
            failed_requests=50,
            average_response_time_ms=200.0,
            active_jobs=10,
            completed_jobs=500,
            failed_jobs=20,
            cache_hit_rate=0.85,
            memory_usage_mb=1024.0,
            cpu_usage_percent=45.0
        )
        
        assert metrics.total_requests == 1000
        assert metrics.successful_requests == 950
        assert metrics.failed_requests == 50
        assert metrics.average_response_time_ms == 200.0
        assert metrics.active_jobs == 10
        assert metrics.completed_jobs == 500
        assert metrics.failed_jobs == 20
        assert metrics.cache_hit_rate == 0.85
        assert metrics.memory_usage_mb == 1024.0
        assert metrics.cpu_usage_percent == 45.0


class TestMetricsMiddleware:
    """Test metrics middleware functionality."""
    
    @pytest.fixture
    def metrics_middleware(self):
        """Create metrics middleware instance."""
        return MetricsMiddleware(Mock())
    
    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = Mock()
        request.method = "GET"
        request.url.path = "/api/test"
        request.state = Mock()
        request.state.user = None
        request.state.tenant = None
        return request
    
    @pytest.fixture
    def mock_response(self):
        """Create mock response."""
        response = Mock()
        response.status_code = 200
        return response
    
    @pytest.mark.asyncio
    async def test_metrics_middleware_disabled(self, metrics_middleware, mock_request, mock_response):
        """Test metrics middleware when disabled."""
        metrics_middleware.metrics_enabled = False
        
        # Mock call_next
        call_next = AsyncMock(return_value=mock_response)
        
        response = await metrics_middleware.dispatch(mock_request, call_next)
        
        assert response == mock_response
        call_next.assert_called_once_with(mock_request)
    
    @pytest.mark.asyncio
    async def test_metrics_middleware_enabled(self, metrics_middleware, mock_request, mock_response):
        """Test metrics middleware when enabled."""
        metrics_middleware.metrics_enabled = True
        
        # Mock call_next
        call_next = AsyncMock(return_value=mock_response)
        
        # Clear global metrics storage
        _metrics_storage.clear()
        _request_times.clear()
        _error_counts.clear()
        
        response = await metrics_middleware.dispatch(mock_request, call_next)
        
        assert response == mock_response
        call_next.assert_called_once_with(mock_request)
        
        # Check that metrics were recorded
        assert _metrics_storage['total_requests'] == 1
        assert _metrics_storage['successful_requests'] == 1
        assert len(_request_times) == 1
    
    @pytest.mark.asyncio
    async def test_metrics_middleware_with_user_context(self, metrics_middleware, mock_response):
        """Test metrics middleware with user context."""
        metrics_middleware.metrics_enabled = True
        
        # Mock request with user context
        mock_request = Mock()
        mock_request.method = "POST"
        mock_request.url.path = "/api/users"
        mock_request.state = Mock()
        mock_user = Mock()
        mock_user.user_id = "user123"
        mock_tenant = Mock()
        mock_tenant.id = 1
        mock_request.state.user = mock_user
        mock_request.state.tenant = mock_tenant
        
        # Mock call_next
        call_next = AsyncMock(return_value=mock_response)
        
        # Clear global metrics storage
        _metrics_storage.clear()
        _request_times.clear()
        _error_counts.clear()
        
        response = await metrics_middleware.dispatch(mock_request, call_next)
        
        assert response == mock_response
        assert _metrics_storage['total_requests'] == 1
        assert _metrics_storage['successful_requests'] == 1
    
    @pytest.mark.asyncio
    async def test_metrics_middleware_error_response(self, metrics_middleware, mock_request):
        """Test metrics middleware with error response."""
        metrics_middleware.metrics_enabled = True
        
        # Mock error response
        error_response = Mock()
        error_response.status_code = 500
        
        # Mock call_next
        call_next = AsyncMock(return_value=error_response)
        
        # Clear global metrics storage
        _metrics_storage.clear()
        _request_times.clear()
        _error_counts.clear()
        
        response = await metrics_middleware.dispatch(mock_request, call_next)
        
        assert response == error_response
        assert _metrics_storage['total_requests'] == 1
        assert _metrics_storage['failed_requests'] == 1
        assert _error_counts['500'] == 1


class TestMonitoringRouter:
    """Test monitoring router functionality."""
    
    @pytest.fixture
    def monitoring_router(self):
        """Create monitoring router instance."""
        return MonitoringRouter()
    
    @pytest.mark.asyncio
    async def test_health_check_endpoint(self, monitoring_router):
        """Test health check endpoint."""
        with patch('src.middleware.monitoring.get_health_status') as mock_get_health:
            mock_health_status = {
                "overall_status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "checks": [],
                "summary": {"healthy": 1},
                "uptime_seconds": 3600.0
            }
            mock_get_health.return_value = mock_health_status
            
            # Mock the endpoint function
            endpoint_func = monitoring_router.router.routes[0].endpoint
            response = await endpoint_func()
            
            assert response.status_code == 200
            assert response.body.decode() == '{"overall_status":"healthy","timestamp":"' + mock_health_status["timestamp"] + '","checks":[],"summary":{"healthy":1},"uptime_seconds":3600.0}'
    
    @pytest.mark.asyncio
    async def test_health_check_endpoint_error(self, monitoring_router):
        """Test health check endpoint with error."""
        with patch('src.middleware.monitoring.get_health_status') as mock_get_health:
            mock_get_health.side_effect = Exception("Health check failed")
            
            # Mock the endpoint function
            endpoint_func = monitoring_router.router.routes[0].endpoint
            response = await endpoint_func()
            
            assert response.status_code == 500
            assert "error" in response.body.decode()
    
    @pytest.mark.asyncio
    async def test_liveness_check_endpoint(self, monitoring_router):
        """Test liveness check endpoint."""
        # Mock the endpoint function
        endpoint_func = monitoring_router.router.routes[1].endpoint
        response = await endpoint_func()
        
        assert response.status_code == 200
        response_data = response.body.decode()
        assert "status" in response_data
        assert "timestamp" in response_data
    
    @pytest.mark.asyncio
    async def test_readiness_check_endpoint_ready(self, monitoring_router):
        """Test readiness check endpoint when ready."""
        with patch('src.middleware.monitoring.get_health_checker') as mock_get_checker:
            # Mock health checker
            mock_checker = Mock()
            mock_db_check = Mock()
            mock_db_check.status.value = "healthy"
            mock_redis_check = Mock()
            mock_redis_check.status.value = "healthy"
            
            # Make the health checker methods async
            async def mock_check_database():
                return mock_db_check
            async def mock_check_redis():
                return mock_redis_check
            
            mock_checker.check_database = mock_check_database
            mock_checker.check_redis = mock_check_redis
            mock_get_checker.return_value = mock_checker
            
            # Mock the endpoint function
            endpoint_func = monitoring_router.router.routes[2].endpoint
            response = await endpoint_func()
            
            assert response.status_code == 200
            response_data = response.body.decode()
            assert "status" in response_data
            assert "ready" in response_data
    
    @pytest.mark.asyncio
    async def test_readiness_check_endpoint_not_ready(self, monitoring_router):
        """Test readiness check endpoint when not ready."""
        with patch('src.middleware.monitoring.get_health_checker') as mock_get_checker:
            # Mock health checker with unhealthy database
            mock_checker = Mock()
            mock_db_check = Mock()
            mock_db_check.status.value = "unhealthy"
            mock_checker.check_database.return_value = mock_db_check
            mock_get_checker.return_value = mock_checker
            
            # Mock the endpoint function
            endpoint_func = monitoring_router.router.routes[2].endpoint
            response = await endpoint_func()
            
            assert response.status_code == 503
            response_data = response.body.decode()
            assert "not_ready" in response_data
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, monitoring_router):
        """Test metrics endpoint."""
        with patch.object(monitoring_router, '_collect_system_metrics') as mock_collect:
            mock_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "system": {"cpu_percent": 30.0, "memory_percent": 50.0},
                "requests": {"total": 1000, "successful": 950},
                "jobs": {"active": 10, "completed": 500},
                "cache": {"hit_rate": 0.85},
                "errors": {"500": 5}
            }
            mock_collect.return_value = mock_metrics
            
            # Mock the endpoint function
            endpoint_func = monitoring_router.router.routes[3].endpoint
            response = await endpoint_func()
            
            assert response.status_code == 200
            response_data = response.body.decode()
            assert "timestamp" in response_data
            assert "system" in response_data
            assert "requests" in response_data
    
    @pytest.mark.asyncio
    async def test_request_metrics_endpoint(self, monitoring_router):
        """Test request metrics endpoint."""
        with patch.object(monitoring_router, '_collect_request_metrics') as mock_collect:
            mock_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "total_requests": 1000,
                "successful_requests": 950,
                "failed_requests": 50,
                "success_rate": 95.0,
                "response_time_percentiles": {"p50": 100.0, "p90": 200.0},
                "error_breakdown": {"500": 5, "404": 10}
            }
            mock_collect.return_value = mock_metrics
            
            # Mock the endpoint function
            endpoint_func = monitoring_router.router.routes[4].endpoint
            response = await endpoint_func()
            
            assert response.status_code == 200
            response_data = response.body.decode()
            assert "total_requests" in response_data
            assert "success_rate" in response_data
            assert "response_time_percentiles" in response_data
    
    @pytest.mark.asyncio
    async def test_job_metrics_endpoint(self, monitoring_router):
        """Test job metrics endpoint."""
        with patch.object(monitoring_router, '_collect_job_metrics') as mock_collect:
            mock_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "job_counts_by_status": {"running": 10, "completed": 500, "failed": 20},
                "recent_jobs_24h": 50,
                "total_jobs": 530
            }
            mock_collect.return_value = mock_metrics
            
            # Mock the endpoint function
            endpoint_func = monitoring_router.router.routes[5].endpoint
            response = await endpoint_func()
            
            assert response.status_code == 200
            response_data = response.body.decode()
            assert "job_counts_by_status" in response_data
            assert "recent_jobs_24h" in response_data
    
    @pytest.mark.asyncio
    async def test_cache_metrics_endpoint(self, monitoring_router):
        """Test cache metrics endpoint."""
        with patch.object(monitoring_router, '_collect_cache_metrics') as mock_collect:
            mock_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "cache_stats": {
                    "l1_cache": {"size": 100, "hits": 50},
                    "l2_cache": {"size": 200, "hits": 30}
                }
            }
            mock_collect.return_value = mock_metrics
            
            # Mock the endpoint function
            endpoint_func = monitoring_router.router.routes[6].endpoint
            response = await endpoint_func()
            
            assert response.status_code == 200
            response_data = response.body.decode()
            assert "cache_stats" in response_data
    
    @pytest.mark.asyncio
    async def test_collect_system_metrics(self, monitoring_router):
        """Test collecting system metrics."""
        with patch('src.middleware.monitoring.psutil') as mock_psutil, \
             patch.object(monitoring_router, '_collect_job_metrics') as mock_job_metrics, \
             patch.object(monitoring_router, '_collect_cache_metrics') as mock_cache_metrics:
            
            # Mock psutil
            mock_psutil.cpu_percent.return_value = 30.0
            mock_psutil.virtual_memory.return_value = Mock(
                percent=50.0,
                available=4 * 1024**3
            )
            mock_psutil.disk_usage.return_value = Mock(
                percent=60.0,
                free=10 * 1024**3
            )
            
            # Mock job and cache metrics
            mock_job_metrics.return_value = {"active_jobs": 10, "completed_jobs": 500}
            mock_cache_metrics.return_value = {"hit_rate": 0.85}
            
            # Set up global metrics
            _metrics_storage['total_requests'] = 1000
            _metrics_storage['successful_requests'] = 950
            _metrics_storage['failed_requests'] = 50
            _request_times.extend([100.0, 200.0, 150.0])
            _error_counts['500'] = 5
            
            metrics = await monitoring_router._collect_system_metrics()
            
            assert "timestamp" in metrics
            assert "system" in metrics
            assert "requests" in metrics
            assert "jobs" in metrics
            assert "cache" in metrics
            assert "errors" in metrics
            
            # Check system metrics
            assert metrics["system"]["cpu_percent"] == 30.0
            assert metrics["system"]["memory_percent"] == 50.0
            
            # Check request metrics
            assert metrics["requests"]["total"] == 1000
            assert metrics["requests"]["successful"] == 950
            assert metrics["requests"]["failed"] == 50
            assert metrics["requests"]["success_rate"] == 95.0
    
    @pytest.mark.asyncio
    async def test_collect_request_metrics(self, monitoring_router):
        """Test collecting request metrics."""
        # Set up global metrics
        _metrics_storage['total_requests'] = 1000
        _metrics_storage['successful_requests'] = 950
        _metrics_storage['failed_requests'] = 50
        _request_times.extend([100.0, 200.0, 150.0, 300.0, 250.0])
        _error_counts['500'] = 5
        _error_counts['404'] = 10
        
        metrics = await monitoring_router._collect_request_metrics()
        
        assert "timestamp" in metrics
        assert metrics["total_requests"] == 1000
        assert metrics["successful_requests"] == 950
        assert metrics["failed_requests"] == 50
        assert metrics["success_rate"] == 95.0
        assert "response_time_percentiles" in metrics
        assert "error_breakdown" in metrics
        
        # Check percentiles
        percentiles = metrics["response_time_percentiles"]
        assert "p50" in percentiles
        assert "p90" in percentiles
        assert "p95" in percentiles
        assert "p99" in percentiles
    
    @pytest.mark.asyncio
    async def test_collect_job_metrics(self, monitoring_router):
        """Test collecting job metrics."""
        with patch('src.middleware.monitoring.get_session') as mock_get_session:
            # Mock database session
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.count.return_value = 10
            mock_get_session.return_value.__enter__.return_value = mock_session
            
            metrics = await monitoring_router._collect_job_metrics()
            
            assert "timestamp" in metrics
            assert "job_counts_by_status" in metrics
            assert "recent_jobs_24h" in metrics
            assert "total_jobs" in metrics
    
    @pytest.mark.asyncio
    async def test_collect_cache_metrics(self, monitoring_router):
        """Test collecting cache metrics."""
        with patch('src.cache.cache_manager.get_cache') as mock_get_cache, \
             patch('src.cache.eviction_engine.CacheEvictionEngine') as mock_eviction_engine_class:
            
            # Mock cache and eviction engine
            mock_cache = AsyncMock()
            mock_eviction_engine = AsyncMock()
            mock_eviction_engine.get_cache_stats.return_value = {
                "l1_cache": {"size": 100, "hits": 50},
                "l2_cache": {"size": 200, "hits": 30}
            }
            mock_get_cache.return_value = mock_cache
            mock_eviction_engine_class.return_value = mock_eviction_engine
            
            metrics = await monitoring_router._collect_cache_metrics()
            
            assert "timestamp" in metrics
            assert "cache_stats" in metrics


class TestLoggingMiddleware:
    """Test logging middleware functionality."""
    
    @pytest.fixture
    def logging_middleware(self):
        """Create logging middleware instance."""
        return LoggingMiddleware(Mock())
    
    @pytest.mark.asyncio
    async def test_logging_middleware(self, logging_middleware):
        """Test logging middleware."""
        # Mock request and response
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        
        mock_response = Mock()
        mock_response.status_code = 200
        
        # Mock call_next
        call_next = AsyncMock(return_value=mock_response)
        
        response = await logging_middleware.dispatch(mock_request, call_next)
        
        assert response == mock_response
        call_next.assert_called_once_with(mock_request)


class TestErrorHandlingMiddleware:
    """Test error handling middleware functionality."""
    
    @pytest.fixture
    def error_middleware(self):
        """Create error handling middleware instance."""
        return ErrorHandlingMiddleware(Mock())
    
    @pytest.mark.asyncio
    async def test_error_handling_middleware_success(self, error_middleware):
        """Test error handling middleware with successful request."""
        # Mock request and response
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        
        mock_response = Mock()
        mock_response.status_code = 200
        
        # Mock call_next
        call_next = AsyncMock(return_value=mock_response)
        
        response = await error_middleware.dispatch(mock_request, call_next)
        
        assert response == mock_response
        call_next.assert_called_once_with(mock_request)
    
    @pytest.mark.asyncio
    async def test_error_handling_middleware_error(self, error_middleware):
        """Test error handling middleware with error."""
        # Mock request
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        
        # Mock call_next to raise exception
        call_next = AsyncMock(side_effect=Exception("Test error"))
        
        # Clear error counts
        _error_counts.clear()
        
        response = await error_middleware.dispatch(mock_request, call_next)
        
        assert response.status_code == 500
        assert _error_counts["500"] == 1
        
        # Check response body
        response_data = response.body.decode()
        assert "error" in response_data
        assert "Internal server error" in response_data


@pytest.mark.asyncio
async def test_integration_monitoring():
    """Integration test for monitoring system."""
    # This would test the complete monitoring system with actual services
    pass
