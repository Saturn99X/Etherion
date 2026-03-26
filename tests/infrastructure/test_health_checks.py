"""
Tests for health checks and monitoring functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from src.core.health import (
    HealthChecker,
    HealthStatus,
    HealthCheck,
    HealthReport,
    get_health_status
)


class TestHealthChecker:
    """Test health checker functionality."""
    
    @pytest.fixture
    def health_checker(self):
        """Create health checker instance."""
        return HealthChecker()
    
    @pytest.mark.asyncio
    async def test_check_database_healthy(self, health_checker):
        """Test healthy database check."""
        with patch('src.core.health.get_session') as mock_get_session, \
             patch('src.core.health.engine') as mock_engine:
            
            # Mock database session
            mock_session = Mock()
            mock_session.execute.return_value.fetchone.return_value = (1,)
            mock_session.query.return_value.count.return_value = 10
            mock_get_session.return_value.__enter__.return_value = mock_session
            
            # Mock engine
            mock_engine.pool.size.return_value = 10
            mock_engine.pool.checkedout.return_value = 2
            
            check = await health_checker.check_database()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "database"
            assert check.status == HealthStatus.HEALTHY
            assert "Database is accessible" in check.message
            assert check.response_time_ms > 0
            assert check.details is not None
            assert "user_count" in check.details
            assert "tenant_count" in check.details
    
    @pytest.mark.asyncio
    async def test_check_database_unhealthy(self, health_checker):
        """Test unhealthy database check."""
        with patch('src.core.health.get_session') as mock_get_session:
            # Mock database error
            mock_get_session.side_effect = Exception("Database connection failed")
            
            check = await health_checker.check_database()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "database"
            assert check.status == HealthStatus.UNHEALTHY
            assert "Database check failed" in check.message
            assert check.error is not None
    
    @pytest.mark.asyncio
    async def test_check_redis_healthy(self, health_checker):
        """Test healthy Redis check."""
        with patch('src.core.health.get_redis_client') as mock_get_redis:
            # Mock Redis client
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            
            # Store the test value to return it later
            stored_value = None
            def set_side_effect(key, value, ex=None):
                nonlocal stored_value
                stored_value = value
                return True
            mock_redis.set.side_effect = set_side_effect
            
            def get_side_effect(key):
                if key == "health_check_test":
                    return stored_value
                return None
            mock_redis.get.side_effect = get_side_effect
            
            mock_redis.delete.return_value = 1
            mock_redis.info.return_value = {
                "redis_version": "6.2.0",
                "used_memory": 1024000,
                "connected_clients": 5,
                "total_commands_processed": 1000
            }
            # Mock get_redis_client to return the mock redis client
            async def mock_get_redis_client():
                return mock_redis
            mock_get_redis.side_effect = mock_get_redis_client
            
            check = await health_checker.check_redis()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "redis"
            assert check.status == HealthStatus.HEALTHY
            assert "Redis is accessible" in check.message
            assert check.details is not None
            assert "version" in check.details
            assert "used_memory" in check.details
    
    @pytest.mark.asyncio
    async def test_check_redis_unhealthy(self, health_checker):
        """Test unhealthy Redis check."""
        with patch('src.core.health.get_redis_client') as mock_get_redis:
            # Mock Redis error
            mock_get_redis.side_effect = Exception("Redis connection failed")
            
            check = await health_checker.check_redis()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "redis"
            assert check.status == HealthStatus.UNHEALTHY
            assert "Redis check failed" in check.message
            assert check.error is not None
    
    @pytest.mark.asyncio
    async def test_check_cache_system_healthy(self, health_checker):
        """Test healthy cache system check."""
        with patch('src.core.health.get_cache') as mock_get_cache:
            # Mock cache
            mock_cache = AsyncMock()
            
            # Store the test value to return it later
            stored_value = None
            def set_side_effect(key, value, ttl=None):
                nonlocal stored_value
                stored_value = value
                return None
            mock_cache.set.side_effect = set_side_effect
            
            def get_side_effect(key):
                if key.startswith("health_check_"):
                    return stored_value
                return None
            mock_cache.get.side_effect = get_side_effect
            
            mock_cache.delete.return_value = True
            mock_cache.get_stats.return_value = {
                "l1": {"size": 100, "hits": 50, "misses": 10},
                "l2": {"size": 200, "hits": 30, "misses": 5}
            }
            # Mock get_cache to return the mock cache
            async def mock_get_cache_func():
                return mock_cache
            mock_get_cache.side_effect = mock_get_cache_func
            
            check = await health_checker.check_cache_system()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "cache_system"
            assert check.status == HealthStatus.HEALTHY
            assert "Cache system is operational" in check.message
            assert check.details is not None
    
    @pytest.mark.asyncio
    async def test_check_celery_workers_healthy(self, health_checker):
        """Test healthy Celery workers check."""
        with patch('src.core.health.celery_app') as mock_celery_app:
            # Mock Celery inspect
            mock_inspect = Mock()
            mock_inspect.active.return_value = {
                "worker1@host": ["task1", "task2"],
                "worker2@host": ["task3"]
            }
            mock_inspect.stats.return_value = {
                "worker1@host": {"total": {"task1": 10, "task2": 5}},
                "worker2@host": {"total": {"task3": 8}}
            }
            mock_inspect.registered.return_value = {
                "worker1@host": ["task1", "task2", "task3"],
                "worker2@host": ["task1", "task2", "task3"]
            }
            mock_celery_app.control.inspect.return_value = mock_inspect
            
            check = await health_checker.check_celery_workers()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "celery_workers"
            assert check.status == HealthStatus.HEALTHY
            assert "Found 2 active workers" in check.message
            assert check.details is not None
            assert "active_workers" in check.details
            assert "worker_count" in check.details
    
    @pytest.mark.asyncio
    async def test_check_celery_workers_unhealthy(self, health_checker):
        """Test unhealthy Celery workers check."""
        with patch('src.core.health.celery_app') as mock_celery_app:
            # Mock Celery inspect with no workers
            mock_inspect = Mock()
            mock_inspect.active.return_value = {}
            mock_celery_app.control.inspect.return_value = mock_inspect
            
            check = await health_checker.check_celery_workers()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "celery_workers"
            assert check.status == HealthStatus.UNHEALTHY
            assert "No active Celery workers found" in check.message
    
    @pytest.mark.asyncio
    async def test_check_gcs_connectivity_healthy(self, health_checker):
        """Test healthy GCS connectivity check."""
        with patch('src.core.health.GCSClient') as mock_gcs_class:
            # Mock GCS client
            mock_gcs = Mock()
            mock_gcs_class.return_value = mock_gcs
            
            check = await health_checker.check_gcs_connectivity()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "gcs_connectivity"
            assert check.status == HealthStatus.HEALTHY
            assert "GCS client initialized successfully" in check.message
            assert check.details is not None
            assert "client_initialized" in check.details
    
    @pytest.mark.asyncio
    async def test_check_external_services_healthy(self, health_checker):
        """Test healthy external services check."""
        with patch.object(health_checker, '_check_http_service') as mock_check_service:
            # Mock all services as healthy
            mock_check_service.return_value = True
            
            check = await health_checker.check_external_services()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "external_services"
            assert check.status == HealthStatus.HEALTHY
            assert "All 2 external services are healthy" in check.message
            assert check.details is not None
            assert "openai_api" in check.details
            assert "google_ai" in check.details
    
    @pytest.mark.asyncio
    async def test_check_external_services_degraded(self, health_checker):
        """Test degraded external services check."""
        with patch.object(health_checker, '_check_http_service') as mock_check_service:
            # Mock one service as unhealthy
            def mock_check(url, timeout=5):
                return "openai" in url  # Only OpenAI is healthy
            
            mock_check_service.side_effect = mock_check
            
            check = await health_checker.check_external_services()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "external_services"
            assert check.status == HealthStatus.DEGRADED
            assert "1/2 external services are healthy" in check.message
    
    @pytest.mark.asyncio
    async def test_check_system_resources_healthy(self, health_checker):
        """Test healthy system resources check."""
        with patch('src.core.health.psutil') as mock_psutil:
            # Mock system resources as healthy
            mock_psutil.cpu_percent.return_value = 30.0
            mock_psutil.virtual_memory.return_value = Mock(
                percent=40.0,
                available=4 * 1024**3  # 4GB
            )
            mock_psutil.disk_usage.return_value = Mock(
                percent=50.0,
                free=10 * 1024**3  # 10GB
            )
            
            check = await health_checker.check_system_resources()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "system_resources"
            assert check.status == HealthStatus.HEALTHY
            assert "System resources are normal" in check.message
            assert check.details is not None
            assert "cpu_percent" in check.details
            assert "memory_percent" in check.details
            assert "disk_percent" in check.details
    
    @pytest.mark.asyncio
    async def test_check_system_resources_degraded(self, health_checker):
        """Test degraded system resources check."""
        with patch('builtins.__import__') as mock_import:
            # Mock psutil import
            mock_psutil = Mock()
            mock_psutil.cpu_percent.return_value = 80.0
            mock_psutil.virtual_memory.return_value = Mock(
                percent=75.0,
                available=1 * 1024**3  # 1GB
            )
            mock_psutil.disk_usage.return_value = Mock(
                percent=60.0,
                free=5 * 1024**3  # 5GB
            )
            
            def import_side_effect(name, *args, **kwargs):
                if name == 'psutil':
                    return mock_psutil
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            check = await health_checker.check_system_resources()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "system_resources"
            assert check.status == HealthStatus.DEGRADED
            assert "System resources are elevated" in check.message
    
    @pytest.mark.asyncio
    async def test_check_system_resources_unhealthy(self, health_checker):
        """Test unhealthy system resources check."""
        with patch('builtins.__import__') as mock_import:
            # Mock psutil import
            mock_psutil = Mock()
            mock_psutil.cpu_percent.return_value = 95.0
            mock_psutil.virtual_memory.return_value = Mock(
                percent=95.0,
                available=0.1 * 1024**3  # 100MB
            )
            mock_psutil.disk_usage.return_value = Mock(
                percent=95.0,
                free=0.1 * 1024**3  # 100MB
            )
            
            def import_side_effect(name, *args, **kwargs):
                if name == 'psutil':
                    return mock_psutil
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            check = await health_checker.check_system_resources()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "system_resources"
            assert check.status == HealthStatus.UNHEALTHY
            assert "System resources are critically high" in check.message
    
    @pytest.mark.asyncio
    async def test_check_system_resources_no_psutil(self, health_checker):
        """Test system resources check without psutil."""
        with patch('builtins.__import__') as mock_import:
            def import_side_effect(name, *args, **kwargs):
                if name == 'psutil':
                    raise ImportError("No module named 'psutil'")
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            check = await health_checker.check_system_resources()
            
            assert isinstance(check, HealthCheck)
            assert check.name == "system_resources"
            assert check.status == HealthStatus.UNKNOWN
            assert "psutil not installed" in check.message
    
    @pytest.mark.asyncio
    async def test_run_all_checks_healthy(self, health_checker):
        """Test running all checks with healthy results."""
        # Mock all checks to return healthy status
        with patch.object(health_checker, 'check_database', return_value=HealthCheck(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database is healthy",
            response_time_ms=10.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_redis', return_value=HealthCheck(
            name="redis",
            status=HealthStatus.HEALTHY,
            message="Redis is healthy",
            response_time_ms=5.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_cache_system', return_value=HealthCheck(
            name="cache_system",
            status=HealthStatus.HEALTHY,
            message="Cache system is healthy",
            response_time_ms=3.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_celery_workers', return_value=HealthCheck(
            name="celery_workers",
            status=HealthStatus.HEALTHY,
            message="Celery workers are healthy",
            response_time_ms=2.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_gcs_connectivity', return_value=HealthCheck(
            name="gcs_connectivity",
            status=HealthStatus.HEALTHY,
            message="GCS connectivity is healthy",
            response_time_ms=15.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_external_services', return_value=HealthCheck(
            name="external_services",
            status=HealthStatus.HEALTHY,
            message="External services are healthy",
            response_time_ms=8.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_system_resources', return_value=HealthCheck(
            name="system_resources",
            status=HealthStatus.HEALTHY,
            message="System resources are healthy",
            response_time_ms=1.0,
            timestamp=datetime.utcnow()
        )):
            
            report = await health_checker.run_all_checks()
            
            assert isinstance(report, HealthReport)
            assert report.overall_status == HealthStatus.HEALTHY
            assert len(report.checks) == 7
            assert report.summary[HealthStatus.HEALTHY] == 7
            assert report.uptime_seconds > 0
            assert report.version == "1.0.0"
    
    @pytest.mark.asyncio
    async def test_run_all_checks_mixed(self, health_checker):
        """Test running all checks with mixed results."""
        # Mock checks to return mixed statuses
        with patch.object(health_checker, 'check_database', return_value=HealthCheck(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database is healthy",
            response_time_ms=10.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_redis', return_value=HealthCheck(
            name="redis",
            status=HealthStatus.HEALTHY,
            message="Redis is healthy",
            response_time_ms=5.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_cache_system', return_value=HealthCheck(
            name="cache_system",
            status=HealthStatus.DEGRADED,
            message="Cache system is degraded",
            response_time_ms=3.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_celery_workers', return_value=HealthCheck(
            name="celery_workers",
            status=HealthStatus.HEALTHY,
            message="Celery workers are healthy",
            response_time_ms=2.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_gcs_connectivity', return_value=HealthCheck(
            name="gcs_connectivity",
            status=HealthStatus.HEALTHY,
            message="GCS connectivity is healthy",
            response_time_ms=15.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_external_services', return_value=HealthCheck(
            name="external_services",
            status=HealthStatus.HEALTHY,
            message="External services are healthy",
            response_time_ms=8.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_system_resources', return_value=HealthCheck(
            name="system_resources",
            status=HealthStatus.HEALTHY,
            message="System resources are healthy",
            response_time_ms=1.0,
            timestamp=datetime.utcnow()
        )):
            
            report = await health_checker.run_all_checks()
            
            assert isinstance(report, HealthReport)
            assert report.overall_status == HealthStatus.DEGRADED
            assert len(report.checks) == 7
            assert report.summary[HealthStatus.HEALTHY] == 6
            assert report.summary[HealthStatus.DEGRADED] == 1
    
    @pytest.mark.asyncio
    async def test_run_all_checks_unhealthy(self, health_checker):
        """Test running all checks with unhealthy results."""
        # Mock checks to return unhealthy status
        with patch.object(health_checker, 'check_database', return_value=HealthCheck(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message="Database is unhealthy",
            response_time_ms=10.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_redis', return_value=HealthCheck(
            name="redis",
            status=HealthStatus.HEALTHY,
            message="Redis is healthy",
            response_time_ms=5.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_cache_system', return_value=HealthCheck(
            name="cache_system",
            status=HealthStatus.HEALTHY,
            message="Cache system is healthy",
            response_time_ms=3.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_celery_workers', return_value=HealthCheck(
            name="celery_workers",
            status=HealthStatus.HEALTHY,
            message="Celery workers are healthy",
            response_time_ms=2.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_gcs_connectivity', return_value=HealthCheck(
            name="gcs_connectivity",
            status=HealthStatus.HEALTHY,
            message="GCS connectivity is healthy",
            response_time_ms=15.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_external_services', return_value=HealthCheck(
            name="external_services",
            status=HealthStatus.HEALTHY,
            message="External services are healthy",
            response_time_ms=8.0,
            timestamp=datetime.utcnow()
        )), \
        patch.object(health_checker, 'check_system_resources', return_value=HealthCheck(
            name="system_resources",
            status=HealthStatus.HEALTHY,
            message="System resources are healthy",
            response_time_ms=1.0,
            timestamp=datetime.utcnow()
        )):
            
            report = await health_checker.run_all_checks()
            
            assert isinstance(report, HealthReport)
            assert report.overall_status == HealthStatus.UNHEALTHY
            assert len(report.checks) == 7
            assert report.summary[HealthStatus.HEALTHY] == 6
            assert report.summary[HealthStatus.UNHEALTHY] == 1


class TestHealthStatus:
    """Test health status enumeration."""
    
    def test_health_status_values(self):
        """Test health status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthCheck:
    """Test health check data structure."""
    
    def test_health_check_creation(self):
        """Test creating health check."""
        check = HealthCheck(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="Test message",
            response_time_ms=100.0,
            timestamp=datetime.utcnow(),
            details={"key": "value"}
        )
        
        assert check.name == "test_check"
        assert check.status == HealthStatus.HEALTHY
        assert check.message == "Test message"
        assert check.response_time_ms == 100.0
        assert check.details == {"key": "value"}


