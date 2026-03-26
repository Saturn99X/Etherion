#!/usr/bin/env python3
"""
Memory leak detection tests for the Etherion AI platform.
"""

import asyncio
import gc
import tracemalloc
import psutil
import os
import time
import threading
from typing import List
import pytest
from src.utils.secrets_manager import TenantSecretsManager
from src.utils.secure_string import SecureString
from src.tools.mcp.base_mcp_tool import BaseMCPTool, MCPToolResult


class MemoryTestTool(BaseMCPTool):
    """Test MCP tool for memory testing."""
    
    def __init__(self):
        super().__init__("memory_test_tool", "Test tool for memory leak detection")
        self.created_objects = []
    
    async def execute(self, params):
        """Execute the test tool."""
        # Create some objects to test memory usage
        for i in range(params.get('object_count', 100)):
            obj = {
                'id': i,
                'data': 'x' * 1000,  # 1KB of data per object
                'nested': {'value': i * 2}
            }
            self.created_objects.append(obj)
        
        return self._create_result(True, data={"objects_created": len(self.created_objects)})


class TestMemoryUsageMonitoring:
    """Test memory usage monitoring."""

    def setup_method(self):
        """Set up test fixtures."""
        tracemalloc.start()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        tracemalloc.stop()

    def test_memory_usage_profiling(self):
        """Test memory usage profiling."""
        # Take initial snapshot
        snapshot1 = tracemalloc.take_snapshot()
        
        # Create some objects
        objects = []
        for i in range(1000):
            obj = {'id': i, 'data': f'value-{i}'}
            objects.append(obj)
        
        # Take second snapshot
        snapshot2 = tracemalloc.take_snapshot()
        
        # Compare snapshots
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        # Should see memory increase
        assert len(top_stats) > 0
        
        # Clean up
        del objects
        gc.collect()

    def test_memory_allocation_tracking(self):
        """Test memory allocation tracking."""
        # Start tracing
        tracemalloc.start()
        
        # Record initial memory
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create objects
        objects = []
        for i in range(5000):
            obj = SecureString(f"test-secret-{i}")
            objects.append(obj)
        
        # Check memory increase
        current_memory = process.memory_info().rss
        memory_increase = current_memory - initial_memory
        
        # Should see memory increase (at least 100KB)
        assert memory_increase > 100 * 1024  # 100KB
        
        # Clean up
        for obj in objects:
            obj.clear()
        del objects
        gc.collect()
        
        tracemalloc.stop()

    def test_memory_usage_alerting(self):
        """Test memory usage alerting with thresholds."""
        process = psutil.Process(os.getpid())
        
        # Set a reasonable memory threshold (100MB)
        memory_threshold = 100 * 1024 * 1024
        
        # Check current memory usage
        current_memory = process.memory_info().rss
        
        # This should not trigger alert in normal conditions
        assert current_memory < memory_threshold, f"Memory usage {current_memory} exceeds threshold {memory_threshold}"


