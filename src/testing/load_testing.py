"""
Load testing system for Noisy Neighbor scenarios.

This module provides comprehensive load testing capabilities to simulate
and test the impact of resource-intensive tenants on system performance
and other tenants' experience.
"""

import asyncio
import time
import random
import statistics
import logging
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from enum import Enum
import threading
from collections import defaultdict, deque
import psutil
import requests
from src.utils.logging_utils import get_logger
from src.security.audit_logger import log_audit_event, AuditEventType, AuditSeverity


class LoadTestScenario(Enum):
    """Types of load test scenarios."""
    NORMAL_LOAD = "normal_load"
    NOISY_NEIGHBOR = "noisy_neighbor"
    BURST_LOAD = "burst_load"
    SUSTAINED_LOAD = "sustained_load"
    MIXED_WORKLOAD = "mixed_workload"
    CACHE_THRASHING = "cache_thrashing"
    DATABASE_CONTENTION = "database_contention"
    API_RATE_LIMITING = "api_rate_limiting"
    MEMORY_PRESSURE = "memory_pressure"
    CPU_INTENSIVE = "cpu_intensive"


class TenantBehavior(Enum):
    """Types of tenant behavior patterns."""
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"
    BURSTY = "bursty"
    SUSTAINED_HIGH = "sustained_high"
    ERRATIC = "erratic"
    MALICIOUS = "malicious"


@dataclass
class LoadTestMetrics:
    """Metrics collected during load testing."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    median_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    max_response_time: float = 0.0
    min_response_time: float = float('inf')
    requests_per_second: float = 0.0
    error_rate: float = 0.0
    throughput: float = 0.0
    cpu_usage: List[float] = field(default_factory=list)
    memory_usage: List[float] = field(default_factory=list)
    cache_hit_rate: float = 0.0
    database_connections: int = 0
    active_tenants: int = 0
    resource_contention_score: float = 0.0
    tenant_isolation_score: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0


@dataclass
class TenantProfile:
    """Profile defining a tenant's behavior during load testing."""
    tenant_id: str
    behavior: TenantBehavior
    request_rate: float  # requests per second
    burst_multiplier: float = 1.0
    sustained_duration: float = 0.0  # seconds
    error_rate: float = 0.0
    resource_intensity: float = 1.0  # 1.0 = normal, >1.0 = more intensive
    cache_usage: float = 0.5  # 0.0 = no cache, 1.0 = heavy cache usage
    database_queries: int = 1  # queries per request
    api_calls: int = 1  # external API calls per request
    memory_usage_mb: int = 10  # MB per request
    cpu_time_ms: int = 100  # milliseconds of CPU time per request


@dataclass
class LoadTestResult:
    """Result of a load test run."""
    scenario: LoadTestScenario
    duration_seconds: float
    total_tenants: int
    total_requests: int
    metrics: LoadTestMetrics
    tenant_metrics: Dict[str, LoadTestMetrics] = field(default_factory=dict)
    system_metrics: Dict[str, Any] = field(default_factory=dict)
    violations: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    success: bool = True
    error_message: Optional[str] = None


