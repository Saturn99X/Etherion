"""
Cache manager for global cache instance management.
"""

import os
import logging
from typing import Optional
from src.cache.cache_engine import ThreeLayerCache

logger = logging.getLogger(__name__)

# Global cache instance
_cache_instance: Optional[ThreeLayerCache] = None


async def initialize_cache() -> ThreeLayerCache:
    """Initialize the global cache instance."""
    global _cache_instance
    
    if _cache_instance is not None:
        return _cache_instance
    
    try:
        # Configuration from environment variables
        l1_size = int(os.getenv('CACHE_L1_SIZE', '1000'))
        l1_ttl = float(os.getenv('CACHE_L1_TTL', '3600'))
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        l2_ttl = float(os.getenv('CACHE_L2_TTL', '7200'))
        
        # Create cache instance
        _cache_instance = ThreeLayerCache(
            l1_size=l1_size,
            l1_ttl=l1_ttl,
            redis_url=redis_url,
            l2_ttl=l2_ttl
        )
        
        # Initialize cache
        await _cache_instance.initialize()
        
        logger.info("Global cache instance initialized successfully")
        return _cache_instance
        
    except Exception as e:
        logger.error(f"Failed to initialize global cache: {e}")
        raise


async def get_cache() -> ThreeLayerCache:
    """Get the global cache instance."""
    global _cache_instance
    
    if _cache_instance is None:
        return await initialize_cache()
    
    return _cache_instance


async def shutdown_cache() -> None:
    """Shutdown the global cache instance."""
    global _cache_instance
    
    if _cache_instance is not None:
        # Close Redis connections
        if hasattr(_cache_instance.l2_cache, '_pool') and _cache_instance.l2_cache._pool:
            await _cache_instance.l2_cache._pool.disconnect()
        
        _cache_instance = None
        logger.info("Global cache instance shutdown")


def get_cache_sync() -> Optional[ThreeLayerCache]:
    """Get the global cache instance synchronously (for non-async contexts)."""
    return _cache_instance
