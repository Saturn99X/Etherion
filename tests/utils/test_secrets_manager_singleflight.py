"""
Tests for the singleflight caching functionality in TenantSecretsManager.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock
from src.utils.secrets_manager import TenantSecretsManager, SingleflightManager


class TestSingleflightManager:
    """Test the SingleflightManager class."""
    
    @pytest.fixture
    def singleflight_manager(self):
        return SingleflightManager(cleanup_interval=1, max_request_age=2, enable_cleanup=False)  # Disable cleanup for testing
    
    @pytest.mark.asyncio
    async def test_singleflight_basic_functionality(self, singleflight_manager):
        """Test basic singleflight functionality."""
        try:
            call_count = 0
            
            async def mock_coro(value):
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.1)  # Simulate some work
                return f"result_{value}"
            
            # Start multiple concurrent requests for the same key
            tasks = []
            for i in range(5):
                task = asyncio.create_task(
                    singleflight_manager.get_or_create("test_key", mock_coro, "test_value")
                )
                tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks)
            
            # All results should be the same
            assert all(result == "result_test_value" for result in results)
            
            # The coroutine should only have been called once
            assert call_count == 1
        finally:
            # Clean up
            await singleflight_manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_singleflight_different_keys(self, singleflight_manager):
        """Test that different keys don't interfere with each other."""
        call_count = {}
        
        async def mock_coro(key):
            call_count[key] = call_count.get(key, 0) + 1
            await asyncio.sleep(0.1)
            return f"result_{key}"
        
        # Start concurrent requests for different keys
        tasks = []
        for i in range(3):
            for key in ["key1", "key2", "key3"]:
                task = asyncio.create_task(
                    singleflight_manager.get_or_create(key, mock_coro, key)
                )
                tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)
        
        # Each key should have been called exactly once
        assert call_count["key1"] == 1
        assert call_count["key2"] == 1
        assert call_count["key3"] == 1
        
        # Results should be correct
        assert len([r for r in results if r == "result_key1"]) == 3
        assert len([r for r in results if r == "result_key2"]) == 3
        assert len([r for r in results if r == "result_key3"]) == 3
    
    @pytest.mark.asyncio
    async def test_singleflight_exception_handling(self, singleflight_manager):
        """Test that exceptions are properly propagated to all waiters."""
        call_count = 0
        
        async def failing_coro():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            raise ValueError("Test exception")
        
        # Start multiple concurrent requests
        tasks = []
        for i in range(3):
            task = asyncio.create_task(
                singleflight_manager.get_or_create("failing_key", failing_coro)
            )
            tasks.append(task)
        
        # All tasks should raise the same exception
        with pytest.raises(ValueError, match="Test exception"):
            await asyncio.gather(*tasks)
        
        # The coroutine should only have been called once
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_singleflight_cleanup(self, singleflight_manager):
        """Test that expired requests are cleaned up."""
        # Create a request that will take a long time
        async def slow_coro():
            await asyncio.sleep(2)
            return "slow_result"
        
        # Start a slow request
        task = asyncio.create_task(
            singleflight_manager.get_or_create("slow_key", slow_coro)
        )
        
        # Wait a bit to ensure the request is active
        await asyncio.sleep(0.1)
        
        # Check that there's an active request
        assert singleflight_manager.get_active_count() == 1
        assert "slow_key" in singleflight_manager.get_active_keys()
        
        # Cancel the task
        task.cancel()
        
        # Wait for cleanup
        await asyncio.sleep(0.1)
        
        # The request should be cleaned up
        assert singleflight_manager.get_active_count() == 0
    
    @pytest.mark.asyncio
    async def test_singleflight_shutdown(self, singleflight_manager):
        """Test that shutdown properly cancels all active requests."""
        # Create some active requests
        async def slow_coro():
            await asyncio.sleep(10)  # Very slow
            return "result"
        
        tasks = []
        for i in range(3):
            task = asyncio.create_task(
                singleflight_manager.get_or_create(f"key_{i}", slow_coro)
            )
            tasks.append(task)
        
        # Wait a bit to ensure requests are active
        await asyncio.sleep(0.1)
        assert singleflight_manager.get_active_count() == 3
        
        # Shutdown
        await singleflight_manager.shutdown()
        
        # All tasks should be cancelled
        for task in tasks:
            assert task.cancelled()


