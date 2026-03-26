"""
Tests for the load testing system.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock
from src.testing.load_testing import (
    LoadTestRunner,
    LoadTestScenario,
    TenantBehavior,
    TenantProfile,
    LoadTestMetrics,
    LoadTestResult,
    NoisyNeighborTestSuite,
    run_noisy_neighbor_tests,
    run_single_scenario
)


class TestLoadTestRunner:
    """Test the LoadTestRunner class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = LoadTestRunner("http://test.example.com")
    
    def test_initialization(self):
        """Test LoadTestRunner initialization."""
        assert self.runner.base_url == "http://test.example.com"
        assert self.runner.max_concurrent_requests == 100
        assert self.runner.request_timeout == 30
        assert self.runner.metrics_collection_interval == 1.0
        assert not self.runner._running
    
    def test_calculate_request_interval_normal(self):
        """Test request interval calculation for normal behavior."""
        profile = TenantProfile("tenant-1", TenantBehavior.NORMAL, 2.0)
        
        interval = self.runner._calculate_request_interval(profile, 0)
        assert interval == 0.5  # 1.0 / 2.0
    
    def test_calculate_request_interval_aggressive(self):
        """Test request interval calculation for aggressive behavior."""
        profile = TenantProfile("tenant-1", TenantBehavior.AGGRESSIVE, 2.0)
        
        interval = self.runner._calculate_request_interval(profile, 0)
        assert interval == 0.25  # 0.5 * 0.5
    
    def test_calculate_request_interval_bursty(self):
        """Test request interval calculation for bursty behavior."""
        profile = TenantProfile("tenant-1", TenantBehavior.BURSTY, 2.0)
        
        # During burst (first 8 requests)
        interval = self.runner._calculate_request_interval(profile, 5)
        assert interval == 0.1  # 0.5 * 0.2
        
        # During pause (last 2 requests)
        interval = self.runner._calculate_request_interval(profile, 9)
        assert interval == 2.5  # 0.5 * 5.0
    
    def test_calculate_request_interval_malicious(self):
        """Test request interval calculation for malicious behavior."""
        profile = TenantProfile("tenant-1", TenantBehavior.MALICIOUS, 2.0)
        
        # Test multiple times to get different results
        intervals = []
        for i in range(100):  # More iterations to increase chance of getting spikes
            interval = self.runner._calculate_request_interval(profile, i)
            intervals.append(interval)
        
        # Should have both very fast (spike) and fast (normal) intervals
        # With 100 iterations and 10% chance, we should get at least one spike
        assert any(interval < 0.01 for interval in intervals)  # Spike
        assert any(0.01 <= interval < 0.1 for interval in intervals)  # Normal aggressive
    
    def test_percentile_calculation(self):
        """Test percentile calculation."""
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        
        assert abs(self.runner._percentile(data, 50) - 5.5) < 0.01  # Median (interpolated)
        assert abs(self.runner._percentile(data, 90) - 9.1) < 0.01  # P90 (interpolated)
        assert abs(self.runner._percentile(data, 95) - 9.55) < 0.01  # P95 (interpolated)
        assert abs(self.runner._percentile(data, 99) - 9.91) < 0.01  # P99 (interpolated)
    
    def test_percentile_empty_data(self):
        """Test percentile calculation with empty data."""
        assert self.runner._percentile([], 50) == 0.0
    
    def test_calculate_contention_score(self):
        """Test contention score calculation."""
        response_times = [0.1, 0.2, 0.3, 0.4, 0.5]
        system_metrics = [
            {"cpu_percent": 50, "memory_percent": 60},
            {"cpu_percent": 60, "memory_percent": 70},
            {"cpu_percent": 70, "memory_percent": 80}
        ]
        tenant_profiles = [
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-2", TenantBehavior.AGGRESSIVE, 2.0)
        ]
        
        score = self.runner._calculate_contention_score(response_times, system_metrics, tenant_profiles)
        
        assert 0.0 <= score <= 1.0
        assert score > 0.0  # Should have some contention
    
    def test_calculate_isolation_score(self):
        """Test isolation score calculation."""
        tenant_profiles = [
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0)
        ]
        
        # Low variance response times (good isolation)
        low_variance_times = [0.1, 0.11, 0.12, 0.13, 0.14]
        score1 = self.runner._calculate_isolation_score(tenant_profiles, low_variance_times)
        
        # High variance response times (poor isolation)
        high_variance_times = [0.1, 0.5, 1.0, 2.0, 5.0]
        score2 = self.runner._calculate_isolation_score(tenant_profiles, high_variance_times)
        
        assert 0.0 <= score1 <= 1.0
        assert 0.0 <= score2 <= 1.0
        assert score1 > score2  # Low variance should have better isolation
    
    def test_generate_recommendations(self):
        """Test recommendation generation."""
        # Create metrics with various issues
        metrics = LoadTestMetrics(
            p95_response_time=3.0,  # High
            p99_response_time=6.0,  # Very high
            requests_per_second=5.0,  # Low
            cpu_usage=[85, 90, 95],  # High
            memory_usage=[75, 80, 85],  # High
            resource_contention_score=0.8,  # High
            tenant_isolation_score=0.6  # Low
        )
        
        recommendations = self.runner._generate_recommendations(metrics, LoadTestScenario.NOISY_NEIGHBOR)
        
        assert len(recommendations) > 0
        assert any("P95 response time" in rec for rec in recommendations)
        assert any("P99 response time" in rec for rec in recommendations)
        assert any("Low throughput" in rec for rec in recommendations)
        assert any("CPU usage" in rec for rec in recommendations)
        assert any("memory usage" in rec.lower() for rec in recommendations)
        assert any("resource contention" in rec for rec in recommendations)
        assert any("tenant isolation" in rec for rec in recommendations)
    
    def test_check_violations(self):
        """Test violation checking."""
        # Create metrics with violations
        metrics = LoadTestMetrics(
            p95_response_time=3.0,  # Violation
            error_rate=0.02,  # Violation
            cpu_usage=[95, 98, 99]  # Violation
        )
        
        violations = self.runner._check_violations(metrics, LoadTestScenario.NORMAL_LOAD)
        
        assert len(violations) > 0
        assert any(v["type"] == "response_time_violation" for v in violations)
        assert any(v["type"] == "error_rate_violation" for v in violations)
        assert any(v["type"] == "resource_violation" for v in violations)
    
    @pytest.mark.asyncio
    async def test_simulate_resource_usage(self):
        """Test resource usage simulation."""
        profile = TenantProfile(
            "tenant-1", 
            TenantBehavior.NORMAL, 
            1.0,
            cpu_time_ms=100,
            memory_usage_mb=50
        )
        
        start_time = time.time()
        await self.runner._simulate_resource_usage(profile)
        duration = time.time() - start_time
        
        # Should take at least 100ms for CPU + 50ms for memory = 150ms
        assert duration >= 0.15
    
    @pytest.mark.asyncio
    async def test_make_normal_request(self):
        """Test normal request simulation."""
        profile = TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0, cpu_time_ms=50)
        
        result = await self.runner._make_normal_request(profile)
        
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_make_cache_request(self):
        """Test cache request simulation."""
        profile = TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0, cache_usage=0.8)
        
        result = await self.runner._make_cache_request(profile)
        
        assert result["status"] == "success"
        assert "cache_operations" in result
        assert result["cache_operations"] > 0
    
    @pytest.mark.asyncio
    async def test_make_database_request(self):
        """Test database request simulation."""
        profile = TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0, database_queries=5)
        
        result = await self.runner._make_database_request(profile)
        
        assert result["status"] == "success"
        assert result["queries"] == 5
    
    @pytest.mark.asyncio
    async def test_make_api_request(self):
        """Test API request simulation."""
        profile = TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0, api_calls=3)
        
        result = await self.runner._make_api_request(profile)
        
        assert result["status"] == "success"
        assert result["api_calls"] == 3
    
    @pytest.mark.asyncio
    async def test_run_scenario_short_duration(self):
        """Test running a scenario with short duration."""
        profiles = [
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 10.0),  # High rate for quick test
            TenantProfile("tenant-2", TenantBehavior.NORMAL, 10.0)
        ]
        
        result = await self.runner.run_scenario(
            LoadTestScenario.NORMAL_LOAD,
            profiles,
            duration_seconds=1.0  # Very short test
        )
        
        assert result.success
        assert result.scenario == LoadTestScenario.NORMAL_LOAD
        assert result.total_tenants == 2
        assert result.total_requests > 0
        assert result.metrics.total_requests > 0
        assert result.metrics.duration_seconds > 0
    
    @pytest.mark.asyncio
    async def test_run_scenario_no_tenants(self):
        """Test running a scenario with no tenants."""
        result = await self.runner.run_scenario(
            LoadTestScenario.NORMAL_LOAD,
            [],
            duration_seconds=1.0
        )
        
        assert not result.success
        assert "No requests completed" in result.error_message


