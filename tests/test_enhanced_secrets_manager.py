import pytest
import time
import threading
from src.utils.secrets_manager import TenantSecretsManager, SecretCacheEntry
from src.utils.secure_string import SecureString


def test_secrets_manager_initialization():
    """Test that TenantSecretsManager initializes correctly."""
    manager = TenantSecretsManager()
    assert manager is not None
    assert hasattr(manager, '_cache')
    assert hasattr(manager, '_lock')


def test_secure_string_in_cache_entry():
    """Test that SecretCacheEntry uses SecureString."""
    secure_str = SecureString("test_secret")
    entry = SecretCacheEntry(
        value=secure_str,
        expires_at=time.time() + 300
    )
    assert isinstance(entry.value, SecureString)
    assert entry.value.get_value() == "test_secret"


def test_cache_statistics():
    """Test cache statistics tracking."""
    manager = TenantSecretsManager()
    
    # Get initial stats
    stats = manager.get_cache_statistics()
    assert 'hits' in stats
    assert 'misses' in stats
    assert 'evictions' in stats
    assert 'errors' in stats


def test_lru_eviction():
    """Test LRU cache eviction."""
    # Create manager with small cache size
    manager = TenantSecretsManager()
    manager._max_cache_size = 2
    
    # Add entries
    manager._set_cached_secret("key1", "value1")
    manager._set_cached_secret("key2", "value2")
    manager._set_cached_secret("key3", "value3")  # This should evict key1
    
    # Check that key1 was evicted
    assert "key1" not in manager._cache
    assert "key2" in manager._cache
    assert "key3" in manager._cache


def test_cache_expiration():
    """Test cache expiration."""
    manager = TenantSecretsManager()
    manager._cache_ttl = 0.1  # 100ms for testing
    
    # Add entry
    manager._set_cached_secret("test_key", "test_value")
    assert "test_key" in manager._cache
    
    # Wait for expiration
    time.sleep(0.2)
    
    # Check that entry is still in cache but expired
    entry = manager._cache["test_key"]
    assert not manager._is_cache_valid(entry)
    
    # Try to get the expired entry
    result = manager._get_cached_secret("test_key")
    assert result is None
    assert "test_key" not in manager._cache


def test_thread_safety():
    """Test thread-safe access to cache."""
    manager = TenantSecretsManager()
    
    def add_entry(key, value):
        manager._set_cached_secret(key, value)
    
    def get_entry(key):
        return manager._get_cached_secret(key)
    
    # Create multiple threads
    threads = []
    for i in range(10):
        t = threading.Thread(target=add_entry, args=(f"key{i}", f"value{i}"))
        threads.append(t)
        t.start()
    
    # Wait for all threads to complete
    for t in threads:
        t.join()
    
    # Verify all entries were added
    for i in range(10):
        assert f"key{i}" in manager._cache
        assert manager._get_cached_secret(f"key{i}") == f"value{i}"


def test_concurrent_access():
    """Test concurrent access to the same cache entry."""
    manager = TenantSecretsManager()
    manager._set_cached_secret("shared_key", "shared_value")
    
    results = []
    
    def access_cache():
        result = manager._get_cached_secret("shared_key")
        results.append(result)
    
    # Create multiple threads accessing the same key
    threads = []
    for i in range(5):
        t = threading.Thread(target=access_cache)
        threads.append(t)
        t.start()
    
    # Wait for all threads to complete
    for t in threads:
        t.join()
    
    # Verify all threads got the same result
    assert len(results) == 5
    for result in results:
        assert result == "shared_value"


if __name__ == "__main__":
    pytest.main([__file__])