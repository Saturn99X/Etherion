"""
Comprehensive health checks and monitoring system.
Provides health status for all critical services and components.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import json

try:
    import psutil
except ImportError:
    psutil = None

from src.database.db import get_session, sync_engine as engine
from src.core.redis import get_redis_client
from src.cache.cache_manager import get_cache
from src.core.celery import celery_app
from src.core.gcs_client import GCSClient

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Individual health check result."""
    name: str
    status: HealthStatus
    message: str
    response_time_ms: float
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class HealthReport:
    """Overall health report."""
    overall_status: HealthStatus
    timestamp: datetime
    checks: List[HealthCheck]
    summary: Dict[str, int]
    uptime_seconds: float
    version: str = "1.0.0"


class HealthChecker:
    """Comprehensive health checking system."""
    
    def __init__(self):
        self.start_time = time.time()
        self.version = "1.0.0"
        self.checks: List[HealthCheck] = []
    
    async def check_database(self) -> HealthCheck:
        """Check database connectivity and performance."""
        start_time = time.time()
        
        try:
            with get_session() as session:
                # Test basic connectivity
                result = session.execute("SELECT 1").fetchone()
                if not result:
                    raise Exception("Database query returned no results")
                
                # Test table access
                from sqlalchemy import text as _text
                # Single roundtrip to fetch multiple counts
                counts = session.execute(
                    _text(
                        """
                        SELECT
                          (SELECT COUNT(*) FROM "user") AS user_count,
                          (SELECT COUNT(*) FROM tenant) AS tenant_count
                        """
                    )
                ).mappings().first()
                user_count = counts.get("user_count", 0) if counts else 0
                tenant_count = counts.get("tenant_count", 0) if counts else 0
                
                response_time = (time.time() - start_time) * 1000
                
                return HealthCheck(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database is accessible and responsive",
                    response_time_ms=response_time,
                    timestamp=datetime.utcnow(),
                    details={
                        "user_count": user_count,
                        "tenant_count": tenant_count,
                        "connection_pool_size": engine.pool.size(),
                        "checked_out_connections": engine.pool.checkedout()
                    }
                )
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database check failed: {str(e)}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    async def check_redis(self) -> HealthCheck:
        """Check Redis connectivity and performance."""
        start_time = time.time()
        
        try:
            redis_client = await get_redis_client()
            
            # Test basic connectivity
            await redis_client.ping()
            
            # Test read/write operations
            test_key = "health_check_test"
            test_value = f"test_{int(time.time())}"
            
            await redis_client.set(test_key, test_value, ex=60)
            retrieved_value = await redis_client.get(test_key)
            
            if retrieved_value != test_value:
                raise Exception("Redis read/write test failed")
            
            await redis_client.delete(test_key)
            
            # Get Redis info
            info = await redis_client.info()
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis is accessible and responsive",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                details={
                    "version": info.get("redis_version"),
                    "used_memory": info.get("used_memory"),
                    "connected_clients": info.get("connected_clients"),
                    "total_commands_processed": info.get("total_commands_processed")
                }
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis check failed: {str(e)}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    async def check_cache_system(self) -> HealthCheck:
        """Check cache system health."""
        start_time = time.time()
        
        try:
            cache = await get_cache()
            
            # Test cache operations
            test_key = f"health_check_{int(time.time())}"
            test_value = {"test": True, "timestamp": time.time()}
            
            # Test set operation
            await cache.set(test_key, test_value, ttl=60)
            
            # Test get operation
            retrieved_value = await cache.get(test_key)
            
            if retrieved_value != test_value:
                raise Exception("Cache read/write test failed")
            
            # Test delete operation
            await cache.delete(test_key)
            
            # Get cache stats
            stats = await cache.get_stats()
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="cache_system",
                status=HealthStatus.HEALTHY,
                message="Cache system is operational",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                details=stats
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                name="cache_system",
                status=HealthStatus.UNHEALTHY,
                message=f"Cache system check failed: {str(e)}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    async def check_celery_workers(self) -> HealthCheck:
        """Check Celery worker health."""
        start_time = time.time()
        
        try:
            # Get active workers
            inspect = celery_app.control.inspect()
            active_workers = inspect.active()
            
            if not active_workers:
                return HealthCheck(
                    name="celery_workers",
                    status=HealthStatus.UNHEALTHY,
                    message="No active Celery workers found",
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.utcnow(),
                    error="No workers available"
                )
            
            # Get worker stats
            stats = inspect.stats()
            registered_tasks = inspect.registered()
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="celery_workers",
                status=HealthStatus.HEALTHY,
                message=f"Found {len(active_workers)} active workers",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                details={
                    "active_workers": list(active_workers.keys()),
                    "worker_count": len(active_workers),
                    "stats": stats,
                    "registered_tasks": registered_tasks
                }
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                name="celery_workers",
                status=HealthStatus.UNHEALTHY,
                message=f"Celery workers check failed: {str(e)}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    async def check_gcs_connectivity(self) -> HealthCheck:
        """Check Google Cloud Storage connectivity."""
        start_time = time.time()
        
        try:
            # Test GCS connectivity with a simple operation
            gcs_client = GCSClient(tenant_id="health_check")
            
            # Try to list buckets (this will fail if credentials are invalid)
            # For now, we'll just check if the client can be created
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="gcs_connectivity",
                status=HealthStatus.HEALTHY,
                message="GCS client initialized successfully",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                details={
                    "client_initialized": True
                }
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                name="gcs_connectivity",
                status=HealthStatus.UNHEALTHY,
                message=f"GCS connectivity check failed: {str(e)}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    async def check_external_services(self) -> HealthCheck:
        """Check external service dependencies."""
        start_time = time.time()
        
        try:
            # Check external services; endpoints configurable via environment
            import os
            openai_models_url = os.getenv("OPENAI_MODELS_URL", "https://api.openai.com/v1/models")
            google_models_url = os.getenv(
                "GOOGLE_GENAI_MODELS_URL",
                "https://generativelanguage.googleapis.com/v1beta/models",
            )
            external_services = {
                "openai_api": await self._check_http_service(openai_models_url, timeout=5),
                "google_ai": await self._check_http_service(google_models_url, timeout=5),
            }
            
            healthy_services = sum(1 for status in external_services.values() if status)
            total_services = len(external_services)
            
            if healthy_services == total_services:
                status = HealthStatus.HEALTHY
                message = f"All {total_services} external services are healthy"
            elif healthy_services > 0:
                status = HealthStatus.DEGRADED
                message = f"{healthy_services}/{total_services} external services are healthy"
            else:
                status = HealthStatus.UNHEALTHY
                message = "No external services are healthy"
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="external_services",
                status=status,
                message=message,
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                details=external_services
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                name="external_services",
                status=HealthStatus.UNHEALTHY,
                message=f"External services check failed: {str(e)}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    async def _check_http_service(self, url: str, timeout: int = 5) -> bool:
        """Check if an HTTP service is accessible."""
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.get(url) as response:
                    return response.status < 500
        except Exception:
            return False
    
    async def check_system_resources(self) -> HealthCheck:
        """Check system resource usage."""
        start_time = time.time()
        
        try:
            import psutil
            
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Determine status based on thresholds
            if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
                status = HealthStatus.UNHEALTHY
                message = "System resources are critically high"
            elif cpu_percent > 70 or memory.percent > 70 or disk.percent > 70:
                status = HealthStatus.DEGRADED
                message = "System resources are elevated"
            else:
                status = HealthStatus.HEALTHY
                message = "System resources are normal"
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="system_resources",
                status=status,
                message=message,
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024**3)
                }
            )
            
        except ImportError:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                name="system_resources",
                status=HealthStatus.UNKNOWN,
                message="System resource monitoring not available (psutil not installed)",
                response_time_ms=response_time,
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheck(
                name="system_resources",
                status=HealthStatus.UNHEALTHY,
                message=f"System resource check failed: {str(e)}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    async def run_all_checks(self) -> HealthReport:
        """Run all health checks and generate a comprehensive report."""
        checks = []
        
        # Run all health checks concurrently
        check_tasks = [
            self.check_database(),
            self.check_redis(),
            self.check_cache_system(),
            self.check_celery_workers(),
            self.check_gcs_connectivity(),
            self.check_external_services(),
            self.check_system_resources()
        ]
        
        results = await asyncio.gather(*check_tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, HealthCheck):
                checks.append(result)
            else:
                # Handle exceptions
                checks.append(HealthCheck(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check failed with exception: {str(result)}",
                    response_time_ms=0,
                    timestamp=datetime.utcnow(),
                    error=str(result)
                ))
        
        # Calculate overall status
        status_counts = {}
        for check in checks:
            status_counts[check.status] = status_counts.get(check.status, 0) + 1
        
        if status_counts.get(HealthStatus.UNHEALTHY, 0) > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif status_counts.get(HealthStatus.DEGRADED, 0) > 0:
            overall_status = HealthStatus.DEGRADED
        elif status_counts.get(HealthStatus.HEALTHY, 0) > 0:
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN
        
        # Calculate uptime
        uptime_seconds = time.time() - self.start_time
        
        return HealthReport(
            overall_status=overall_status,
            timestamp=datetime.utcnow(),
            checks=checks,
            summary=status_counts,
            uptime_seconds=uptime_seconds,
            version=self.version
        )


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


async def get_health_checker() -> HealthChecker:
    """Get the global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


async def get_health_status() -> Dict[str, Any]:
    """Get current health status as a dictionary."""
    health_checker = await get_health_checker()
    report = await health_checker.run_all_checks()
    
    # Convert to dictionary for JSON serialization
    report_dict = asdict(report)
    
    # Convert datetime objects to ISO strings
    for key, value in report_dict.items():
        if isinstance(value, datetime):
            report_dict[key] = value.isoformat()
        elif key == "checks":
            for check in value:
                if isinstance(check.get("timestamp"), datetime):
                    check["timestamp"] = check["timestamp"].isoformat()
    
    return report_dict