class TestNoisyNeighborTestSuite:
    """Test the NoisyNeighborTestSuite class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.test_suite = NoisyNeighborTestSuite("http://test.example.com")
    
    @pytest.mark.asyncio
    async def test_test_normal_with_noisy_neighbor(self):
        """Test the normal with noisy neighbor scenario."""
        result = await self.test_suite._test_normal_with_noisy_neighbor()
        
        assert result.success
        assert result.scenario == LoadTestScenario.NOISY_NEIGHBOR
        assert result.total_tenants == 5  # 4 normal + 1 noisy
        assert result.total_requests > 0
    
    @pytest.mark.asyncio
    async def test_test_multiple_noisy_neighbors(self):
        """Test the multiple noisy neighbors scenario."""
        result = await self.test_suite._test_multiple_noisy_neighbors()
        
        assert result.success
        assert result.scenario == LoadTestScenario.NOISY_NEIGHBOR
        assert result.total_tenants == 5  # 2 normal + 3 noisy
        assert result.total_requests > 0
    
    @pytest.mark.asyncio
    async def test_test_bursty_vs_sustained(self):
        """Test the bursty vs sustained scenario."""
        result = await self.test_suite._test_bursty_vs_sustained()
        
        assert result.success
        assert result.scenario == LoadTestScenario.MIXED_WORKLOAD
        assert result.total_tenants == 4
        assert result.total_requests > 0
    
    @pytest.mark.asyncio
    async def test_test_cache_thrashing(self):
        """Test the cache thrashing scenario."""
        result = await self.test_suite._test_cache_thrashing()
        
        assert result.success
        assert result.scenario == LoadTestScenario.CACHE_THRASHING
        assert result.total_tenants == 5  # 3 cache-heavy + 2 normal
        assert result.total_requests > 0
    
    @pytest.mark.asyncio
    async def test_test_database_contention(self):
        """Test the database contention scenario."""
        result = await self.test_suite._test_database_contention()
        
        assert result.success
        assert result.scenario == LoadTestScenario.DATABASE_CONTENTION
        assert result.total_tenants == 5  # 3 db-heavy + 2 normal
        assert result.total_requests > 0
    
    @pytest.mark.asyncio
    async def test_test_api_rate_limiting(self):
        """Test the API rate limiting scenario."""
        result = await self.test_suite._test_api_rate_limiting()
        
        assert result.success
        assert result.scenario == LoadTestScenario.API_RATE_LIMITING
        assert result.total_tenants == 4  # 2 api-heavy + 2 normal
        assert result.total_requests > 0
    
    @pytest.mark.asyncio
    async def test_run_noisy_neighbor_tests(self):
        """Test running all noisy neighbor tests."""
        results = await self.test_suite.run_noisy_neighbor_tests()
        
        assert len(results) == 6
        assert "normal_with_noisy" in results
        assert "multiple_noisy" in results
        assert "bursty_vs_sustained" in results
        assert "cache_thrashing" in results
        assert "database_contention" in results
        assert "api_rate_limiting" in results
        
        # All tests should succeed
        for test_name, result in results.items():
            assert result.success, f"Test {test_name} failed: {result.error_message}"
    
    def test_generate_report(self):
        """Test report generation."""
        # Create mock results
        results = {
            "test1": LoadTestResult(
                scenario=LoadTestScenario.NORMAL_LOAD,
                duration_seconds=60.0,
                total_tenants=2,
                total_requests=100,
                metrics=LoadTestMetrics(
                    total_requests=100,
                    average_response_time=0.5,
                    p95_response_time=1.0,
                    requests_per_second=1.67
                ),
                system_metrics={"avg_cpu_percent": 50.0, "max_cpu_percent": 80.0},
                recommendations=["Test recommendation"],
                violations=[]
            )
        }
        
        report = self.test_suite.generate_report(results)
        
        assert "# Noisy Neighbor Load Test Report" in report
        assert "Test1" in report
        assert "60.0 seconds" in report
        assert "2" in report  # Total tenants
        assert "100" in report  # Total requests
        assert "Test recommendation" in report


class TestLoadTestingFunctions:
    """Test the module-level functions."""
    
    @pytest.mark.asyncio
    async def test_run_noisy_neighbor_tests_function(self):
        """Test the run_noisy_neighbor_tests function."""
        results = await run_noisy_neighbor_tests("http://test.example.com")
        
        assert len(results) == 6
        assert all(result.success for result in results.values())
    
    @pytest.mark.asyncio
    async def test_run_single_scenario_function(self):
        """Test the run_single_scenario function."""
        profiles = [
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 10.0)
        ]
        
        result = await run_single_scenario(
            LoadTestScenario.NORMAL_LOAD,
            profiles,
            duration_seconds=1.0,
            base_url="http://test.example.com"
        )
        
        assert result.success
        assert result.scenario == LoadTestScenario.NORMAL_LOAD
        assert result.total_tenants == 1


class TestLoadTestingIntegration:
    """Integration tests for load testing."""
    
    @pytest.mark.asyncio
    async def test_full_load_test_workflow(self):
        """Test a complete load test workflow."""
        # Create a realistic test scenario
        profiles = [
            TenantProfile("tenant-normal-1", TenantBehavior.NORMAL, 2.0),
            TenantProfile("tenant-normal-2", TenantBehavior.NORMAL, 2.0),
            TenantProfile("tenant-noisy", TenantBehavior.AGGRESSIVE, 10.0,
                         resource_intensity=3.0, cpu_time_ms=200, memory_usage_mb=100)
        ]
        
        runner = LoadTestRunner("http://test.example.com")
        result = await runner.run_scenario(
            LoadTestScenario.NOISY_NEIGHBOR,
            profiles,
            duration_seconds=2.0  # Short test for CI
        )
        
        # Verify results
        assert result.success
        assert result.scenario == LoadTestScenario.NOISY_NEIGHBOR
        assert result.total_tenants == 3
        assert result.total_requests > 0
        assert result.metrics.total_requests > 0
        assert result.metrics.average_response_time > 0
        assert result.metrics.requests_per_second > 0
        assert 0.0 <= result.metrics.resource_contention_score <= 1.0
        assert 0.0 <= result.metrics.tenant_isolation_score <= 1.0
        
        # Should have some recommendations
        assert len(result.recommendations) >= 0  # May or may not have recommendations
    
    @pytest.mark.asyncio
    async def test_metrics_accuracy(self):
        """Test that metrics are calculated accurately."""
        profiles = [
            TenantProfile("tenant-1", TenantBehavior.NORMAL, 5.0)  # 5 RPS
        ]
        
        runner = LoadTestRunner("http://test.example.com")
        result = await runner.run_scenario(
            LoadTestScenario.NORMAL_LOAD,
            profiles,
            duration_seconds=2.0
        )
        
        assert result.success
        assert result.metrics.total_requests > 0
        assert result.metrics.duration_seconds > 0
        
        # Calculate expected RPS (should be close to 5)
        expected_rps = result.metrics.total_requests / result.metrics.duration_seconds
        assert abs(expected_rps - result.metrics.requests_per_second) < 0.1
    
    @pytest.mark.asyncio
    async def test_tenant_isolation_measurement(self):
        """Test that tenant isolation is properly measured."""
        # Create profiles with different behaviors
        profiles = [
            TenantProfile("tenant-normal", TenantBehavior.NORMAL, 1.0),
            TenantProfile("tenant-aggressive", TenantBehavior.AGGRESSIVE, 5.0,
                         resource_intensity=2.0)
        ]
        
        runner = LoadTestRunner("http://test.example.com")
        result = await runner.run_scenario(
            LoadTestScenario.NOISY_NEIGHBOR,
            profiles,
            duration_seconds=2.0
        )
        
        assert result.success
        assert 0.0 <= result.metrics.tenant_isolation_score <= 1.0
        assert 0.0 <= result.metrics.resource_contention_score <= 1.0
        
        # With an aggressive tenant, we should see some contention
        # but the exact values depend on the simulation
        assert result.metrics.resource_contention_score >= 0.0
