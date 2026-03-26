import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.core.caching import get_cache_manager, CacheManager
from src.utils.cache_invalidator import get_cache_invalidator, CacheInvalidator
from src.utils.redis_client import get_redis_client, RedisClient
from src.tasks.cache_cleanup import get_cleanup_task, CacheCleanupTask

class TestCachingSystem:
    """Test suite for the caching system"""
    
    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client"""
        with patch('src.core.redis.get_redis_client') as mock:
            client = AsyncMock()
            client.get = AsyncMock(return_value='{"test": "value"}')
            client.set = AsyncMock(return_value=True)
            client.delete = AsyncMock(return_value=1)
            client.exists = AsyncMock(return_value=1)
            mock.return_value = client
            yield client
    
    @pytest.fixture
    def mock_tenant_context(self):
        """Mock tenant context"""
        with patch('src.utils.tenant_context.get_current_tenant_id') as mock:
            mock.return_value = 'test-tenant-123'
            yield mock
    
    def test_cache_manager_initialization(self):
        """Test cache manager initialization"""
        cache_manager = get_cache_manager()
        assert isinstance(cache_manager, CacheManager)
        assert cache_manager.db_cache is not None
        assert cache_manager.agent_cache is not None
        assert cache_manager.semantic_cache is not None
    
    @pytest.mark.asyncio
    async def test_db_cache_operations(self, mock_redis_client, mock_tenant_context):
        """Test DB cache operations"""
        cache_manager = get_cache_manager()
        
        # Test set
        result = await cache_manager.set_db_query('test_key', {'data': 'value'})
        assert result is True
        mock_redis_client.set.assert_called_once()
        
        # Test get
        result = await cache_manager.get_db_query('test_key')
        assert result == {'data': 'value'}
        mock_redis_client.get.assert_called_once()
        
        # Test delete
        result = await cache_manager.db_cache.delete('test_key')
        assert result is True
        mock_redis_client.delete.assert_called_once()
        
        # Test exists
        result = await cache_manager.db_cache.exists('test_key')
        assert result is True
        mock_redis_client.exists.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_agent_cache_operations(self, mock_redis_client, mock_tenant_context):
        """Test agent response cache operations"""
        cache_manager = get_cache_manager()
        
        # Test set with default expiration
        result = await cache_manager.set_agent_response('agent_key', {'response': 'data'})
        assert result is True
        mock_redis_client.set.assert_called_once()
        
        # Test get
        result = await cache_manager.get_agent_response('agent_key')
        assert result == {'response': 'data'}
        mock_redis_client.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self, mock_redis_client, mock_tenant_context):
        """Test cache invalidation"""
        invalidator = get_cache_invalidator()
        
        # Test invalidation
        result = await invalidator.invalidate('db_query', 'test_key')
        assert result is True
        mock_redis_client.delete.assert_called_once()
        
        # Test project invalidation
        result = await invalidator.invalidate_project('project-123')
        assert result is True
        # Should have called delete multiple times
        assert mock_redis_client.delete.call_count > 1
    
    @pytest.mark.asyncio
    async def test_tenant_cache_invalidation(self, mock_redis_client, mock_tenant_context):
        """Test tenant-wide cache invalidation"""
        invalidator = get_cache_invalidator()
        
        # Mock scan to return some keys
        mock_redis_client.scan_iter = AsyncMock()
        mock_redis_client.scan_iter.return_value = ['test-tenant-123:key1', 'test-tenant-123:key2']
        
        result = await invalidator.invalidate_tenant_all()
        assert result is True
        # Should have deleted keys
        assert mock_redis_client.delete.call_count > 0
    
    def test_redis_client_initialization(self):
        """Test Redis client initialization"""
        redis_client = get_redis_client()
        assert isinstance(redis_client, RedisClient)
        assert redis_client.redis_client is not None
    
    @pytest.mark.asyncio
    async def test_redis_client_tenant_isolation(self, mock_redis_client, mock_tenant_context):
        """Test Redis client tenant isolation"""
        redis_client = get_redis_client()
        
        # Test set with tenant prefix
        result = await redis_client.set('test_key', {'data': 'value'})
        assert result is True
        # Should have been called with tenant-prefixed key
        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args[0]
        assert call_args[0].startswith('test-tenant-123:')
        
        # Test get with tenant prefix
        result = await redis_client.get('test_key')
        assert result == {'data': 'value'}
        mock_redis_client.get.assert_called_once()
        
        # Test delete with tenant prefix
        result = await redis_client.delete('test_key')
        assert result is True
        mock_redis_client.delete.assert_called_once()
        
        # Test exists with tenant prefix
        result = await redis_client.exists('test_key')
        assert result is True
        mock_redis_client.exists.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_redis_client_hash_operations(self, mock_redis_client, mock_tenant_context):
        """Test Redis client hash operations"""
        redis_client = get_redis_client()
        
        # Test hset
        result = await redis_client.hset('hash_key', 'field1', {'data': 'value'})
        assert result is True
        mock_redis_client.hset.assert_called_once()
        
        # Test hget
        result = await redis_client.hget('hash_key', 'field1')
        assert result == {'data': 'value'}
        mock_redis_client.hget.assert_called_once()
        
        # Test hdel
        result = await redis_client.hdel('hash_key', 'field1')
        assert result is True
        mock_redis_client.hdel.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_redis_client_list_operations(self, mock_redis_client, mock_tenant_context):
        """Test Redis client list operations"""
        redis_client = get_redis_client()
        
        # Test lpush
        result = await redis_client.lpush('list_key', 'item1', 'item2')
        assert result == 2
        mock_redis_client.lpush.assert_called_once()
        
        # Test rpop
        result = await redis_client.rpop('list_key')
        assert result == 'item2'
        mock_redis_client.rpop.assert_called_once()
        
        # Test llen
        result = await redis_client.llen('list_key')
        assert result == 1
        mock_redis_client.llen.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_redis_client_counter_operations(self, mock_redis_client, mock_tenant_context):
        """Test Redis client counter operations"""
        redis_client = get_redis_client()
        
        # Test incr
        result = await redis_client.incr('counter_key', 5)
        assert result == 5
        mock_redis_client.incrby.assert_called_once_with('test-tenant-123:counter_key', 5)
        
        # Test decr
        result = await redis_client.decr('counter_key', 3)
        assert result == 2
        mock_redis_client.decrby.assert_called_once_with('test-tenant-123:counter_key', 3)
    
    @pytest.mark.asyncio
    async def test_redis_client_expiration_operations(self, mock_redis_client, mock_tenant_context):
        """Test Redis client expiration operations"""
        redis_client = get_redis_client()
        
        # Test expire
        result = await redis_client.expire('temp_key', 3600)
        assert result is True
        mock_redis_client.expire.assert_called_once()
        
        # Test ttl
        result = await redis_client.ttl('temp_key')
        assert result == 3600
        mock_redis_client.ttl.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_redis_client_scan_operation(self, mock_redis_client, mock_tenant_context):
        """Test Redis client scan operation"""
        redis_client = get_redis_client()
        
        # Mock scan to return some keys
        mock_redis_client.scan_iter = AsyncMock()
        mock_redis_client.scan_iter.return_value = [
            'test-tenant-123:key1',
            'test-tenant-123:key2',
            'test-tenant-123:key3'
        ]
        
        result = await redis_client.scan('key*', 5)
        assert result == ['key1', 'key2', 'key3']
        mock_redis_client.scan_iter.assert_called_once_with(
            match='test-tenant-123:key*',
            count=5
        )
    
    @pytest.mark.asyncio
    async def test_cache_cleanup_task_initialization(self):
        """Test cache cleanup task initialization"""
        cleanup_task = get_cleanup_task()
        assert isinstance(cleanup_task, CacheCleanupTask)
        assert cleanup_task.redis_client is not None
        assert cleanup_task.db is not None
    
    @pytest.mark.asyncio
    async def test_cache_cleanup_tenant_cache(self, mock_redis_client, mock_tenant_context):
        """Test tenant cache cleanup"""
        cleanup_task = get_cleanup_task()
        
        # Mock scan to return some keys
        mock_redis_client.scan_iter = AsyncMock()
        mock_redis_client.scan_iter.return_value = [
            'test-tenant-123:key1',
            'test-tenant-123:key2',
            'test-tenant-123:key3',
            'test-tenant-123:key4'
        ]
        
        # Mock object idletime
        mock_redis_client.object = AsyncMock(side_effect=lambda cmd, key: 100 if cmd == 'idletime' else None)
        
        # Mock memory usage
        mock_redis_client.memory_usage = AsyncMock(return_value=1024)
        
        # Mock delete
        mock_redis_client.delete = AsyncMock(return_value=1)
        
        result = await cleanup_task.cleanup_tenant_cache('test-tenant-123', 0.5)
        
        assert result['tenant_id'] == 'test-tenant-123'
        assert result['cleanup_percentage'] == 0.5
        assert result['total_keys_before'] == 4
        assert result['keys_removed'] == 2  # 50% of 4 keys
        assert result['total_bytes_freed'] > 0
        
        # Should have called delete twice (for 2 keys)
        assert mock_redis_client.delete.call_count == 2
    
    @pytest.mark.asyncio
    async def test_increment_tenant_active_seconds(self, mock_redis_client, mock_tenant_context):
        """Test increment tenant active seconds"""
        from src.tasks.cache_cleanup import increment_tenant_active_seconds
        
        result = await increment_tenant_active_seconds('test-tenant-123', 5)
        assert result is True
        mock_redis_client.incrby.assert_called_once_with('tenant_active_seconds:test-tenant-123', 5)
        mock_redis_client.expire.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_manager_semantic_cache(self, mock_redis_client, mock_tenant_context):
        """Test semantic cache operations"""
        cache_manager = get_cache_manager()
        
        # Mock Redis JSON operations
        mock_redis_client.json = AsyncMock()
        mock_redis_client.json.return_value.set = AsyncMock(return_value=True)
        mock_redis_client.ft = AsyncMock()
        mock_redis_client.ft.return_value.info = AsyncMock(side_effect=Exception("Index not found"))
        mock_redis_client.ft.return_value.schema = AsyncMock()
        mock_redis_client.ft.return_value.schema.return_value.create = AsyncMock(return_value=True)
        
        # Test set semantic cache
        result = await cache_manager.set_semantic('semantic_key', {'content': 'test data'})
        assert result is True
        
        # Test get semantic cache (will fail due to missing index, but should not crash)
        result = await cache_manager.get_semantic('semantic_key')
        assert result is None
    
    def test_cache_manager_singleton(self):
        """Test cache manager singleton pattern"""
        cache_manager1 = get_cache_manager()
        cache_manager2 = get_cache_manager()
        assert cache_manager1 is cache_manager2
    
    def test_cache_invalidator_singleton(self):
        """Test cache invalidator singleton pattern"""
        invalidator1 = get_cache_invalidator()
        invalidator2 = get_cache_invalidator()
        assert invalidator1 is invalidator2
    
    def test_redis_client_singleton(self):
        """Test Redis client singleton pattern"""
        redis_client1 = get_redis_client()
        redis_client2 = get_redis_client()
        assert redis_client1 is redis_client2
    
    def test_cleanup_task_singleton(self):
        """Test cleanup task singleton pattern"""
        cleanup_task1 = get_cleanup_task()
        cleanup_task2 = get_cleanup_task()
        assert cleanup_task1 is cleanup_task2