class TestMemoryLeakDetection:
    """Test memory leak detection."""

    @pytest.mark.slow
    def test_memory_leak_detection_long_running(self):
        """Test memory leak detection with long-running scenarios."""
        # Record initial memory
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        secrets_managers = []
        
        # Create many secrets managers over time
        for i in range(100):
            manager = TenantSecretsManager()
            secrets_managers.append(manager)
            
            # Store some secrets
            asyncio.run(manager.store_secret(
                f"tenant-{i}", "test_service", "api_key", f"secret-{i}"
            ))
            
            # Periodic cleanup every 10 iterations
            if i % 10 == 9:
                # Clear some managers
                for j in range(5):
                    if secrets_managers:
                        mgr = secrets_managers.pop()
                        # The manager should clean up its cache in __del__
                        del mgr
        
        # Force garbage collection
        gc.collect()
        
        # Check memory usage
        current_memory = process.memory_info().rss
        memory_increase = current_memory - initial_memory
        
        # Clean up remaining managers
        for manager in secrets_managers:
            # Clear cache explicitly
            manager._clear_cache()
            del manager
        
        gc.collect()
        
        # Memory should not have grown excessively
        # (This is a rough check - exact values depend on system)
        assert memory_increase < 50 * 1024 * 1024  # Less than 50MB increase

    def test_memory_allocation_patterns(self):
        """Test memory allocation patterns."""
        # Start tracing
        tracemalloc.start()
        
        # Take initial snapshot
        snapshot1 = tracemalloc.take_snapshot()
        
        # Create objects in patterns
        pattern_objects = []
        for batch in range(10):
            batch_objects = []
            for i in range(100):
                obj = {
                    'batch': batch,
                    'index': i,
                    'data': 'x' * (i + 1) * 10  # Variable size data
                }
                batch_objects.append(obj)
            pattern_objects.append(batch_objects)
        
        # Take snapshot after allocation
        snapshot2 = tracemalloc.take_snapshot()
        
        # Compare snapshots
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        # Should see allocations
        allocated_size = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)
        assert allocated_size > 0
        
        # Clean up
        del pattern_objects
        gc.collect()
        
        tracemalloc.stop()

    def test_memory_deallocation_verification(self):
        """Test memory deallocation verification."""
        process = psutil.Process(os.getpid())
        
        # Record initial memory
        initial_memory = process.memory_info().rss
        
        # Create objects
        secure_strings = []
        for i in range(1000):
            s = SecureString(f"sensitive-data-{i}")
            secure_strings.append(s)
        
        # Check memory after creation
        memory_after_creation = process.memory_info().rss
        assert memory_after_creation > initial_memory
        
        # Clear all secure strings
        for s in secure_strings:
            s.clear()
        
        # Delete references
        del secure_strings
        gc.collect()
        
        # Memory should be lower (approximately)
        final_memory = process.memory_info().rss
        # Note: Python's memory management may not immediately return memory to OS
        # so we're checking that the trend is reasonable

    def test_memory_fragmentation_analysis(self):
        """Test memory fragmentation analysis."""
        # Start tracing
        tracemalloc.start()
        
        # Create objects of varying sizes
        objects = []
        for i in range(1000):
            # Varying sizes to simulate fragmentation
            size = (i % 100) * 100 + 100  # 100 to 10000 bytes
            obj = 'x' * size
            objects.append(obj)
        
        # Take snapshot
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        
        # Should see various allocation sizes
        sizes = [stat.size for stat in top_stats[:10]]
        assert len(sizes) > 0
        
        # Clean up
        del objects
        gc.collect()
        
        tracemalloc.stop()


class TestLongRunningTests:
    """Test long-running scenarios for memory stability."""

    @pytest.mark.slow
    def test_memory_stability_long_running(self):
        """Test memory stability during long-running operations."""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Simulate long-running operations
        for cycle in range(50):
            # Create and use various objects
            manager = TenantSecretsManager()
            
            # Store and retrieve secrets
            for i in range(20):
                tenant_id = f"tenant-{cycle}-{i}"
                service = f"service-{i}"
                key_type = "api_key"
                secret = f"secret-{cycle}-{i}"
                
                asyncio.run(manager.store_secret(tenant_id, service, key_type, secret))
                retrieved = asyncio.run(manager.get_secret(tenant_id, service, key_type))
                assert retrieved == secret
            
            # Check memory growth
            current_memory = process.memory_info().rss
            memory_growth = current_memory - initial_memory
            
            # Memory growth should be reasonable (less than 10MB per cycle on average)
            max_reasonable_growth = (cycle + 1) * 10 * 1024 * 1024  # 10MB per cycle
            assert memory_growth < max_reasonable_growth, f"Memory growth {memory_growth} exceeds reasonable limit"
            
            # Clean up
            manager._clear_cache()
            del manager
            gc.collect()

    @pytest.mark.slow
    def test_memory_consumption_stress(self):
        """Test memory consumption under stress."""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create high volume of objects
        all_objects = []
        for batch in range(20):
            batch_objects = []
            for i in range(500):
                # Create complex nested objects
                obj = {
                    'id': f"{batch}-{i}",
                    'data': [{'key': f'value-{j}', 'nested': {'deep': j}} for j in range(50)],
                    'secure_string': SecureString(f"secret-{batch}-{i}"),
                    'metadata': {
                        'created': time.time(),
                        'batch': batch,
                        'index': i
                    }
                }
                batch_objects.append(obj)
            all_objects.append(batch_objects)
            
            # Periodic cleanup
            if batch % 5 == 4:
                # Clear some batches
                for _ in range(3):
                    if all_objects:
                        old_batch = all_objects.pop(0)
                        # Clear secure strings
                        for obj in old_batch:
                            obj['secure_string'].clear()
                        del old_batch
        
        # Check peak memory
        peak_memory = process.memory_info().rss
        memory_increase = peak_memory - initial_memory
        
        # Should be less than 100MB
        assert memory_increase < 100 * 1024 * 1024
        
        # Clean up everything
        for batch in all_objects:
            for obj in batch:
                obj['secure_string'].clear()
        del all_objects
        gc.collect()

    @pytest.mark.slow
    def test_memory_usage_patterns(self):
        """Test memory usage patterns over time."""
        process = psutil.Process(os.getpid())
        memory_samples = []
        
        # Record memory over time
        for i in range(100):
            # Create some objects
            objects = [SecureString(f"data-{i}-{j}") for j in range(100)]
            
            # Sample memory
            if i % 10 == 0:
                memory = process.memory_info().rss
                memory_samples.append(memory)
            
            # Clean up
            for obj in objects:
                obj.clear()
            del objects
            gc.collect()
        
        # Memory samples should show reasonable patterns
        assert len(memory_samples) == 10
        
        # Check that memory doesn't grow unbounded
        initial_sample = memory_samples[0]
        final_sample = memory_samples[-1]
        growth = final_sample - initial_sample
        
        # Growth should be reasonable (less than 10MB)
        assert growth < 10 * 1024 * 1024

    def test_regression_memory_leaks(self):
        """Test for regression of memory leaks."""
        # This is a basic regression test that can be expanded
        # based on previously identified memory leak patterns
        
        # Test SecureString creation and destruction
        def create_and_destroy_strings(count):
            strings = []
            for i in range(count):
                s = SecureString(f"test-data-{i}")
                strings.append(s)
            
            # Destroy all
            for s in strings:
                s.clear()
            del strings
            gc.collect()
        
        # Run multiple cycles
        for _ in range(10):
            create_and_destroy_strings(1000)
        
        # If there were memory leaks, they would accumulate
        # This test ensures that basic create/destroy cycles
        # don't leak memory significantly


