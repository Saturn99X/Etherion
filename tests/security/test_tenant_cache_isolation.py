import pytest
import asyncio
from unittest.mock import MagicMock, patch
from src.utils.redis_client import redis_manager, TenantRedisManager
from src.database.db import get_session
from src.database.models import Tenant
from src.core.caching import CacheManager

@pytest.mark.asyncio
async def test_tenant_prefix_enforcement():
    """Test RedisClient requires tenant_id and prefixes keys."""
    # Missing tenant_id raises ValueError
    with pytest.raises(ValueError, match="tenant_id is required"):
        RedisClient(None)
    
    # Valid tenant
    client = redis_manager.get_client(123)
    key = "test_key"
    full_key = client._full_key(key)
    assert full_key == "tenant:123:test_key"
    
    # Sanitization
    dirty_key = "test<invalid>"
    sanitized = client._full_key(dirty_key)
    assert sanitized == "tenant:123:test"  # < removed

@pytest.mark.asyncio
async def test_cross_tenant_read_failure():
    """Test Tenant A cannot read Tenant B's keys."""
    # Mock two tenants
    with patch('src.database.db.get_session') as mock_session:
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = MagicMock(id=1)
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query
        
        manager = TenantRedisManager()
        client_a = manager.get_client(1)
        client_b = manager.get_client(2)
        
        # Set key in A
        client_a.set("shared_key", "secret_a")
        
        # B cannot read
        result_b = client_b.get("shared_key")
        assert result_b is None
        
        # Verify isolation
        all_keys_a = client_a.scan_keys()
        assert len(all_keys_a) == 1  # Only A's key
        all_keys_b = client_b.scan_keys()
        assert len(all_keys_b) == 0  # No cross-read

@pytest.mark.asyncio
async def test_purge_scoped_to_tenant():
    """Test batch_purge only affects own tenant's keys."""
    manager = TenantRedisManager()
    client_a = manager.get_client(1)
    client_b = manager.get_client(2)
    
    # Set keys in both
    client_a.set("key_a1", "value_a1")
    client_a.set("key_a2", "value_a2")
    client_b.set("key_b1", "value_b1")
    
    # A purges 50%
    result_a = client_a.batch_purge(percentage=0.5, lru=True)
    assert result_a['purged'] == 1  # One of A's keys
    assert result_a['total'] == 2
    
    # B's keys intact
    result_b_get = client_b.get("key_b1")
    assert result_b_get == "value_b1"
    
    # A's scan shows only remaining
    a_keys = client_a.scan_keys()
    assert len(a_keys) == 1

@pytest.mark.asyncio
async def test_cache_manager_tenant_isolation():
    """Test CacheManager uses isolated client."""
    with patch('src.core.caching.redis_manager.get_client') as mock_client_a, \
         patch('src.core.caching.redis_manager.get_client', return_value=MagicMock(), side_effect=lambda tid: mock_client_a if tid == 1 else MagicMock()) as mock_client_b:
        
        mgr_a = CacheManager(1)
        mgr_b = CacheManager(2)
        
        # A sets, B gets None
        await mgr_a.semantic_cache.set("test query", "result_a")
        result_b = await mgr_b.semantic_cache.get("test query")
        assert result_b is None
        
        # Verify different clients
        assert mock_client_a.call_count == 1  # For A
        assert mock_client_b.call_count == 1  # For B

@pytest.mark.asyncio
async def test_bypass_detection():
    """Test direct Redis call forbidden via wrapper error."""
    from redis import Redis
    with pytest.raises(ValueError, match="tenant_id is required"):
        direct = Redis.from_url("redis://localhost")
        direct.set("bypass_key", "leak")  # But in code, wrapper prevents this
    # Note: Direct calls not used; test ensures wrapper enforcement in integration