class TestTenantSecretsManagerSingleflight:
    """Test singleflight integration in TenantSecretsManager."""
    
    @pytest.fixture
    def secrets_manager(self):
        return TenantSecretsManager()
    
    @pytest.mark.asyncio
    async def test_concurrent_secret_requests(self, secrets_manager):
        """Test that concurrent requests for the same secret use singleflight."""
        # Mock the secret retrieval to simulate a slow operation
        original_method = secrets_manager._simulate_secret_retrieval
        call_count = 0
        
        def mock_slow_retrieval(secret_key):
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)  # Simulate slow retrieval
            return f"secret_value_{call_count}"
        
        secrets_manager._simulate_secret_retrieval = mock_slow_retrieval
        
        try:
            # Start multiple concurrent requests for the same secret
            tasks = []
            for i in range(5):
                task = asyncio.create_task(
                    secrets_manager.get_secret("tenant1", "service1", "api_key")
                )
                tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks)
            
            # All results should be the same (from singleflight)
            assert all(result == "secret_value_1" for result in results)
            
            # The retrieval method should only have been called once
            assert call_count == 1
            
        finally:
            # Restore original method
            secrets_manager._simulate_secret_retrieval = original_method
    
    @pytest.mark.asyncio
    async def test_different_secrets_not_singleflighted(self, secrets_manager):
        """Test that different secrets don't interfere with each other."""
        # Mock the secret retrieval
        original_method = secrets_manager._simulate_secret_retrieval
        call_count = {}
        
        def mock_retrieval(secret_key):
            call_count[secret_key] = call_count.get(secret_key, 0) + 1
            time.sleep(0.1)  # Simulate slow retrieval
            return f"secret_value_{secret_key}"
        
        secrets_manager._simulate_secret_retrieval = mock_retrieval
        
        try:
            # Start concurrent requests for different secrets
            tasks = []
            secrets = [
                ("tenant1", "service1", "api_key"),
                ("tenant1", "service2", "api_key"),
                ("tenant2", "service1", "api_key")
            ]
            
            for tenant_id, service_name, key_type in secrets:
                for i in range(2):  # Multiple requests per secret
                    task = asyncio.create_task(
                        secrets_manager.get_secret(tenant_id, service_name, key_type)
                    )
                    tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks)
            
            # Each secret should have been retrieved exactly once
            assert call_count["tenant1--service1--api_key"] == 1
            assert call_count["tenant1--service2--api_key"] == 1
            assert call_count["tenant2--service1--api_key"] == 1
            
        finally:
            # Restore original method
            secrets_manager._simulate_secret_retrieval = original_method
    
    @pytest.mark.asyncio
    async def test_singleflight_stats(self, secrets_manager):
        """Test that singleflight statistics are available."""
        # Initially no active requests
        stats = secrets_manager.get_singleflight_stats()
        assert stats["active_requests"] == 0
        assert stats["active_keys"] == []
        
        # Start a slow request
        async def slow_retrieval(secret_key):
            await asyncio.sleep(0.2)
            return "slow_secret"
        
        # Mock the retrieval method
        original_method = secrets_manager._retrieve_secret_from_storage
        secrets_manager._retrieve_secret_from_storage = slow_retrieval
        
        try:
            # Start a request
            task = asyncio.create_task(
                secrets_manager.get_secret("tenant1", "service1", "api_key")
            )
            
            # Wait a bit to ensure request is active
            await asyncio.sleep(0.1)
            
            # Check stats
            stats = secrets_manager.get_singleflight_stats()
            assert stats["active_requests"] == 1
            assert "tenant1--service1--api_key" in stats["active_keys"]
            
            # Wait for completion
            await task
            
            # Stats should be cleared
            stats = secrets_manager.get_singleflight_stats()
            assert stats["active_requests"] == 0
            
        finally:
            # Restore original method
            secrets_manager._retrieve_secret_from_storage = original_method
    
    @pytest.mark.asyncio
    async def test_singleflight_with_cache_hit(self, secrets_manager):
        """Test that singleflight doesn't interfere with cache hits."""
        # First, populate the cache
        await secrets_manager.store_secret("tenant1", "service1", "api_key", "cached_secret")
        
        # Mock the retrieval method to track calls
        original_method = secrets_manager._simulate_secret_retrieval
        call_count = 0
        
        def mock_retrieval(secret_key):
            nonlocal call_count
            call_count += 1
            return "retrieved_secret"
        
        secrets_manager._simulate_secret_retrieval = mock_retrieval
        
        try:
            # Start multiple concurrent requests
            tasks = []
            for i in range(5):
                task = asyncio.create_task(
                    secrets_manager.get_secret("tenant1", "service1", "api_key")
                )
                tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks)
            
            # All results should be from cache
            assert all(result == "cached_secret" for result in results)
            
            # The retrieval method should not have been called
            assert call_count == 0
            
        finally:
            # Restore original method
            secrets_manager._simulate_secret_retrieval = original_method
    
    @pytest.mark.asyncio
    async def test_singleflight_error_handling(self, secrets_manager):
        """Test that errors in singleflight are properly handled."""
        # Mock the retrieval method to raise an exception
        original_method = secrets_manager._retrieve_secret_from_storage
        
        async def failing_retrieval(secret_key, tenant_id, service_name, key_type):
            raise ValueError("Secret retrieval failed")
        
        secrets_manager._retrieve_secret_from_storage = failing_retrieval
        
        try:
            # Start multiple concurrent requests
            tasks = []
            for i in range(3):
                task = asyncio.create_task(
                    secrets_manager.get_secret("tenant1", "service1", "api_key")
                )
                tasks.append(task)
            
            # All tasks should return None (error handling)
            results = await asyncio.gather(*tasks)
            assert all(result is None for result in results)
            
        finally:
            # Restore original method
            secrets_manager._retrieve_secret_from_storage = original_method
    
    @pytest.mark.asyncio
    async def test_secrets_manager_shutdown(self, secrets_manager):
        """Test that secrets manager shutdown properly cleans up singleflight."""
        # Start some active requests
        async def slow_retrieval(secret_key, tenant_id, service_name, key_type):
            await asyncio.sleep(10)  # Very slow
            return "slow_secret"
        
        original_method = secrets_manager._retrieve_secret_from_storage
        secrets_manager._retrieve_secret_from_storage = slow_retrieval
        
        try:
            # Start some requests
            tasks = []
            for i in range(3):
                task = asyncio.create_task(
                    secrets_manager.get_secret(f"tenant{i}", "service1", "api_key")
                )
                tasks.append(task)
            
            # Wait a bit to ensure requests are active
            await asyncio.sleep(0.1)
            assert secrets_manager.get_singleflight_stats()["active_requests"] > 0
            
            # Shutdown
            await secrets_manager.shutdown()
            
            # All tasks should be cancelled
            for task in tasks:
                assert task.cancelled()
            
        finally:
            # Restore original method
            secrets_manager._retrieve_secret_from_storage = original_method


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