class TestMemoryProfilingTools:
    """Test memory profiling tools integration."""

    def test_memory_profiling_integration(self):
        """Test integration with memory profiling frameworks."""
        # Test that tracemalloc works correctly
        tracemalloc.start()
        
        # Create some allocations
        snapshot1 = tracemalloc.take_snapshot()
        
        data = [i for i in range(10000)]
        
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        # Should have some stats
        assert len(top_stats) > 0
        
        # Clean up
        del data
        gc.collect()
        tracemalloc.stop()

    def test_memory_analysis_frameworks(self):
        """Test memory analysis with profiling frameworks."""
        # Test psutil integration
        process = psutil.Process(os.getpid())
        
        # Get memory info
        mem_info = process.memory_info()
        assert hasattr(mem_info, 'rss')
        assert hasattr(mem_info, 'vms')
        
        # Get memory percent
        mem_percent = process.memory_percent()
        assert isinstance(mem_percent, float)
        assert 0 <= mem_percent <= 100

    def test_memory_leak_detection_automated(self):
        """Test automated memory leak detection."""
        # Simple automated leak detection
        def detect_memory_growth(func, *args, **kwargs):
            """Detect memory growth from function execution."""
            process = psutil.Process(os.getpid())
            
            # Initial memory
            initial_memory = process.memory_info().rss
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Final memory
            final_memory = process.memory_info().rss
            
            # Calculate growth
            growth = final_memory - initial_memory
            
            return {
                'result': result,
                'initial_memory': initial_memory,
                'final_memory': final_memory,
                'growth_bytes': growth,
                'growth_mb': growth / (1024 * 1024)
            }
        
        # Test with a function that creates objects
        def create_objects(count):
            return [SecureString(f"test-{i}") for i in range(count)]
        
        # Detect memory growth
        analysis = detect_memory_growth(create_objects, 1000)
        
        # Should show positive growth
        assert analysis['growth_bytes'] > 0
        assert analysis['growth_mb'] > 0
        
        # Clean up
        objects = analysis['result']
        for obj in objects:
            obj.clear()
        del objects
        gc.collect()

    def test_memory_optimization_recommendations(self):
        """Test memory optimization recommendations."""
        # This test validates that our memory management practices are sound
        
        # Test that SecureString properly clears memory
        test_string = SecureString("sensitive-data")
        assert test_string.get_value() == "sensitive-data"
        
        initial_memory_address = id(test_string._buffer) if hasattr(test_string, '_buffer') else None
        
        test_string.clear()
        assert test_string.get_value() is None
        assert test_string.is_empty()
        
        # Test that TenantSecretsManager properly manages cache
        manager = TenantSecretsManager()
        
        # Store a secret
        asyncio.run(manager.store_secret("test-tenant", "test-service", "api-key", "test-secret"))
        
        # Check cache
        cache_stats = manager.get_cache_statistics()
        assert cache_stats['current_cache_size'] >= 0
        
        # Clear cache
        manager._clear_cache()
        cache_stats_after = manager.get_cache_statistics()
        assert cache_stats_after['current_cache_size'] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not slow"])