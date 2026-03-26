"""
Monitoring middleware and endpoints for system observability.
Provides metrics collection, logging, and monitoring endpoints.
"""

import time
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import json

from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.core.health import get_health_status, HealthChecker, get_health_checker
from src.core.redis import get_redis_client
from src.database.db import get_session
from src.database.models import Job, JobStatus

# Import psutil for system metrics
try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)

# Add missing functions for compatibility
async def get_cache():
    """Get cache instance for monitoring."""
    from src.cache.cache_manager import get_cache as _get_cache
    return await _get_cache()

# Import CacheEvictionEngine for monitoring
from src.cache.eviction_engine import CacheEvictionEngine

# Global metrics storage
_metrics_storage: Dict[str, int] = defaultdict(int)
_request_times: deque = deque(maxlen=1000)
_error_counts: Dict[str, int] = defaultdict(int)


@dataclass
class RequestMetrics:
    """Request metrics data."""
    method: str
    path: str
    status_code: int
    response_time_ms: float
    timestamp: datetime
    user_id: Optional[str] = None
    tenant_id: Optional[int] = None


@dataclass
class SystemMetrics:
    """System metrics data."""
    timestamp: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time_ms: float
    active_jobs: int
    completed_jobs: int
    failed_jobs: int
    cache_hit_rate: float
    memory_usage_mb: float
    cpu_usage_percent: float


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting request metrics."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.metrics_enabled = True
    
    async def dispatch(self, request: Request, call_next):
        """Process request and collect metrics."""
        if not self.metrics_enabled:
            return await call_next(request)
        
        start_time = time.time()
        
        # Extract request information
        method = request.method
        path = request.url.path
        user_id = getattr(request.state, 'user', None)
        tenant_id = getattr(request.state, 'tenant', None)
        
        # Process request
        response = await call_next(request)
        
        # Calculate metrics
        response_time = (time.time() - start_time) * 1000
        status_code = response.status_code
        
        # Create metrics record
        metrics = RequestMetrics(
            method=method,
            path=path,
            status_code=status_code,
            response_time_ms=response_time,
            timestamp=datetime.utcnow(),
            user_id=user_id.user_id if user_id else None,
            tenant_id=tenant_id.id if tenant_id else None
        )
        
        # Store metrics
        await self._store_metrics(metrics)
        
        return response
    
    async def _store_metrics(self, metrics: RequestMetrics):
        """Store request metrics."""
        # Store in memory
        _request_times.append(metrics.response_time_ms)
        
        # Update counters
        _metrics_storage['total_requests'] += 1
        
        if 200 <= metrics.status_code < 400:
            _metrics_storage['successful_requests'] += 1
        else:
            _metrics_storage['failed_requests'] += 1
            _error_counts[f"{metrics.status_code}"] += 1
        
        # Store in Redis for persistence
        try:
            redis_client = await get_redis_client()
            metrics_key = f"metrics:request:{int(time.time())}"
            metrics_data = asdict(metrics)
            metrics_data['timestamp'] = metrics_data['timestamp'].isoformat()
            
            await redis_client.setex(metrics_key, 3600, json.dumps(metrics_data))  # 1 hour TTL
        except Exception as e:
            logger.warning(f"Failed to store metrics in Redis: {e}")


