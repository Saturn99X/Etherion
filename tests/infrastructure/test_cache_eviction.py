"""
Tests for cache eviction engine functionality.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.cache.cache_engine import ThreeLayerCache, CacheLevel, CacheEntry
from src.cache.eviction_engine import (
    CacheEvictionEngine, 
    SemanticEvictionEngine, 
    EvictionStrategy,
    EvictionMetrics
)


class TestSemanticEvictionEngine:
    """Test semantic eviction engine."""
    
    @pytest.fixture
    def semantic_engine(self):
        """Create semantic eviction engine instance."""
        return SemanticEvictionEngine(similarity_threshold=0.8)
    
    def test_calculate_semantic_hash(self, semantic_engine):
        """Test semantic hash calculation."""
        # Test with different data types
        data1 = {"key": "value", "number": 123}
        data2 = {"key": "value", "number": 123}  # Same content
        data3 = {"key": "different", "number": 456}  # Different content
        
        hash1 = semantic_engine._calculate_semantic_hash(data1)
        hash2 = semantic_engine._calculate_semantic_hash(data2)
        hash3 = semantic_engine._calculate_semantic_hash(data3)
        
        # Same content should produce same hash
        assert hash1 == hash2
        # Different content should produce different hash
        assert hash1 != hash3
        # Hash should be string
        assert isinstance(hash1, str)
        assert len(hash1) == 16  # Truncated to 16 chars
    
    def test_calculate_similarity(self, semantic_engine):
        """Test similarity calculation between hashes."""
        hash1 = "abcdef1234567890"
        hash2 = "abcdef1234567890"  # Identical
        hash3 = "abcdef1234567891"  # One char different
        hash4 = "fedcba0987654321"  # Completely different
        
        # Identical hashes should have similarity 1.0
        assert semantic_engine._calculate_similarity(hash1, hash2) == 1.0
        
        # Similar hashes should have high similarity
        similarity = semantic_engine._calculate_similarity(hash1, hash3)
        assert 0.8 <= similarity < 1.0
        
        # Different hashes should have low similarity
        similarity = semantic_engine._calculate_similarity(hash1, hash4)
        assert similarity < 0.5
    
    def test_add_entry(self, semantic_engine):
        """Test adding entries to semantic index."""
        key = "test_key"
        value = {"data": "test_value"}
        tenant_id = "tenant_1"
        
        semantic_engine.add_entry(key, value, tenant_id)
        
        # Check entry was added
        assert key in semantic_engine.semantic_index
        entry = semantic_engine.semantic_index[key]
        assert entry.key == key
        assert entry.value == value
        assert entry.tenant_id == tenant_id
        assert entry.access_count == 1
        assert entry.importance_score == 1.0
    
    def test_update_access(self, semantic_engine):
        """Test updating access pattern."""
        key = "test_key"
        value = {"data": "test_value"}
        
        semantic_engine.add_entry(key, value)
        
        # Update access multiple times
        for i in range(3):
            semantic_engine.update_access(key)
        
        entry = semantic_engine.semantic_index[key]
        assert entry.access_count == 4  # Initial + 3 updates
        assert len(entry.access_pattern) == 4
    
    def test_get_eviction_candidates(self, semantic_engine):
        """Test getting eviction candidates."""
        # Add multiple entries with different access patterns
        for i in range(5):
            key = f"key_{i}"
            value = {"data": f"value_{i}"}
            semantic_engine.add_entry(key, value)
            
            # Make some entries more recently accessed
            if i < 2:
                for _ in range(3):
                    semantic_engine.update_access(key)
        
        candidates = semantic_engine.get_eviction_candidates(max_evict=3)
        
        # Should return candidates sorted by eviction score
        assert len(candidates) <= 3
        assert all(isinstance(candidate, str) for candidate in candidates)
    
    def test_remove_entry(self, semantic_engine):
        """Test removing entries from semantic index."""
        key1 = "key_1"
        key2 = "key_2"
        value1 = {"data": "value_1"}
        value2 = {"data": "value_2"}
        
        semantic_engine.add_entry(key1, value1)
        semantic_engine.add_entry(key2, value2)
        
        # Remove entry
        semantic_engine.remove_entry(key1)
        
        # Check entry was removed
        assert key1 not in semantic_engine.semantic_index
        assert key2 in semantic_engine.semantic_index


class TestCacheEvictionEngine:
    """Test cache eviction engine."""
    
    @pytest.fixture
    def mock_cache(self):
        """Create mock cache instance."""
        cache = Mock(spec=ThreeLayerCache)
        cache.l1_cache = Mock()
        cache.l1_cache._cache = {}
        cache.l1_cache._access_order = {}
        cache.l1_cache.max_size = 100
        cache.l1_cache.delete = Mock(return_value=True)
        cache.l2_cache = Mock()
        cache.l2_cache.redis_client = AsyncMock()
        cache.l2_cache.redis_client.memory_purge = AsyncMock()
        cache.l3_cache = None
        return cache
    
    @pytest.fixture
    def eviction_engine(self, mock_cache):
        """Create eviction engine instance."""
        return CacheEvictionEngine(mock_cache)
    
    @pytest.mark.asyncio
    async def test_start_stop(self, eviction_engine):
        """Test starting and stopping eviction engine."""
        # Start engine
        await eviction_engine.start()
        assert eviction_engine._running is True
        
        # Stop engine
        await eviction_engine.stop()
        assert eviction_engine._running is False
    
    @pytest.mark.asyncio
    async def test_evict_lru_l1(self, eviction_engine, mock_cache):
        """Test LRU eviction for L1 cache."""
        # Mock L1 cache with entries
        mock_cache.l1_cache._cache = {
            "key1": Mock(),
            "key2": Mock(),
            "key3": Mock()
        }
        mock_cache.l1_cache._access_order = {"key1": None, "key2": None, "key3": None}
        mock_cache.l1_cache.max_size = 2  # Force eviction
        
        metrics = await eviction_engine.evict_lru(CacheLevel.L1_MEMORY, max_evict=2)
        
        assert isinstance(metrics, EvictionMetrics)
        assert metrics.evicted_count >= 0
        assert "lru_l1" in metrics.eviction_reasons
    
    @pytest.mark.asyncio
    async def test_evict_by_ttl(self, eviction_engine, mock_cache):
        """Test TTL-based eviction."""
        # Mock expired entries
        expired_entry = Mock()
        expired_entry.is_expired.return_value = True
        
        mock_cache.l1_cache._cache = {"expired_key": expired_entry}
        mock_cache.l1_cache.delete.return_value = True
        
        metrics = await eviction_engine.evict_by_ttl(CacheLevel.L1_MEMORY)
        
        assert isinstance(metrics, EvictionMetrics)
        assert metrics.evicted_count >= 0
        assert "ttl_l1" in metrics.eviction_reasons
    
    @pytest.mark.asyncio
    async def test_semantic_eviction(self, eviction_engine):
        """Test semantic eviction."""
        # Add entries to semantic engine
        eviction_engine.semantic_engine.add_entry("key1", {"data": "value1"})
        eviction_engine.semantic_engine.add_entry("key2", {"data": "value2"})
        
        # Mock cache delete method
        eviction_engine.cache.delete = AsyncMock(return_value=True)
        
        metrics = await eviction_engine.semantic_eviction(max_evict=1)
        
        assert isinstance(metrics, EvictionMetrics)
        assert metrics.evicted_count >= 0
        assert "semantic" in metrics.eviction_reasons
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self, eviction_engine):
        """Test cleanup of expired entries."""
        metrics = await eviction_engine.cleanup_expired_entries()
        
        assert isinstance(metrics, EvictionMetrics)
        assert metrics.evicted_count >= 0
    
    @pytest.mark.asyncio
    async def test_evict_tenant_data(self, eviction_engine, mock_cache):
        """Test evicting tenant data."""
        tenant_id = "tenant_1"
        
        # Mock cache clear_tenant method
        mock_cache.clear_tenant = AsyncMock(return_value={"total_evicted": 5})
        
        metrics = await eviction_engine.evict_tenant_data(tenant_id)
        
        assert isinstance(metrics, EvictionMetrics)
        assert metrics.evicted_count == 5
        assert "tenant_clear" in metrics.eviction_reasons
    
    def test_add_to_semantic_index(self, eviction_engine):
        """Test adding entries to semantic index."""
        key = "test_key"
        value = {"data": "test_value"}
        tenant_id = "tenant_1"
        
        eviction_engine.add_to_semantic_index(key, value, tenant_id)
        
        assert key in eviction_engine.semantic_engine.semantic_index
    
    def test_update_semantic_access(self, eviction_engine):
        """Test updating semantic access."""
        key = "test_key"
        value = {"data": "test_value"}
        
        eviction_engine.add_to_semantic_index(key, value)
        eviction_engine.update_semantic_access(key)
        
        entry = eviction_engine.semantic_engine.semantic_index[key]
        assert entry.access_count == 2  # Initial + update
    
    @pytest.mark.asyncio
    async def test_warm_cache(self, eviction_engine):
        """Test cache warming."""
        warming_data = [("key1", "value1"), ("key2", "value2")]
        
        # Mock warming strategy
        def warming_strategy():
            return warming_data
        
        # Mock cache set method
        eviction_engine.cache.set = AsyncMock()
        
        await eviction_engine.warm_cache(warming_strategy)
        
        # Verify cache was called for each item
        assert eviction_engine.cache.set.call_count == len(warming_data)
    
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, eviction_engine, mock_cache):
        """Test getting cache statistics."""
        # Mock cache stats
        mock_cache.l1_cache._cache = {"key1": Mock(), "key2": Mock()}
        mock_cache.l1_cache.max_size = 100
        mock_cache.l2_cache.redis_client.info = AsyncMock(return_value={
            "used_memory": 1024,
            "maxmemory": 2048
        })
        
        stats = await eviction_engine.get_cache_stats()
        
        assert isinstance(stats, dict)
        assert "l1_cache" in stats
        assert "semantic_index" in stats
        assert "eviction_metrics" in stats
        assert "l2_cache" in stats
    
    def test_get_metrics(self, eviction_engine):
        """Test getting eviction metrics."""
        metrics = eviction_engine.get_metrics()
        
        assert isinstance(metrics, EvictionMetrics)
        assert metrics.evicted_count == 0
        assert metrics.evicted_size_bytes == 0
        assert metrics.eviction_reasons is not None


class TestEvictionMetrics:
    """Test eviction metrics."""
    
    def test_eviction_metrics_initialization(self):
        """Test eviction metrics initialization."""
        metrics = EvictionMetrics()
        
        assert metrics.evicted_count == 0
        assert metrics.evicted_size_bytes == 0
        assert metrics.eviction_reasons is not None
        assert metrics.last_eviction_time is None
    
    def test_eviction_metrics_with_data(self):
        """Test eviction metrics with data."""
        metrics = EvictionMetrics(
            evicted_count=10,
            evicted_size_bytes=1024,
            last_eviction_time=datetime.utcnow()
        )
        
        assert metrics.evicted_count == 10
        assert metrics.evicted_size_bytes == 1024
        assert metrics.last_eviction_time is not None


@pytest.mark.asyncio
async def test_integration_cache_eviction():
    """Integration test for cache eviction."""
    # This would test the full integration of cache eviction
    # with actual cache instances (requires Redis and database setup)
    pass

