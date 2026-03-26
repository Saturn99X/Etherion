"""
Three-layer caching system with intelligent eviction policies.
L1: In-memory LRU cache, L2: Redis cache, L3: Database cache
"""

import asyncio
import json
import logging
import time
import hashlib
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
# Use redis.asyncio for Python 3.13 compatibility
import redis.asyncio as aioredis
from functools import wraps
import threading
from collections import OrderedDict

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """Cache level enumeration."""
    L1_MEMORY = "l1_memory"
    L2_REDIS = "l2_redis"
    L3_DATABASE = "l3_database"


class EvictionPolicy(Enum):
    """Cache eviction policy enumeration."""
    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    TTL = "ttl"  # Time To Live
    SIZE = "size"  # Size-based eviction


@dataclass
class CacheEntry:
    """Cache entry data structure."""
    key: str
    value: Any
    created_at: float
    last_accessed: float
    access_count: int
    ttl: Optional[float] = None
    tenant_id: Optional[str] = None
    cache_level: CacheLevel = CacheLevel.L1_MEMORY
    
    def is_expired(self) -> bool:
        """Check if the cache entry is expired."""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'key': self.key,
            'value': self.value,
            'created_at': self.created_at,
            'last_accessed': self.last_accessed,
            'access_count': self.access_count,
            'ttl': self.ttl,
            'tenant_id': self.tenant_id,
            'cache_level': self.cache_level.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """Create from dictionary."""
        data['cache_level'] = CacheLevel(data['cache_level'])
        return cls(**data)


class L1MemoryCache:
    """L1: In-memory LRU cache with tenant isolation."""
    
    def __init__(self, max_size: int = 1000, default_ttl: float = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.RLock()
    
    def get(self, key: str, tenant_id: Optional[str] = None) -> Optional[Any]:
        """Get value from L1 cache."""
        with self._lock:
            full_key = self._make_key(key, tenant_id)
            entry = self._cache.get(full_key)
            
            if entry is None:
                return None
            
            if entry.is_expired():
                self._remove_entry(full_key)
                return None
            
            # Update access information
            entry.last_accessed = time.time()
            entry.access_count += 1
            self._access_order.move_to_end(full_key)
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None, 
            tenant_id: Optional[str] = None) -> None:
        """Set value in L1 cache."""
        with self._lock:
            full_key = self._make_key(key, tenant_id)
            ttl = ttl or self.default_ttl
            
            entry = CacheEntry(
                key=full_key,
                value=value,
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=1,
                ttl=ttl,
                tenant_id=tenant_id,
                cache_level=CacheLevel.L1_MEMORY
            )
            
            self._cache[full_key] = entry
            self._access_order[full_key] = None
            
            # Evict if necessary
            if len(self._cache) > self.max_size:
                self._evict_lru()
    
    def delete(self, key: str, tenant_id: Optional[str] = None) -> bool:
        """Delete value from L1 cache."""
        with self._lock:
            full_key = self._make_key(key, tenant_id)
            return self._remove_entry(full_key)
    
    def clear_tenant(self, tenant_id: str) -> int:
        """Clear all cache entries for a specific tenant."""
        with self._lock:
            keys_to_remove = [
                key for key in self._cache.keys()
                if key.startswith(f"{tenant_id}:")
            ]
            
            for key in keys_to_remove:
                self._remove_entry(key)
            
            return len(keys_to_remove)
    
    def _make_key(self, key: str, tenant_id: Optional[str] = None) -> str:
        """Make tenant-aware cache key."""
        if tenant_id:
            return f"{tenant_id}:{key}"
        return key
    
    def _remove_entry(self, full_key: str) -> bool:
        """Remove entry from cache and access order."""
        if full_key in self._cache:
            del self._cache[full_key]
            if full_key in self._access_order:
                del self._access_order[full_key]
            return True
        return False
    
    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if self._access_order:
            oldest_key = next(iter(self._access_order))
            self._remove_entry(oldest_key)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hit_rate': self._calculate_hit_rate(),
                'memory_usage': self._estimate_memory_usage()
            }
    
    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total_accesses = sum(entry.access_count for entry in self._cache.values())
        if total_accesses == 0:
            return 0.0
        return sum(entry.access_count for entry in self._cache.values()) / total_accesses
    
    def _estimate_memory_usage(self) -> int:
        """Estimate memory usage in bytes."""
        return sum(len(str(entry.value)) for entry in self._cache.values())