class TestHealthReport:
    """Test health report data structure."""
    
    def test_health_report_creation(self):
        """Test creating health report."""
        checks = [
            HealthCheck(
                name="test1",
                status=HealthStatus.HEALTHY,
                message="Test 1",
                response_time_ms=100.0,
                timestamp=datetime.utcnow()
            ),
            HealthCheck(
                name="test2",
                status=HealthStatus.HEALTHY,
                message="Test 2",
                response_time_ms=200.0,
                timestamp=datetime.utcnow()
            )
        ]
        
        report = HealthReport(
            overall_status=HealthStatus.HEALTHY,
            timestamp=datetime.utcnow(),
            checks=checks,
            summary={HealthStatus.HEALTHY: 2},
            uptime_seconds=3600.0
        )
        
        assert report.overall_status == HealthStatus.HEALTHY
        assert len(report.checks) == 2
        assert report.summary[HealthStatus.HEALTHY] == 2
        assert report.uptime_seconds == 3600.0


@pytest.mark.asyncio
async def test_get_health_status():
    """Test getting health status."""
    with patch('src.core.health.get_health_checker') as mock_get_checker:
        # Mock health checker
        mock_checker = Mock()
        mock_report = HealthReport(
            overall_status=HealthStatus.HEALTHY,
            timestamp=datetime.utcnow(),
            checks=[],
            summary={HealthStatus.HEALTHY: 1},
            uptime_seconds=3600.0
        )
        # Make run_all_checks return a coroutine
        async def mock_run_all_checks():
            return mock_report
        mock_checker.run_all_checks = mock_run_all_checks
        mock_get_checker.return_value = mock_checker
    
        status = await get_health_status()
        
        assert isinstance(status, dict)
        assert "overall_status" in status
        assert "timestamp" in status
        assert "checks" in status
        assert "summary" in status
        assert "uptime_seconds" in status


@pytest.mark.asyncio
async def test_integration_health_checks():
    """Integration test for health checks."""
    # This would test health checks with actual services running
    pass
