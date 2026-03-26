import json
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
import asyncio
from contextlib import asynccontextmanager

from src.core.redis import get_redis_client
import redis.asyncio as aioredis
from src.utils.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)

class CacheLayer:
    """Base class for cache layers"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client()
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache"""
        raise NotImplementedError
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in cache"""
        raise NotImplementedError
    
    async def delete(self, key: str) -> bool:
        """Delete value from cache"""
        raise NotImplementedError
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        raise NotImplementedError

class DBQueryCache(CacheLayer):
    """Layer 1: DB Query Cache for standard key-value data"""
    
    def __init__(self, redis_client=None):
        super().__init__(redis_client)
        self.prefix = "db_query"
    
    def _get_tenant_key(self, key: str) -> str:
        """Get tenant-prefixed key"""
        tenant_id = get_tenant_context()
        return f"{tenant_id}:{self.prefix}:{key}"
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from DB query cache"""
        try:
            tenant_key = self._get_tenant_key(key)
            value = await self.redis_client.get(tenant_key)
            if value is None:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.error(f"Error getting DB query cache {key}: {e}")
            return default
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in DB query cache"""
        try:
            tenant_key = self._get_tenant_key(key)
            json_value = json.dumps(value) if not isinstance(value, str) else value
            return await self.redis_client.set(tenant_key, json_value, ex=expire)
        except Exception as e:
            logger.error(f"Error setting DB query cache {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from DB query cache"""
        try:
            tenant_key = self._get_tenant_key(key)
            return await self.redis_client.delete(tenant_key) > 0
        except Exception as e:
            logger.error(f"Error deleting DB query cache {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in DB query cache"""
        try:
            tenant_key = self._get_tenant_key(key)
            return await self.redis_client.exists(tenant_key) > 0
        except Exception as e:
            logger.error(f"Error checking DB query cache {key}: {e}")
            return False

class AgentResponseCache(CacheLayer):
    """Layer 2: Agent/Tool Response Cache for expensive operations"""
    
    def __init__(self, redis_client=None):
        super().__init__(redis_client)
        self.prefix = "agent_response"
    
    def _get_tenant_key(self, key: str) -> str:
        """Get tenant-prefixed key"""
        tenant_id = get_tenant_context()
        return f"{tenant_id}:{self.prefix}:{key}"
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from agent response cache"""
        try:
            tenant_key = self._get_tenant_key(key)
            value = await self.redis_client.get(tenant_key)
            if value is None:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.error(f"Error getting agent response cache {key}: {e}")
            return default
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in agent response cache"""
        try:
            tenant_key = self._get_tenant_key(key)
            json_value = json.dumps(value) if not isinstance(value, str) else value
            # Default expiration for agent responses: 1 hour
            if expire is None:
                expire = 3600
            return await self.redis_client.set(tenant_key, json_value, ex=expire)
        except Exception as e:
            logger.error(f"Error setting agent response cache {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from agent response cache"""
        try:
            tenant_key = self._get_tenant_key(key)
            return await self.redis_client.delete(tenant_key) > 0
        except Exception as e:
            logger.error(f"Error deleting agent response cache {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in agent response cache"""
        try:
            tenant_key = self._get_tenant_key(key)
            return await self.redis_client.exists(tenant_key) > 0
        except Exception as e:
            logger.error(f"Error checking agent response cache {key}: {e}")
            return False

class SemanticCache(CacheLayer):
    """Layer 3: Semantic Cache using Redis Search Module"""
    
    def __init__(self, redis_client=None):
        super().__init__(redis_client)
        self.prefix = "semantic"
        self.index_name = "semantic_idx"
        self.enabled = True
        self._feature_checked = False
        # Ensure index exists (best-effort, async)
        try:
            asyncio.get_event_loop().create_task(self._ensure_index_exists())
        except Exception:
            pass
    
    def _get_tenant_key(self, key: str) -> str:
        """Get tenant-prefixed key"""
        tenant_id = get_tenant_context()
        return f"{tenant_id}:{self.prefix}:{key}"
    
    async def _ensure_index_exists(self):
        """Ensure Redis Search index exists with vector JSON schema."""
        if self._feature_checked:
            return
        self._feature_checked = True
        try:
            info = await self.redis_client.execute_command("INFO", "MODULES")
            if "search" not in str(info).lower():
                self.enabled = False
                return
        except Exception:
            self.enabled = False
            return
        try:
            await self.redis_client.ft(self.index_name).info()
            return
        except Exception:
            pass
        try:
            # Create index ON JSON with HNSW vector field 'vector'
            await self.redis_client.execute_command(
                "FT.CREATE",
                self.index_name,
                "ON",
                "JSON",
                "PREFIX",
                "1",
                "tenant:",
                "SCHEMA",
                "$.vector",
                "AS",
                "vector",
                "VECTOR",
                "HNSW",
                "6",
                "TYPE",
                "FLOAT32",
                "DIM",
                "768",
                "DISTANCE_METRIC",
                "COSINE",
                "$.content",
                "AS",
                "content",
                "TEXT",
                "$.tenant_id",
                "AS",
                "tenant_id",
                "TAG",
                "$.key",
                "AS",
                "key",
                "TAG",
                "$.timestamp",
                "AS",
                "timestamp",
                "NUMERIC",
            )
        except Exception as e:
            self.enabled = False
            logger.warning(f"FT.CREATE semantic index skipped/failed: {e}")
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from semantic cache using vector similarity"""
        try:
            if not getattr(self, "enabled", False):
                return default
            # For semantic cache, we'll use vector similarity search
            # This is a simplified implementation - in production, you'd use actual vector embeddings
            tenant_id = get_tenant_context()
            query = f"*=>[KNN 1 @vector $query_vector]"
            params = {"query_vector": [0.1] * 8}  # Placeholder vector
            
            results = await self.redis_client.ft(self.index_name).search(query, params)
            
            if results.total > 0:
                # Return the most similar result
                return results.docs[0].content
            return default
        except Exception as e:
            logger.error(f"Error getting semantic cache {key}: {e}")
            return default
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in semantic cache"""
        try:
            if not getattr(self, "enabled", False):
                return False
            tenant_id = get_tenant_context()
            tenant_key = self._get_tenant_key(key)
            
            # Store the content and metadata
            document = {
                "vector": [0.1] * 8,  # Placeholder vector - in production, use actual embeddings
                "content": json.dumps(value) if not isinstance(value, str) else value,
                "tenant_id": tenant_id,
                "key": key,
                "timestamp": int(datetime.utcnow().timestamp())
            }
            
            # Use Redis JSON for storing complex data
            await self.redis_client.json().set(tenant_key, "$", document)
            
            if expire:
                await self.redis_client.expire(tenant_key, expire)
            
            return True
        except Exception as e:
            logger.error(f"Error setting semantic cache {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from semantic cache"""
        try:
            if not getattr(self, "enabled", False):
                return False
            tenant_key = self._get_tenant_key(key)
            result = await self.redis_client.delete(tenant_key)
            return result > 0
        except Exception as e:
            logger.error(f"Error deleting semantic cache {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in semantic cache"""
        try:
            if not getattr(self, "enabled", False):
                return False
            tenant_key = self._get_tenant_key(key)
            return await self.redis_client.exists(tenant_key) > 0
        except Exception as e:
            logger.error(f"Error checking semantic cache {key}: {e}")
            return False

class CacheManager:
    """Unified cache manager for all cache layers"""
    
    def __init__(self, redis_client=None):
        self.db_cache = DBQueryCache(redis_client)
        self.agent_cache = AgentResponseCache(redis_client)
        self.semantic_cache = SemanticCache(redis_client)
    
    async def get_db_query(self, key: str, default: Any = None) -> Any:
        """Get from DB query cache"""
        return await self.db_cache.get(key, default)
    
    async def set_db_query(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set in DB query cache"""
        return await self.db_cache.set(key, value, expire)
    
    async def get_agent_response(self, key: str, default: Any = None) -> Any:
        """Get from agent response cache"""
        return await self.agent_cache.get(key, default)
    
    async def set_agent_response(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set in agent response cache"""
        return await self.agent_cache.set(key, value, expire)
    
    async def get_semantic(self, key: str, default: Any = None) -> Any:
        """Get from semantic cache"""
        return await self.semantic_cache.get(key, default)
    
    async def set_semantic(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set in semantic cache"""
        return await self.semantic_cache.set(key, value, expire)
    
    async def invalidate(self, cache_type: str, key: str) -> bool:
        """Invalidate a specific cache entry"""
        try:
            if cache_type == "db_query":
                return await self.db_cache.delete(key)
            elif cache_type == "agent_response":
                return await self.agent_cache.delete(key)
            elif cache_type == "semantic":
                return await self.semantic_cache.delete(key)
            else:
                logger.warning(f"Unknown cache type: {cache_type}")
                return False
        except Exception as e:
            logger.error(f"Error invalidating cache {cache_type}:{key}: {e}")
            return False
    
    async def invalidate_tenant_all(self) -> bool:
        """Invalidate all cache for current tenant"""
        try:
            tenant_id = get_tenant_context()
            pattern = f"{tenant_id}:*"
            
            # Scan and delete all keys for this tenant
            keys = []
            async for key in self.db_cache.redis_client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                await self.db_cache.redis_client.delete(*keys)
            
            return True
        except Exception as e:
            logger.error(f"Error invalidating tenant cache: {e}")
            return False

# Global cache manager instance
_cache_manager: Optional[CacheManager] = None

def get_cache_manager() -> CacheManager:
    """Get global cache manager instance, rebinding to current Redis client if it changed.

    This allows E2E tests to inject a DummyRedisClient via monkeypatch and have the
    cache manager pick it up even if the singleton was created earlier.
    """
    global _cache_manager
    try:
        current_client = get_redis_client()
    except Exception:
        current_client = None

    if _cache_manager is None:
        _cache_manager = CacheManager(current_client)
        return _cache_manager

    # If the bound client differs from the current client reference, rebind
    try:
        bound_client = _cache_manager.db_cache.redis_client
        if (current_client is not None) and (bound_client is not current_client):
            _cache_manager = CacheManager(current_client)
    except Exception:
        # If anything goes wrong determining the client identity, rebuild once
        _cache_manager = CacheManager(current_client)
    return _cache_manager