class L2RedisCache:
    """L2: Redis cache with tenant isolation and clustering support."""
    
    def __init__(self, redis_url: str, max_connections: int = 10, default_ttl: float = 7200):
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.default_ttl = default_ttl
        self._pool: Optional[aioredis.ConnectionPool] = None
        self._redis: Optional[aioredis.Redis] = None
    
    async def initialize(self) -> None:
        """Initialize Redis connection pool."""
        try:
            self._pool = aioredis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                retry_on_timeout=True
            )
            self._redis = aioredis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._redis.ping()
            logger.info("L2 Redis cache initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize L2 Redis cache: {e}")
            raise
    
    async def get(self, key: str, tenant_id: Optional[str] = None) -> Optional[Any]:
        """Get value from L2 cache."""
        if not self._redis:
            return None
        
        try:
            full_key = self._make_key(key, tenant_id)
            value = await self._redis.get(full_key)
            
            if value is None:
                return None
            
            # Update access time
            await self._redis.hset(f"{full_key}:meta", "last_accessed", time.time())
            await self._redis.hincrby(f"{full_key}:meta", "access_count", 1)
            
            return json.loads(value)
            
        except Exception as e:
            logger.error(f"Error getting from L2 cache: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[float] = None,
                  tenant_id: Optional[str] = None) -> None:
        """Set value in L2 cache."""
        if not self._redis:
            return
        
        try:
            full_key = self._make_key(key, tenant_id)
            ttl = ttl or self.default_ttl
            
            # Store value
            await self._redis.setex(full_key, int(ttl), json.dumps(value))
            
            # Store metadata
            metadata = {
                "created_at": time.time(),
                "last_accessed": time.time(),
                "access_count": 1,
                "tenant_id": tenant_id or "",
                "cache_level": CacheLevel.L2_REDIS.value
            }
            await self._redis.hset(f"{full_key}:meta", mapping=metadata)
            await self._redis.expire(f"{full_key}:meta", int(ttl))
            
        except Exception as e:
            logger.error(f"Error setting L2 cache: {e}")
    
    async def delete(self, key: str, tenant_id: Optional[str] = None) -> bool:
        """Delete value from L2 cache."""
        if not self._redis:
            return False
        
        try:
            full_key = self._make_key(key, tenant_id)
            result = await self._redis.delete(full_key, f"{full_key}:meta")
            return result > 0
            
        except Exception as e:
            logger.error(f"Error deleting from L2 cache: {e}")
            return False
    
    async def clear_tenant(self, tenant_id: str) -> int:
        """Clear all cache entries for a specific tenant."""
        if not self._redis:
            return 0
        
        try:
            pattern = f"{tenant_id}:*"
            keys = await self._redis.keys(pattern)
            
            if keys:
                await self._redis.delete(*keys)
            
            return len(keys)
            
        except Exception as e:
            logger.error(f"Error clearing tenant cache: {e}")
            return 0
    
    def _make_key(self, key: str, tenant_id: Optional[str] = None) -> str:
        """Make tenant-aware cache key."""
        if tenant_id:
            return f"cache:{tenant_id}:{key}"
        return f"cache:{key}"
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        if not self._redis:
            return {}
        
        try:
            info = await self._redis.info()
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'hit_rate': self._calculate_hit_rate(info)
            }
        except Exception as e:
            logger.error(f"Error getting Redis stats: {e}")
            return {}
    
    def _calculate_hit_rate(self, info: Dict[str, Any]) -> float:
        """Calculate Redis hit rate."""
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)
        total = hits + misses
        return hits / total if total > 0 else 0.0


class L3DatabaseCache:
    """L3: Database cache for persistent storage."""
    
    def __init__(self, db_session_factory: Callable):
        self.db_session_factory = db_session_factory
    
    async def get(self, key: str, tenant_id: Optional[str] = None) -> Optional[Any]:
        """Get value from L3 database cache."""
        # This would integrate with your existing database models
        # For now, return None as placeholder
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[float] = None,
                  tenant_id: Optional[str] = None) -> None:
        """Set value in L3 database cache."""
        # This would integrate with your existing database models
        # For now, do nothing as placeholder
        pass
    
    async def delete(self, key: str, tenant_id: Optional[str] = None) -> bool:
        """Delete value from L3 database cache."""
        # This would integrate with your existing database models
        # For now, return False as placeholder
        return False


