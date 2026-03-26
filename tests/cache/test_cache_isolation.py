"""
Tests for cache isolation and tenant separation.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock
from src.cache.cache_engine import (
    ThreeLayerCache, L1MemoryCache, L2RedisCache, L3DatabaseCache,
    CacheLevel, CacheEntry, cache_key, cached
)


class TestL1MemoryCache:
    """Test L1 memory cache isolation."""
    
    def test_tenant_isolation(self):
        """Test that tenants cannot access each other's cache entries."""
        cache = L1MemoryCache(max_size=100, default_ttl=3600)
        
        # Set values for different tenants
        cache.set("key1", "value1", tenant_id="tenant1")
        cache.set("key1", "value2", tenant_id="tenant2")
        cache.set("key2", "value3", tenant_id="tenant1")
        
        # Verify isolation
        assert cache.get("key1", "tenant1") == "value1"
        assert cache.get("key1", "tenant2") == "value2"
        assert cache.get("key2", "tenant1") == "value3"
        assert cache.get("key2", "tenant2") is None
        assert cache.get("key1") is None  # No tenant specified
    
    def test_tenant_cache_clearing(self):
        """Test clearing cache for specific tenant."""
        cache = L1MemoryCache(max_size=100, default_ttl=3600)
        
        # Set values for multiple tenants
        cache.set("key1", "value1", tenant_id="tenant1")
        cache.set("key2", "value2", tenant_id="tenant1")
        cache.set("key1", "value3", tenant_id="tenant2")
        
        # Clear tenant1 cache
        cleared_count = cache.clear_tenant("tenant1")
        
        # Verify tenant1 cache is cleared
        assert cleared_count == 2
        assert cache.get("key1", "tenant1") is None
        assert cache.get("key2", "tenant1") is None
        
        # Verify tenant2 cache is intact
        assert cache.get("key1", "tenant2") == "value3"
    
    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        cache = L1MemoryCache(max_size=100, default_ttl=0.1)  # 100ms TTL
        
        cache.set("key1", "value1", ttl=0.1, tenant_id="tenant1")
        assert cache.get("key1", "tenant1") == "value1"
        
        # Wait for expiration
        time.sleep(0.2)
        assert cache.get("key1", "tenant1") is None
    
    def test_lru_eviction(self):
        """Test LRU eviction policy."""
        cache = L1MemoryCache(max_size=3, default_ttl=3600)
        
        # Fill cache
        cache.set("key1", "value1", tenant_id="tenant1")
        cache.set("key2", "value2", tenant_id="tenant1")
        cache.set("key3", "value3", tenant_id="tenant1")
        
        # Access key1 to make it recently used
        cache.get("key1", "tenant1")
        
        # Add one more entry to trigger eviction
        cache.set("key4", "value4", tenant_id="tenant1")
        
        # key2 should be evicted (least recently used)
        assert cache.get("key1", "tenant1") == "value1"  # Recently accessed
        assert cache.get("key2", "tenant1") is None  # Evicted
        assert cache.get("key3", "tenant1") == "value3"
        assert cache.get("key4", "tenant1") == "value4"