class MonitoringRouter:
    """Router for monitoring endpoints."""
    
    def __init__(self):
        self.router = APIRouter(prefix="/monitoring", tags=["monitoring"])
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup monitoring routes."""
        
        @self.router.get("/health")
        async def health_check():
            """Get comprehensive health status."""
            try:
                health_status = await get_health_status()
                return JSONResponse(content=health_status)
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return JSONResponse(
                    content={"error": "Health check failed", "details": str(e)},
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        @self.router.get("/health/live")
        async def liveness_check():
            """Simple liveness check."""
            return JSONResponse(content={"status": "alive", "timestamp": datetime.utcnow().isoformat()})
        
        @self.router.get("/health/ready")
        async def readiness_check():
            """Readiness check for Kubernetes."""
            try:
                # Check critical dependencies
                health_checker = await get_health_checker()
                
                # Quick database check
                db_check = await health_checker.check_database()
                if db_check.status.value != "healthy":
                    return JSONResponse(
                        content={"status": "not_ready", "reason": "database_unhealthy"},
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
                
                # Quick Redis check
                redis_check = await health_checker.check_redis()
                if redis_check.status.value != "healthy":
                    return JSONResponse(
                        content={"status": "not_ready", "reason": "redis_unhealthy"},
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
                
                return JSONResponse(content={"status": "ready", "timestamp": datetime.utcnow().isoformat()})
                
            except Exception as e:
                logger.error(f"Readiness check failed: {e}")
                return JSONResponse(
                    content={"status": "not_ready", "reason": str(e)},
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        
        @self.router.get("/metrics")
        async def get_metrics():
            """Get system metrics."""
            try:
                metrics = await self._collect_system_metrics()
                return JSONResponse(content=metrics)
            except Exception as e:
                logger.error(f"Failed to collect metrics: {e}")
                return JSONResponse(
                    content={"error": "Failed to collect metrics", "details": str(e)},
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        @self.router.get("/metrics/requests")
        async def get_request_metrics():
            """Get request metrics."""
            try:
                request_metrics = await self._collect_request_metrics()
                return JSONResponse(content=request_metrics)
            except Exception as e:
                logger.error(f"Failed to collect request metrics: {e}")
                return JSONResponse(
                    content={"error": "Failed to collect request metrics", "details": str(e)},
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        @self.router.get("/metrics/jobs")
        async def get_job_metrics():
            """Get job-related metrics."""
            try:
                job_metrics = await self._collect_job_metrics()
                return JSONResponse(content=job_metrics)
            except Exception as e:
                logger.error(f"Failed to collect job metrics: {e}")
                return JSONResponse(
                    content={"error": "Failed to collect job metrics", "details": str(e)},
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        @self.router.get("/metrics/cache")
        async def get_cache_metrics():
            """Get cache metrics."""
            try:
                cache_metrics = await self._collect_cache_metrics()
                return JSONResponse(content=cache_metrics)
            except Exception as e:
                logger.error(f"Failed to collect cache metrics: {e}")
                return JSONResponse(
                    content={"error": "Failed to collect cache metrics", "details": str(e)},
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        @self.router.get("/logs/recent")
        async def get_recent_logs(limit: int = 100):
            """Get recent application logs."""
            try:
                # This would typically read from log files or a log aggregation service
                # For now, we'll return a placeholder
                return JSONResponse(content={
                    "message": "Log retrieval not implemented",
                    "limit": limit,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                logger.error(f"Failed to retrieve logs: {e}")
                return JSONResponse(
                    content={"error": "Failed to retrieve logs", "details": str(e)},
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
    
    async def _collect_system_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive system metrics."""
        try:
            if psutil is None:
                raise ImportError("psutil not available")
            
            # System resource metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Request metrics
            total_requests = _metrics_storage['total_requests']
            successful_requests = _metrics_storage['successful_requests']
            failed_requests = _metrics_storage['failed_requests']
            
            # Calculate average response time
            avg_response_time = sum(_request_times) / len(_request_times) if _request_times else 0
            
            # Job metrics
            job_metrics = await self._collect_job_metrics()
            
            # Cache metrics
            cache_metrics = await self._collect_cache_metrics()
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "system": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024**3)
                },
                "requests": {
                    "total": total_requests,
                    "successful": successful_requests,
                    "failed": failed_requests,
                    "success_rate": (successful_requests / total_requests * 100) if total_requests > 0 else 0,
                    "average_response_time_ms": avg_response_time
                },
                "jobs": job_metrics,
                "cache": cache_metrics,
                "errors": dict(_error_counts)
            }
            
        except ImportError:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "error": "System metrics not available (psutil not installed)"
            }
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
            raise
    
    async def _collect_request_metrics(self) -> Dict[str, Any]:
        """Collect request-specific metrics."""
        total_requests = _metrics_storage['total_requests']
        successful_requests = _metrics_storage['successful_requests']
        failed_requests = _metrics_storage['failed_requests']
        
        # Calculate percentiles
        response_times = list(_request_times)
        response_times.sort()
        
        percentiles = {}
        if response_times:
            percentiles = {
                "p50": response_times[int(len(response_times) * 0.5)],
                "p90": response_times[int(len(response_times) * 0.9)],
                "p95": response_times[int(len(response_times) * 0.95)],
                "p99": response_times[int(len(response_times) * 0.99)]
            }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "success_rate": (successful_requests / total_requests * 100) if total_requests > 0 else 0,
            "response_time_percentiles": percentiles,
            "error_breakdown": dict(_error_counts)
        }
    
    async def _collect_job_metrics(self) -> Dict[str, Any]:
        """Collect job-related metrics."""
        try:
            with get_session() as session:
                # Count jobs by status
                job_counts = {}
                for status in JobStatus:
                    count = session.query(Job).filter(Job.status == status).count()
                    job_counts[status.value] = count
                
                # Get recent job activity (last 24 hours)
                from datetime import timedelta
                recent_cutoff = datetime.utcnow() - timedelta(hours=24)
                recent_jobs = session.query(Job).filter(Job.created_at >= recent_cutoff).count()
                
                return {
                    "timestamp": datetime.utcnow().isoformat(),
                    "job_counts_by_status": job_counts,
                    "recent_jobs_24h": recent_jobs,
                    "total_jobs": sum(job_counts.values())
                }
                
        except Exception as e:
            logger.error(f"Failed to collect job metrics: {e}")
            return {"error": str(e)}
    
    async def _collect_cache_metrics(self) -> Dict[str, Any]:
        """Collect cache metrics."""
        try:
            from src.cache.cache_manager import get_cache
            from src.cache.eviction_engine import CacheEvictionEngine
            
            cache = await get_cache()
            eviction_engine = CacheEvictionEngine(cache)
            
            # Get cache stats
            cache_stats = await eviction_engine.get_cache_stats()
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "cache_stats": cache_stats
            }
            
        except Exception as e:
            logger.error(f"Failed to collect cache metrics: {e}")
            return {"error": str(e)}


# Global monitoring router instance
monitoring_router = MonitoringRouter()


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for enhanced request logging."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("request_logger")
    
    async def dispatch(self, request: Request, call_next):
        """Log request details."""
        start_time = time.time()
        
        # Log request
        self.logger.info(f"Request started: {request.method} {request.url.path}")
        
        # Process request
        response = await call_next(request)
        
        # Log response
        process_time = time.time() - start_time
        self.logger.info(
            f"Request completed: {request.method} {request.url.path} "
            f"Status: {response.status_code} Time: {process_time:.3f}s"
        )
        
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for error handling and logging."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("error_logger")
    
    async def dispatch(self, request: Request, call_next):
        """Handle errors and log them."""
        try:
            return await call_next(request)
        except Exception as e:
            # Log error
            self.logger.error(
                f"Unhandled error in {request.method} {request.url.path}: {str(e)}",
                exc_info=True
            )
            
            # Update error metrics
            _error_counts["500"] += 1
            
            # Return error response
            return JSONResponse(
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred",
                    "timestamp": datetime.utcnow().isoformat()
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