class ThreeLayerCache:
    """Main three-layer cache system with intelligent eviction."""
    
    def __init__(self, l1_size: int = 1000, l1_ttl: float = 3600,
                 redis_url: str = "redis://localhost:6379", l2_ttl: float = 7200,
                 db_session_factory: Optional[Callable] = None):
        
        self.l1_cache = L1MemoryCache(max_size=l1_size, default_ttl=l1_ttl)
        self.l2_cache = L2RedisCache(redis_url=redis_url, default_ttl=l2_ttl)
        self.l3_cache = L3DatabaseCache(db_session_factory) if db_session_factory else None
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all cache layers."""
        try:
            await self.l2_cache.initialize()
            self._initialized = True
            logger.info("Three-layer cache system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize cache system: {e}")
            raise
    
    async def get(self, key: str, tenant_id: Optional[str] = None) -> Optional[Any]:
        """Get value from cache with fallback through layers."""
        # L1: Memory cache
        value = self.l1_cache.get(key, tenant_id)
        if value is not None:
            return value
        
        # L2: Redis cache
        if self._initialized:
            value = await self.l2_cache.get(key, tenant_id)
            if value is not None:
                # Promote to L1
                self.l1_cache.set(key, value, tenant_id=tenant_id)
                return value
        
        # L3: Database cache
        if self.l3_cache:
            value = await self.l3_cache.get(key, tenant_id)
            if value is not None:
                # Promote to L1 and L2
                self.l1_cache.set(key, value, tenant_id=tenant_id)
                if self._initialized:
                    await self.l2_cache.set(key, value, tenant_id=tenant_id)
                return value
        
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[float] = None,
                  tenant_id: Optional[str] = None, levels: List[CacheLevel] = None) -> None:
        """Set value in specified cache levels."""
        if levels is None:
            levels = [CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS, CacheLevel.L3_DATABASE]
        
        # L1: Memory cache
        if CacheLevel.L1_MEMORY in levels:
            self.l1_cache.set(key, value, ttl, tenant_id)
        
        # L2: Redis cache
        if CacheLevel.L2_REDIS in levels and self._initialized:
            await self.l2_cache.set(key, value, ttl, tenant_id)
        
        # L3: Database cache
        if CacheLevel.L3_DATABASE in levels and self.l3_cache:
            await self.l3_cache.set(key, value, ttl, tenant_id)
    
    async def delete(self, key: str, tenant_id: Optional[str] = None,
                     levels: List[CacheLevel] = None) -> bool:
        """Delete value from specified cache levels."""
        if levels is None:
            levels = [CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS, CacheLevel.L3_DATABASE]
        
        deleted = False
        
        # L1: Memory cache
        if CacheLevel.L1_MEMORY in levels:
            deleted |= self.l1_cache.delete(key, tenant_id)
        
        # L2: Redis cache
        if CacheLevel.L2_REDIS in levels and self._initialized:
            deleted |= await self.l2_cache.delete(key, tenant_id)
        
        # L3: Database cache
        if CacheLevel.L3_DATABASE in levels and self.l3_cache:
            deleted |= await self.l3_cache.delete(key, tenant_id)
        
        return deleted
    
    async def clear_tenant(self, tenant_id: str) -> Dict[str, int]:
        """Clear all cache entries for a specific tenant."""
        cleared = {"l1": 0, "l2": 0, "l3": 0, "total_evicted": 0}
        
        # Clear L1 cache
        with self.l1_cache._lock:
            tenant_keys = [key for key, entry in self.l1_cache._cache.items() 
                          if entry.tenant_id == tenant_id]
            for key in tenant_keys:
                if self.l1_cache.delete(key):
                    cleared["l1"] += 1
        
        # Clear L2 cache
        if self._initialized:
            # This would need Redis pattern matching implementation
            # For now, we'll clear by iterating through keys
            try:
                pattern = f"*:tenant:{tenant_id}:*"
                keys = await self.l2_cache.redis_client.keys(pattern)
                if keys:
                    await self.l2_cache.redis_client.delete(*keys)
                    cleared["l2"] = len(keys)
            except Exception as e:
                logger.warning(f"Failed to clear L2 cache for tenant {tenant_id}: {e}")
        
        # Clear L3 cache
        if self.l3_cache:
            # This would need database implementation
            cleared["l3"] = 0
        
        cleared["total_evicted"] = cleared["l1"] + cleared["l2"] + cleared["l3"]
        return cleared
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        stats = {
            'l1': self.l1_cache.get_stats(),
            'l2': await self.l2_cache.get_stats() if self._initialized else {},
            'l3': {}  # Would be implemented based on DB schema
        }
        
        return stats


def cache_key(*args, **kwargs) -> str:
    """Generate cache key from arguments."""
    key_data = {
        'args': args,
        'kwargs': sorted(kwargs.items())
    }
    key_string = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_string.encode()).hexdigest()


def cached(ttl: Optional[float] = None, tenant_aware: bool = True,
           levels: List[CacheLevel] = None, cache_instance: Optional[ThreeLayerCache] = None):
    """Decorator for caching function results."""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if cache_instance is None:
                # Use global cache instance
                from src.cache.cache_manager import get_cache
                cache = await get_cache()
            else:
                cache = cache_instance
            
            # Extract tenant_id if tenant_aware
            tenant_id = None
            if tenant_aware and 'tenant_id' in kwargs:
                tenant_id = kwargs['tenant_id']
            
            # Generate cache key
            key = cache_key(func.__name__, *args, **kwargs)
            
            # Try to get from cache
            result = await cache.get(key, tenant_id)
            if result is not None:
                return result
            
            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Store in cache
            await cache.set(key, result, ttl, tenant_id, levels)
            
            return result
        
        return wrapper
    return decorator