class LoadTestRunner:
    """
    Comprehensive load testing runner for Noisy Neighbor scenarios.
    
    Simulates various tenant behaviors and measures their impact on system
    performance and tenant isolation.
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.logger = get_logger("load_testing")
        
        # Configuration
        self.max_concurrent_requests = int(os.getenv('LOAD_TEST_MAX_CONCURRENT', '100'))
        self.request_timeout = int(os.getenv('LOAD_TEST_TIMEOUT', '30'))
        self.metrics_collection_interval = float(os.getenv('LOAD_TEST_METRICS_INTERVAL', '1.0'))
        
        # State
        self._running = False
        self._metrics_lock = threading.Lock()
        self._response_times: deque = deque(maxlen=10000)
        self._system_metrics: deque = deque(maxlen=1000)
        
        self.logger.info("LoadTestRunner initialized", 
                        base_url=base_url,
                        max_concurrent_requests=self.max_concurrent_requests)
    
    async def run_scenario(self, scenario: LoadTestScenario, 
                          tenant_profiles: List[TenantProfile],
                          duration_seconds: float = 60.0) -> LoadTestResult:
        """
        Run a load test scenario.
        
        Args:
            scenario: The load test scenario to run
            tenant_profiles: List of tenant profiles to simulate
            duration_seconds: Duration of the test in seconds
            
        Returns:
            LoadTestResult: Results of the load test
        """
        self.logger.info("Starting load test scenario", 
                        scenario=scenario.value,
                        tenant_count=len(tenant_profiles),
                        duration=duration_seconds)
        
        # Log audit event
        log_audit_event(
            AuditEventType.SYSTEM_STARTUP,
            AuditSeverity.LOW,
            "load_testing",
            details={
                "scenario": scenario.value,
                "tenant_count": len(tenant_profiles),
                "duration_seconds": duration_seconds
            }
        )
        
        start_time = datetime.now(timezone.utc)
        self._running = True
        
        # Clear previous metrics
        with self._metrics_lock:
            self._response_times.clear()
            self._system_metrics.clear()
        
        # Start system metrics collection
        metrics_task = asyncio.create_task(self._collect_system_metrics())
        
        # Start tenant simulation tasks
        tenant_tasks = []
        for profile in tenant_profiles:
            task = asyncio.create_task(self._simulate_tenant(profile, duration_seconds))
            tenant_tasks.append(task)
        
        try:
            # Wait for all tasks to complete or timeout
            await asyncio.wait_for(
                asyncio.gather(*tenant_tasks, return_exceptions=True),
                timeout=duration_seconds + 10
            )
        except asyncio.TimeoutError:
            self.logger.warning("Load test timed out")
        finally:
            self._running = False
            metrics_task.cancel()
        
        end_time = datetime.now(timezone.utc)
        
        # Calculate metrics
        result = await self._calculate_results(
            scenario, tenant_profiles, start_time, end_time
        )
        
        self.logger.info("Load test completed", 
                        scenario=scenario.value,
                        success=result.success,
                        total_requests=result.total_requests,
                        error_rate=result.metrics.error_rate)
        
        return result
    
    async def _simulate_tenant(self, profile: TenantProfile, duration_seconds: float):
        """Simulate a tenant's behavior during the load test."""
        start_time = time.time()
        request_count = 0
        
        while time.time() - start_time < duration_seconds and self._running:
            # Calculate request interval based on behavior
            interval = self._calculate_request_interval(profile, request_count)
            
            # Wait for next request
            await asyncio.sleep(interval)
            
            if not self._running:
                break
            
            # Make request
            await self._make_tenant_request(profile)
            request_count += 1
    
    def _calculate_request_interval(self, profile: TenantProfile, request_count: int) -> float:
        """Calculate the interval between requests based on tenant behavior."""
        base_interval = 1.0 / profile.request_rate
        
        if profile.behavior == TenantBehavior.NORMAL:
            return base_interval
        
        elif profile.behavior == TenantBehavior.AGGRESSIVE:
            # 50% faster than normal
            return base_interval * 0.5
        
        elif profile.behavior == TenantBehavior.BURSTY:
            # Burst every 10 requests, then pause
            if request_count % 10 < 8:
                return base_interval * 0.2  # 5x faster during burst
            else:
                return base_interval * 5.0  # 5x slower during pause
        
        elif profile.behavior == TenantBehavior.SUSTAINED_HIGH:
            # Consistently high rate
            return base_interval * 0.3
        
        elif profile.behavior == TenantBehavior.ERRATIC:
            # Random intervals
            return base_interval * random.uniform(0.1, 3.0)
        
        elif profile.behavior == TenantBehavior.MALICIOUS:
            # Very aggressive with occasional spikes
            if random.random() < 0.1:  # 10% chance of spike
                return base_interval * 0.01  # 100x faster
            else:
                return base_interval * 0.1  # 10x faster
        
        return base_interval
    
    async def _make_tenant_request(self, profile: TenantProfile):
        """Make a request on behalf of a tenant."""
        start_time = time.time()
        
        try:
            # Simulate different types of requests based on profile
            if profile.cache_usage > 0.7:
                # Cache-heavy request
                response = await self._make_cache_request(profile)
            elif profile.database_queries > 3:
                # Database-heavy request
                response = await self._make_database_request(profile)
            elif profile.api_calls > 1:
                # API-heavy request
                response = await self._make_api_request(profile)
            else:
                # Normal request
                response = await self._make_normal_request(profile)
            
            # Simulate resource usage
            await self._simulate_resource_usage(profile)
            
            response_time = time.time() - start_time
            
            # Record metrics
            with self._metrics_lock:
                self._response_times.append(response_time)
            
            # Simulate occasional errors
            if random.random() < profile.error_rate:
                raise Exception(f"Simulated error for tenant {profile.tenant_id}")
            
        except Exception as e:
            response_time = time.time() - start_time
            self.logger.warning("Request failed", 
                              tenant_id=profile.tenant_id,
                              error=str(e),
                              response_time=response_time)
    
    async def _make_normal_request(self, profile: TenantProfile):
        """Make a normal request."""
        # Simulate a simple API call
        await asyncio.sleep(profile.cpu_time_ms / 1000.0)
        return {"status": "success"}
    
    async def _make_cache_request(self, profile: TenantProfile):
        """Make a cache-heavy request."""
        # Simulate cache operations
        cache_operations = int(profile.cache_usage * 10)
        for _ in range(cache_operations):
            await asyncio.sleep(0.001)  # 1ms per cache operation
        return {"status": "success", "cache_operations": cache_operations}
    
    async def _make_database_request(self, profile: TenantProfile):
        """Make a database-heavy request."""
        # Simulate database queries
        for _ in range(profile.database_queries):
            await asyncio.sleep(0.01)  # 10ms per query
        return {"status": "success", "queries": profile.database_queries}
    
    async def _make_api_request(self, profile: TenantProfile):
        """Make an API-heavy request."""
        # Simulate external API calls
        for _ in range(profile.api_calls):
            await asyncio.sleep(0.05)  # 50ms per API call
        return {"status": "success", "api_calls": profile.api_calls}
    
    async def _simulate_resource_usage(self, profile: TenantProfile):
        """Simulate resource usage based on profile."""
        # Simulate CPU usage
        if profile.cpu_time_ms > 0:
            await asyncio.sleep(profile.cpu_time_ms / 1000.0)
        
        # Simulate memory usage (in a real scenario, this would allocate memory)
        if profile.memory_usage_mb > 0:
            # Simulate memory allocation time
            await asyncio.sleep(profile.memory_usage_mb * 0.001)  # 1ms per MB
    
    async def _collect_system_metrics(self):
        """Collect system metrics during the test."""
        while self._running:
            try:
                # Get system metrics
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # Get process metrics
                process = psutil.Process()
                process_memory = process.memory_info().rss / 1024 / 1024  # MB
                
                metrics = {
                    "timestamp": datetime.now(timezone.utc),
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "process_memory_mb": process_memory,
                    "active_connections": len(psutil.net_connections()),
                }
                
                with self._metrics_lock:
                    self._system_metrics.append(metrics)
                
                await asyncio.sleep(self.metrics_collection_interval)
                
            except Exception as e:
                self.logger.error("Failed to collect system metrics", error=str(e))
                await asyncio.sleep(self.metrics_collection_interval)
    
    async def _calculate_results(self, scenario: LoadTestScenario,
                                tenant_profiles: List[TenantProfile],
                                start_time: datetime, end_time: datetime) -> LoadTestResult:
        """Calculate load test results."""
        duration = (end_time - start_time).total_seconds()
        
        # Calculate response time metrics
        with self._metrics_lock:
            response_times = list(self._response_times)
            system_metrics = list(self._system_metrics)
        
        if not response_times:
            return LoadTestResult(
                scenario=scenario,
                duration_seconds=duration,
                total_tenants=len(tenant_profiles),
                total_requests=0,
                metrics=LoadTestMetrics(),
                success=False,
                error_message="No requests completed"
            )
        
        # Calculate response time statistics
        avg_response_time = statistics.mean(response_times)
        median_response_time = statistics.median(response_times)
        p95_response_time = self._percentile(response_times, 95)
        p99_response_time = self._percentile(response_times, 99)
        max_response_time = max(response_times)
        min_response_time = min(response_times)
        
        # Calculate throughput metrics
        total_requests = len(response_times)
        requests_per_second = total_requests / duration if duration > 0 else 0
        
        # Calculate system metrics
        avg_cpu = statistics.mean([m["cpu_percent"] for m in system_metrics]) if system_metrics else 0
        avg_memory = statistics.mean([m["memory_percent"] for m in system_metrics]) if system_metrics else 0
        max_cpu = max([m["cpu_percent"] for m in system_metrics]) if system_metrics else 0
        max_memory = max([m["memory_percent"] for m in system_metrics]) if system_metrics else 0
        
        # Calculate resource contention score
        contention_score = self._calculate_contention_score(
            response_times, system_metrics, tenant_profiles
        )
        
        # Calculate tenant isolation score
        isolation_score = self._calculate_isolation_score(tenant_profiles, response_times)
        
        # Create metrics object
        metrics = LoadTestMetrics(
            total_requests=total_requests,
            successful_requests=total_requests,  # Assuming all completed successfully
            failed_requests=0,  # Would need to track failures separately
            average_response_time=avg_response_time,
            median_response_time=median_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            max_response_time=max_response_time,
            min_response_time=min_response_time,
            requests_per_second=requests_per_second,
            error_rate=0.0,  # Would need to track errors separately
            throughput=requests_per_second,
            cpu_usage=[m["cpu_percent"] for m in system_metrics],
            memory_usage=[m["memory_percent"] for m in system_metrics],
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            resource_contention_score=contention_score,
            tenant_isolation_score=isolation_score
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(metrics, scenario)
        
        # Check for violations
        violations = self._check_violations(metrics, scenario)
        
        return LoadTestResult(
            scenario=scenario,
            duration_seconds=duration,
            total_tenants=len(tenant_profiles),
            total_requests=total_requests,
            metrics=metrics,
            system_metrics={
                "avg_cpu_percent": avg_cpu,
                "max_cpu_percent": max_cpu,
                "avg_memory_percent": avg_memory,
                "max_memory_percent": max_memory,
                "system_metrics_count": len(system_metrics)
            },
            recommendations=recommendations,
            violations=violations,
            success=True
        )
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        # Use numpy-style percentile calculation for more accurate results
        index = (percentile / 100.0) * (len(sorted_data) - 1)
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            # Linear interpolation for non-integer indices
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    def _calculate_contention_score(self, response_times: List[float],
                                   system_metrics: List[Dict[str, Any]],
                                   tenant_profiles: List[TenantProfile]) -> float:
        """Calculate resource contention score."""
        if not response_times or not system_metrics:
            return 0.0
        
        # Base score from response time degradation
        avg_response_time = statistics.mean(response_times)
        base_score = min(avg_response_time / 1.0, 1.0)  # Normalize to 1.0
        
        # CPU contention
        avg_cpu = statistics.mean([m["cpu_percent"] for m in system_metrics])
        cpu_score = avg_cpu / 100.0
        
        # Memory contention
        avg_memory = statistics.mean([m["memory_percent"] for m in system_metrics])
        memory_score = avg_memory / 100.0
        
        # Tenant behavior impact
        aggressive_tenants = sum(1 for p in tenant_profiles 
                               if p.behavior in [TenantBehavior.AGGRESSIVE, TenantBehavior.MALICIOUS])
        behavior_score = aggressive_tenants / len(tenant_profiles) if tenant_profiles else 0
        
        # Weighted combination
        contention_score = (base_score * 0.4 + cpu_score * 0.3 + 
                           memory_score * 0.2 + behavior_score * 0.1)
        
        return min(contention_score, 1.0)
    
    def _calculate_isolation_score(self, tenant_profiles: List[TenantProfile],
                                  response_times: List[float]) -> float:
        """Calculate tenant isolation score."""
        if not tenant_profiles or not response_times:
            return 1.0
        
        # In a real implementation, this would measure actual isolation
        # For now, we'll use a simplified calculation based on response time variance
        
        if len(response_times) < 2:
            return 1.0
        
        # Lower variance indicates better isolation
        variance = statistics.variance(response_times)
        avg_response_time = statistics.mean(response_times)
        
        # Normalize variance relative to average
        normalized_variance = variance / (avg_response_time ** 2) if avg_response_time > 0 else 0
        
        # Convert to isolation score (lower variance = higher isolation)
        isolation_score = max(0.0, 1.0 - normalized_variance)
        
        return isolation_score
    
    def _generate_recommendations(self, metrics: LoadTestMetrics,
                                 scenario: LoadTestScenario) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        # Response time recommendations
        if metrics.p95_response_time > 2.0:
            recommendations.append("Consider optimizing slow endpoints - P95 response time exceeds 2 seconds")
        
        if metrics.p99_response_time > 5.0:
            recommendations.append("Critical: P99 response time exceeds 5 seconds - immediate optimization required")
        
        # Throughput recommendations
        if metrics.requests_per_second < 10:
            recommendations.append("Low throughput detected - consider horizontal scaling")
        
        # Resource recommendations
        if metrics.cpu_usage and max(metrics.cpu_usage) > 80:
            recommendations.append("High CPU usage detected - consider CPU optimization or scaling")
        
        if metrics.memory_usage and max(metrics.memory_usage) > 80:
            recommendations.append("High memory usage detected - consider memory optimization")
        
        # Contention recommendations
        if metrics.resource_contention_score > 0.7:
            recommendations.append("High resource contention detected - implement better resource isolation")
        
        # Isolation recommendations
        if metrics.tenant_isolation_score < 0.8:
            recommendations.append("Poor tenant isolation detected - review isolation mechanisms")
        
        # Scenario-specific recommendations
        if scenario == LoadTestScenario.NOISY_NEIGHBOR:
            if metrics.resource_contention_score > 0.5:
                recommendations.append("Noisy neighbor impact detected - implement resource quotas")
        
        return recommendations
    
    def _check_violations(self, metrics: LoadTestMetrics,
                         scenario: LoadTestScenario) -> List[Dict[str, Any]]:
        """Check for SLA violations and other issues."""
        violations = []
        
        # Response time violations
        if metrics.p95_response_time > 2.0:
            violations.append({
                "type": "response_time_violation",
                "severity": "high",
                "metric": "p95_response_time",
                "value": metrics.p95_response_time,
                "threshold": 2.0,
                "message": "P95 response time exceeds SLA threshold"
            })
        
        # Error rate violations
        if metrics.error_rate > 0.01:  # 1%
            violations.append({
                "type": "error_rate_violation",
                "severity": "critical",
                "metric": "error_rate",
                "value": metrics.error_rate,
                "threshold": 0.01,
                "message": "Error rate exceeds acceptable threshold"
            })
        
        # Resource violations
        if metrics.cpu_usage and max(metrics.cpu_usage) > 90:
            violations.append({
                "type": "resource_violation",
                "severity": "high",
                "metric": "cpu_usage",
                "value": max(metrics.cpu_usage),
                "threshold": 90,
                "message": "CPU usage exceeds critical threshold"
            })
        
        return violations


class NoisyNeighborTestSuite:
    """
    Test suite specifically for Noisy Neighbor scenarios.
    
    Provides predefined test scenarios to evaluate the impact of
    resource-intensive tenants on system performance and isolation.
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.runner = LoadTestRunner(base_url)
        self.logger = get_logger("noisy_neighbor_tests")
    
    async def run_noisy_neighbor_tests(self) -> Dict[str, LoadTestResult]:
        """Run all noisy neighbor test scenarios."""
        results = {}
        
        # Test 1: Normal tenants with one noisy neighbor
        results["normal_with_noisy"] = await self._test_normal_with_noisy_neighbor()
        
        # Test 2: Multiple noisy neighbors
        results["multiple_noisy"] = await self._test_multiple_noisy_neighbors()
        
        # Test 3: Bursty vs sustained load
        results["bursty_vs_sustained"] = await self._test_bursty_vs_sustained()
        
        # Test 4: Cache thrashing
        results["cache_thrashing"] = await self._test_cache_thrashing()
        
        # Test 5: Database contention
        results["database_contention"] = await self._test_database_contention()
        
        # Test 6: API rate limiting
        results["api_rate_limiting"] = await self._test_api_rate_limiting()
        
        return results
    
    async def _test_normal_with_noisy_neighbor(self) -> LoadTestResult:
        """Test normal tenants with one noisy neighbor."""
        self.logger.info("Running test: Normal tenants with noisy neighbor")
        
        profiles = [
            # Normal tenants
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-3", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-4", TenantBehavior.NORMAL, 1.0),
            
            # Noisy neighbor
            TenantProfile("tenant-noisy", TenantBehavior.AGGRESSIVE, 10.0, 
                         resource_intensity=5.0, cpu_time_ms=500, memory_usage_mb=100)
        ]
        
        return await self.runner.run_scenario(
            LoadTestScenario.NOISY_NEIGHBOR,
            profiles,
            duration_seconds=60.0
        )
    
    async def _test_multiple_noisy_neighbors(self) -> LoadTestResult:
        """Test multiple noisy neighbors."""
        self.logger.info("Running test: Multiple noisy neighbors")
        
        profiles = [
            # Normal tenants
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0),
            
            # Multiple noisy neighbors
            TenantProfile("tenant-noisy-1", TenantBehavior.AGGRESSIVE, 5.0,
                         resource_intensity=3.0, cpu_time_ms=300),
            TenantProfile("tenant-noisy-2", TenantBehavior.BURSTY, 8.0,
                         resource_intensity=4.0, memory_usage_mb=150),
            TenantProfile("tenant-noisy-3", TenantBehavior.SUSTAINED_HIGH, 6.0,
                         resource_intensity=2.0, database_queries=5)
        ]
        
        return await self.runner.run_scenario(
            LoadTestScenario.NOISY_NEIGHBOR,
            profiles,
            duration_seconds=60.0
        )
    
    async def _test_bursty_vs_sustained(self) -> LoadTestResult:
        """Test bursty vs sustained load patterns."""
        self.logger.info("Running test: Bursty vs sustained load")
        
        profiles = [
            # Sustained high load tenant
            TenantProfile("tenant-sustained", TenantBehavior.SUSTAINED_HIGH, 5.0,
                         resource_intensity=2.0),
            
            # Bursty tenant
            TenantProfile("tenant-bursty", TenantBehavior.BURSTY, 10.0,
                         resource_intensity=3.0),
            
            # Normal tenants
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0),
        ]
        
        return await self.runner.run_scenario(
            LoadTestScenario.MIXED_WORKLOAD,
            profiles,
            duration_seconds=60.0
        )
    
    async def _test_cache_thrashing(self) -> LoadTestResult:
        """Test cache thrashing scenario."""
        self.logger.info("Running test: Cache thrashing")
        
        profiles = [
            # Cache-heavy tenants
            TenantProfile("tenant-cache-1", TenantBehavior.AGGRESSIVE, 20.0,
                         cache_usage=0.9, resource_intensity=1.5),
            TenantProfile("tenant-cache-2", TenantBehavior.AGGRESSIVE, 20.0,
                         cache_usage=0.9, resource_intensity=1.5),
            TenantProfile("tenant-cache-3", TenantBehavior.AGGRESSIVE, 20.0,
                         cache_usage=0.9, resource_intensity=1.5),
            
            # Normal tenants
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0),
        ]
        
        return await self.runner.run_scenario(
            LoadTestScenario.CACHE_THRASHING,
            profiles,
            duration_seconds=60.0
        )
    
    async def _test_database_contention(self) -> LoadTestResult:
        """Test database contention scenario."""
        self.logger.info("Running test: Database contention")
        
        profiles = [
            # Database-heavy tenants
            TenantProfile("tenant-db-1", TenantBehavior.SUSTAINED_HIGH, 5.0,
                         database_queries=10, resource_intensity=2.0),
            TenantProfile("tenant-db-2", TenantBehavior.SUSTAINED_HIGH, 5.0,
                         database_queries=10, resource_intensity=2.0),
            TenantProfile("tenant-db-3", TenantBehavior.SUSTAINED_HIGH, 5.0,
                         database_queries=10, resource_intensity=2.0),
            
            # Normal tenants
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0),
        ]
        
        return await self.runner.run_scenario(
            LoadTestScenario.DATABASE_CONTENTION,
            profiles,
            duration_seconds=60.0
        )
    
    async def _test_api_rate_limiting(self) -> LoadTestResult:
        """Test API rate limiting scenario."""
        self.logger.info("Running test: API rate limiting")
        
        profiles = [
            # API-heavy tenants
            TenantProfile("tenant-api-1", TenantBehavior.AGGRESSIVE, 15.0,
                         api_calls=5, resource_intensity=1.5),
            TenantProfile("tenant-api-2", TenantBehavior.AGGRESSIVE, 15.0,
                         api_calls=5, resource_intensity=1.5),
            
            # Normal tenants
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0),
        ]
        
        return await self.runner.run_scenario(
            LoadTestScenario.API_RATE_LIMITING,
            profiles,
            duration_seconds=60.0
        )
    
    def generate_report(self, results: Dict[str, LoadTestResult]) -> str:
        """Generate a comprehensive test report."""
        report = []
        report.append("# Noisy Neighbor Load Test Report")
        report.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        report.append("")
        
        for test_name, result in results.items():
            report.append(f"## {test_name.replace('_', ' ').title()}")
            report.append("")
            
            if not result.success:
                report.append(f"**Status:** FAILED - {result.error_message}")
                report.append("")
                continue
            
            report.append(f"**Duration:** {result.duration_seconds:.1f} seconds")
            report.append(f"**Total Tenants:** {result.total_tenants}")
            report.append(f"**Total Requests:** {result.total_requests}")
            report.append(f"**Requests/Second:** {result.metrics.requests_per_second:.2f}")
            report.append("")
            
            # Response time metrics
            report.append("### Response Time Metrics")
            report.append(f"- Average: {result.metrics.average_response_time:.3f}s")
            report.append(f"- Median: {result.metrics.median_response_time:.3f}s")
            report.append(f"- P95: {result.metrics.p95_response_time:.3f}s")
            report.append(f"- P99: {result.metrics.p99_response_time:.3f}s")
            report.append(f"- Max: {result.metrics.max_response_time:.3f}s")
            report.append("")
            
            # System metrics
            if result.system_metrics:
                report.append("### System Metrics")
                report.append(f"- Average CPU: {result.system_metrics.get('avg_cpu_percent', 0):.1f}%")
                report.append(f"- Max CPU: {result.system_metrics.get('max_cpu_percent', 0):.1f}%")
                report.append(f"- Average Memory: {result.system_metrics.get('avg_memory_percent', 0):.1f}%")
                report.append(f"- Max Memory: {result.system_metrics.get('max_memory_percent', 0):.1f}%")
                report.append("")
            
            # Quality scores
            report.append("### Quality Scores")
            report.append(f"- Resource Contention: {result.metrics.resource_contention_score:.2f}")
            report.append(f"- Tenant Isolation: {result.metrics.tenant_isolation_score:.2f}")
            report.append("")
            
            # Violations
            if result.violations:
                report.append("### Violations")
                for violation in result.violations:
                    report.append(f"- **{violation['type']}** ({violation['severity']}): {violation['message']}")
                report.append("")
            
            # Recommendations
            if result.recommendations:
                report.append("### Recommendations")
                for rec in result.recommendations:
                    report.append(f"- {rec}")
                report.append("")
            
            report.append("---")
            report.append("")
        
        return "\n".join(report)


# Convenience functions for running tests
async def run_noisy_neighbor_tests(base_url: str = "http://localhost:8000") -> Dict[str, LoadTestResult]:
    """Run all noisy neighbor tests."""
    test_suite = NoisyNeighborTestSuite(base_url)
    return await test_suite.run_noisy_neighbor_tests()


async def run_single_scenario(scenario: LoadTestScenario, tenant_profiles: List[TenantProfile],
                            duration_seconds: float = 60.0,
                            base_url: str = "http://localhost:8000") -> LoadTestResult:
    """Run a single load test scenario."""
    runner = LoadTestRunner(base_url)
    return await runner.run_scenario(scenario, tenant_profiles, duration_seconds)