class TestL2RedisCache:
    """Test L2 Redis cache isolation."""
    
    @pytest.mark.asyncio
    async def test_redis_initialization(self):
        """Test Redis cache initialization."""
        with patch('aioredis.ConnectionPool.from_url') as mock_pool, \
             patch('aioredis.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            
            cache = L2RedisCache("redis://localhost:6379")
            await cache.initialize()
            
            assert cache._redis is not None
            mock_redis_instance.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tenant_isolation_redis(self):
        """Test tenant isolation in Redis cache."""
        with patch('aioredis.ConnectionPool.from_url'), \
             patch('aioredis.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.get.return_value = None
            mock_redis_instance.setex.return_value = True
            mock_redis_instance.hset.return_value = True
            mock_redis_instance.expire.return_value = True
            
            cache = L2RedisCache("redis://localhost:6379")
            await cache.initialize()
            
            # Set values for different tenants
            await cache.set("key1", "value1", tenant_id="tenant1")
            await cache.set("key1", "value2", tenant_id="tenant2")
            
            # Verify different keys are used
            calls = mock_redis_instance.setex.call_args_list
            assert len(calls) == 2
            assert calls[0][0][0] == "cache:tenant1:key1"
            assert calls[1][0][0] == "cache:tenant2:key1"
    
    @pytest.mark.asyncio
    async def test_redis_tenant_clearing(self):
        """Test clearing Redis cache for specific tenant."""
        with patch('aioredis.ConnectionPool.from_url'), \
             patch('aioredis.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.keys.return_value = [b"cache:tenant1:key1", b"cache:tenant1:key2"]
            mock_redis_instance.delete.return_value = 2
            
            cache = L2RedisCache("redis://localhost:6379")
            await cache.initialize()
            
            cleared_count = await cache.clear_tenant("tenant1")
            
            assert cleared_count == 2
            mock_redis_instance.keys.assert_called_with("cache:tenant1:*")
            mock_redis_instance.delete.assert_called_once()


class TestThreeLayerCache:
    """Test three-layer cache system."""
    
    @pytest.mark.asyncio
    async def test_cache_fallback(self):
        """Test cache fallback through layers."""
        with patch('aioredis.ConnectionPool.from_url'), \
             patch('aioredis.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.get.return_value = None
            
            cache = ThreeLayerCache()
            await cache.initialize()
            
            # L1 cache miss, L2 cache miss, L3 cache miss
            result = await cache.get("nonexistent_key", "tenant1")
            assert result is None
            
            # Set in L1 only
            await cache.set("key1", "value1", tenant_id="tenant1", levels=[CacheLevel.L1_MEMORY])
            
            # Should find in L1
            result = await cache.get("key1", "tenant1")
            assert result == "value1"
            
            # Set in L2
            await cache.set("key2", "value2", tenant_id="tenant1", levels=[CacheLevel.L2_REDIS])
            
            # Should find in L2 and promote to L1
            result = await cache.get("key2", "tenant1")
            assert result == "value2"
            
            # Should now be in L1 as well
            result = await cache.get("key2", "tenant1")
            assert result == "value2"
    
    @pytest.mark.asyncio
    async def test_tenant_isolation_three_layer(self):
        """Test tenant isolation across all layers."""
        with patch('aioredis.ConnectionPool.from_url'), \
             patch('aioredis.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.get.return_value = None
            mock_redis_instance.setex.return_value = True
            mock_redis_instance.hset.return_value = True
            mock_redis_instance.expire.return_value = True
            
            cache = ThreeLayerCache()
            await cache.initialize()
            
            # Set values for different tenants
            await cache.set("key1", "value1", tenant_id="tenant1")
            await cache.set("key1", "value2", tenant_id="tenant2")
            
            # Verify isolation
            result1 = await cache.get("key1", "tenant1")
            result2 = await cache.get("key1", "tenant2")
            
            assert result1 == "value1"
            assert result2 == "value2"
    
    @pytest.mark.asyncio
    async def test_cache_deletion(self):
        """Test cache deletion across layers."""
        with patch('aioredis.ConnectionPool.from_url'), \
             patch('aioredis.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.delete.return_value = 1
            
            cache = ThreeLayerCache()
            await cache.initialize()
            
            # Set value in multiple layers
            await cache.set("key1", "value1", tenant_id="tenant1")
            
            # Delete from all layers
            deleted = await cache.delete("key1", "tenant1")
            assert deleted is True
            
            # Verify deletion
            result = await cache.get("key1", "tenant1")
            assert result is None


class TestCacheDecorator:
    """Test cache decorator functionality."""
    
    @pytest.mark.asyncio
    async def test_cached_decorator(self):
        """Test the @cached decorator."""
        with patch('aioredis.ConnectionPool.from_url'), \
             patch('aioredis.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.get.return_value = None
            mock_redis_instance.setex.return_value = True
            mock_redis_instance.hset.return_value = True
            mock_redis_instance.expire.return_value = True
            
            # Create cache instance
            cache = ThreeLayerCache()
            await cache.initialize()
            
            # Mock the get_cache function
            with patch('src.cache.cache_engine.get_cache', return_value=cache):
                
                call_count = 0
                
                @cached(ttl=3600, tenant_aware=True)
                async def expensive_function(param1: str, param2: int, tenant_id: str):
                    nonlocal call_count
                    call_count += 1
                    return f"result_{param1}_{param2}_{tenant_id}"
                
                # First call - should execute function
                result1 = await expensive_function("test", 123, "tenant1")
                assert result1 == "result_test_123_tenant1"
                assert call_count == 1
                
                # Second call - should use cache
                result2 = await expensive_function("test", 123, "tenant1")
                assert result2 == "result_test_123_tenant1"
                assert call_count == 1  # Function not called again
                
                # Different tenant - should execute function
                result3 = await expensive_function("test", 123, "tenant2")
                assert result3 == "result_test_123_tenant2"
                assert call_count == 2


class TestCacheMetrics:
    """Test cache metrics and statistics."""
    
    def test_l1_cache_stats(self):
        """Test L1 cache statistics."""
        cache = L1MemoryCache(max_size=100, default_ttl=3600)
        
        # Set some values
        cache.set("key1", "value1", tenant_id="tenant1")
        cache.set("key2", "value2", tenant_id="tenant1")
        cache.get("key1", "tenant1")  # Access to increase hit count
        
        stats = cache.get_stats()
        
        assert stats['size'] == 2
        assert stats['max_size'] == 100
        assert stats['hit_rate'] > 0
        assert stats['memory_usage'] > 0
    
    @pytest.mark.asyncio
    async def test_redis_cache_stats(self):
        """Test Redis cache statistics."""
        with patch('aioredis.ConnectionPool.from_url'), \
             patch('aioredis.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.info.return_value = {
                'connected_clients': 5,
                'used_memory': 1024000,
                'keyspace_hits': 100,
                'keyspace_misses': 50
            }
            
            cache = L2RedisCache("redis://localhost:6379")
            await cache.initialize()
            
            stats = await cache.get_stats()
            
            assert stats['connected_clients'] == 5
            assert stats['used_memory'] == 1024000
            assert stats['keyspace_hits'] == 100
            assert stats['keyspace_misses'] == 50
            assert stats['hit_rate'] == 100 / 150  # 100 hits / 150 total


class TestCacheKeyGeneration:
    """Test cache key generation."""
    
    def test_cache_key_generation(self):
        """Test cache key generation from function arguments."""
        key1 = cache_key("func_name", "arg1", 123, param1="value1", param2="value2")
        key2 = cache_key("func_name", "arg1", 123, param2="value2", param1="value1")
        key3 = cache_key("func_name", "arg1", 456, param1="value1", param2="value2")
        
        # Same arguments should generate same key
        assert key1 == key2
        
        # Different arguments should generate different keys
        assert key1 != key3
        
        # Keys should be consistent
        assert len(key1) == 32  # MD5 hash length
        assert key1.isalnum()  # Should be alphanumeric


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
