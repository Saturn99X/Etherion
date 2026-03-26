#!/usr/bin/env python3
"""
Integration tests for cache isolation in multi-tenant scenarios.
"""

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from src.utils.secrets_manager import TenantSecretsManager
from src.utils.secure_string import SecureString


class TestCacheIsolation:
    """Test cache isolation in multi-tenant scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tenant_secrets_manager = TenantSecretsManager()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        # Clear cache to avoid interference between tests
        self.tenant_secrets_manager._clear_cache()

    def test_cache_isolation_between_tenants(self):
        """Test that cache entries are isolated between different tenants."""
        # Store secrets for tenant 1
        tenant1_id = f"tenant1-{uuid.uuid4().hex[:8]}"
        secret1_value = "secret-value-tenant1"
        
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant1_id, "test_service", "api_key", secret1_value
        ))
        
        # Store secrets for tenant 2
        tenant2_id = f"tenant2-{uuid.uuid4().hex[:8]}"
        secret2_value = "secret-value-tenant2"
        
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant2_id, "test_service", "api_key", secret2_value
        ))
        
        # Retrieve secrets for each tenant
        retrieved_secret1 = asyncio.run(self.tenant_secrets_manager.get_secret(
            tenant1_id, "test_service", "api_key"
        ))
        
        retrieved_secret2 = asyncio.run(self.tenant_secrets_manager.get_secret(
            tenant2_id, "test_service", "api_key"
        ))
        
        # Verify isolation
        assert retrieved_secret1 == secret1_value
        assert retrieved_secret2 == secret2_value
        assert retrieved_secret1 != retrieved_secret2

    def test_cross_tenant_data_access_prevention(self):
        """Test that tenants cannot access each other's cached data."""
        # Store secret for tenant 1
        tenant1_id = f"tenant1-{uuid.uuid4().hex[:8]}"
        secret_value = "confidential-secret-tenant1"
        
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant1_id, "confidential_service", "private_key", secret_value
        ))
        
        # Try to access the same secret using tenant 2's ID
        tenant2_id = f"tenant2-{uuid.uuid4().hex[:8]}"
        
        # This should return None or a different value, not the tenant1 secret
        retrieved_secret = asyncio.run(self.tenant_secrets_manager.get_secret(
            tenant2_id, "confidential_service", "private_key"
        ))
        
        # Verify that tenant 2 cannot access tenant 1's secret
        assert retrieved_secret != secret_value
        # In a real implementation, this might return None or raise an exception

    def test_cache_key_namespace_separation(self):
        """Test that cache keys are properly namespaced by tenant."""
        tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
        service_name = "test_service"
        key_type1 = "api_key"
        key_type2 = "secret_key"
        
        secret1 = "api-key-value"
        secret2 = "secret-key-value"
        
        # Store two different secrets for the same tenant
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant_id, service_name, key_type1, secret1
        ))
        
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant_id, service_name, key_type2, secret2
        ))
        
        # Retrieve both secrets
        retrieved_secret1 = asyncio.run(self.tenant_secrets_manager.get_secret(
            tenant_id, service_name, key_type1
        ))
        
        retrieved_secret2 = asyncio.run(self.tenant_secrets_manager.get_secret(
            tenant_id, service_name, key_type2
        ))
        
        # Verify that both secrets are stored and retrieved correctly
        assert retrieved_secret1 == secret1
        assert retrieved_secret2 == secret2
        assert retrieved_secret1 != retrieved_secret2

    def test_tenant_specific_cache_operations(self):
        """Test tenant-specific cache operations."""
        tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
        service_name = "test_service"
        key_type = "api_key"
        secret_value = "test-secret-value"
        
        # Test storing a secret
        result = asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant_id, service_name, key_type, secret_value
        ))
        assert result is True
        
        # Test retrieving the secret
        retrieved_secret = asyncio.run(self.tenant_secrets_manager.get_secret(
            tenant_id, service_name, key_type
        ))
        assert retrieved_secret == secret_value
        
        # Test cache statistics
        stats = self.tenant_secrets_manager.get_cache_statistics()
        assert stats['total_accesses'] >= 1
        assert stats['hits'] >= 0
        assert stats['misses'] >= 0

    @pytest.mark.asyncio
    async def test_concurrent_cache_access_patterns(self):
        """Test concurrent cache access patterns."""
        tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
        service_name = "concurrent_test_service"
        key_type = "api_key"
        secret_value = "concurrent-test-secret"
        
        # Store initial secret
        await self.tenant_secrets_manager.store_secret(
            tenant_id, service_name, key_type, secret_value
        )
        
        # Simulate concurrent access
        async def access_cache():
            return await self.tenant_secrets_manager.get_secret(
                tenant_id, service_name, key_type
            )
        
        # Create multiple concurrent tasks
        tasks = [access_cache() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # Verify all results are correct
        for result in results:
            assert result == secret_value

    def test_race_condition_detection(self):
        """Test for race conditions in cache operations."""
        tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
        service_name = "race_test_service"
        key_type = "api_key"
        
        def store_and_retrieve(value):
            """Function to store and immediately retrieve a secret."""
            asyncio.run(self.tenant_secrets_manager.store_secret(
                tenant_id, service_name, key_type, value
            ))
            return asyncio.run(self.tenant_secrets_manager.get_secret(
                tenant_id, service_name, key_type
            ))
        
        # Run multiple threads simultaneously
        values = [f"value-{i}" for i in range(10)]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(store_and_retrieve, value) for value in values]
            results = [future.result() for future in futures]
        
        # At least one result should match one of the values (due to race conditions)
        # But we're testing that the system doesn't crash or corrupt data
        assert all(result is not None for result in results)

    def test_lock_contention_scenarios(self):
        """Test lock contention scenarios."""
        tenant_ids = [f"tenant-{uuid.uuid4().hex[:8]}" for _ in range(5)]
        service_name = "contention_test_service"
        key_type = "api_key"
        
        def intensive_cache_operation(tenant_id):
            """Perform intensive cache operations for a tenant."""
            for i in range(20):
                secret_value = f"secret-{tenant_id}-{i}"
                asyncio.run(self.tenant_secrets_manager.store_secret(
                    tenant_id, service_name, key_type, secret_value
                ))
                retrieved = asyncio.run(self.tenant_secrets_manager.get_secret(
                    tenant_id, service_name, key_type
                ))
                assert retrieved == secret_value
            return True
        
        # Run multiple threads with different tenants
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(intensive_cache_operation, tenant_id) 
                      for tenant_id in tenant_ids]
            results = [future.result() for future in futures]
        
        # All operations should complete successfully
        assert all(results)

    def test_cache_consistency_verification(self):
        """Test cache consistency verification."""
        tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
        service_name = "consistency_test_service"
        key_type = "api_key"
        original_value = "original-value"
        
        # Store initial value
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant_id, service_name, key_type, original_value
        ))
        
        # Retrieve multiple times to check consistency
        retrieved_values = []
        for _ in range(5):
            value = asyncio.run(self.tenant_secrets_manager.get_secret(
                tenant_id, service_name, key_type
            ))
            retrieved_values.append(value)
        
        # All retrieved values should be the same
        assert all(value == original_value for value in retrieved_values)

    def test_cache_update_propagation(self):
        """Test cache update propagation."""
        tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
        service_name = "update_test_service"
        key_type = "api_key"
        initial_value = "initial-value"
        updated_value = "updated-value"
        
        # Store initial value
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant_id, service_name, key_type, initial_value
        ))
        
        # Verify initial value
        retrieved = asyncio.run(self.tenant_secrets_manager.get_secret(
            tenant_id, service_name, key_type
        ))
        assert retrieved == initial_value
        
        # Update value
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant_id, service_name, key_type, updated_value
        ))
        
        # Verify updated value is propagated
        retrieved = asyncio.run(self.tenant_secrets_manager.get_secret(
            tenant_id, service_name, key_type
        ))
        assert retrieved == updated_value

    def test_cache_version_validation(self):
        """Test cache version validation."""
        tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
        service_name = "version_test_service"
        key_type = "api_key"
        
        # Store a secret
        secret_v1 = "secret-version-1"
        asyncio.run(self.tenant_secrets_manager.store_secret(
            tenant_id, service_name, key_type, secret_v1
        ))
        
        # Get cache contents to check version info
        cache_contents = self.tenant_secrets_manager.get_cache_contents()
        
        # Verify that cache entries have version information
        assert len(cache_contents) > 0
        for entry in cache_contents:
            assert 'version' in entry
            assert isinstance(entry['version'], int)
            assert entry['version'] >= 1

    def test_secure_string_memory_isolation(self):
        """Test that SecureString properly isolates memory."""
        # Create two secure strings with different values
        value1 = "sensitive-data-1"
        value2 = "sensitive-data-2"
        
        secure_str1 = SecureString(value1)
        secure_str2 = SecureString(value2)
        
        # Verify values are stored correctly
        assert secure_str1.get_value() == value1
        assert secure_str2.get_value() == value2
        
        # Verify they are different objects
        assert secure_str1 is not secure_str2
        assert secure_str1.get_value() != secure_str2.get_value()
        
        # Test clearing
        secure_str1.clear()
        assert secure_str1.get_value() is None
        # secure_str2 should still have its value
        assert secure_str2.get_value() == value2

    def test_secure_memory_wiping(self):
        """Test that memory is properly wiped when SecureString is cleared."""
        value = "test-sensitive-data"
        secure_str = SecureString(value)
        
        # Verify value is stored
        assert secure_str.get_value() == value
        
        # Clear the secure string
        secure_str.clear()
        
        # Verify value is wiped
        assert secure_str.get_value() is None
        assert secure_str.is_empty()

    def test_concurrent_secure_string_operations(self):
        """Test concurrent operations on SecureString."""
        def create_and_use_secure_string(value):
            secure_str = SecureString(value)
            result = secure_str.get_value()
            secure_str.clear()
            return result
        
        values = [f"value-{i}" for i in range(10)]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_and_use_secure_string, value) 
                      for value in values]
            results = [future.result() for future in futures]
        
        # All operations should complete successfully
        assert results == values


if __name__ == "__main__":
    pytest.main([__file__, "-v"])