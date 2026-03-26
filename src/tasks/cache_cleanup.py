import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from src.core.redis import get_redis_client
from src.utils.tenant_context import get_current_tenant_id
from src.database.db import get_db
from src.database.models import Tenant

logger = logging.getLogger(__name__)

class CacheCleanupTask:
    """Task for cleaning up tenant cache based on time-on-task expiration"""
    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.db = get_db()
    
    async def cleanup_tenant_cache(self, tenant_id: str, cleanup_percentage: float = 0.25) -> Dict[str, Any]:
        """
        Clean up cache for a specific tenant by removing the oldest entries
        
        Args:
            tenant_id: Tenant identifier
            cleanup_percentage: Percentage of keys to remove (0.0 to 1.0)
            
        Returns:
            Dict with cleanup statistics
        """
        try:
            stats = {
                "tenant_id": tenant_id,
                "cleanup_percentage": cleanup_percentage,
                "total_keys_before": 0,
                "keys_removed": 0,
                "total_bytes_freed": 0,
                "execution_time_ms": 0
            }
            
            start_time = datetime.utcnow()
            
            # Get all keys for this tenant
            pattern = f"{tenant_id}:*"
            keys = []
            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)
            
            stats["total_keys_before"] = len(keys)
            
            if not keys:
                logger.info(f"No cache keys found for tenant {tenant_id}")
                return stats
            
            # Get idle times for all keys
            key_idle_times = []
            for key in keys:
                try:
                    idle_time = await self.redis_client.object("idletime", key)
                    if idle_time is not None:
                        key_idle_times.append((key, idle_time))
                except Exception as e:
                    logger.warning(f"Error getting idle time for key {key}: {e}")
                    continue
            
            if not key_idle_times:
                logger.info(f"No idle times found for tenant {tenant_id}")
                return stats
            
            # Sort by idle time (oldest first)
            key_idle_times.sort(key=lambda x: x[1], reverse=True)
            
            # Calculate how many keys to remove
            keys_to_remove_count = int(len(key_idle_times) * cleanup_percentage)
            keys_to_remove = [key for key, _ in key_idle_times[:keys_to_remove_count]]
            
            if not keys_to_remove:
                logger.info(f"No keys to remove for tenant {tenant_id}")
                return stats
            
            # Remove the oldest keys
            removed_count = 0
            total_bytes = 0
            
            for key in keys_to_remove:
                try:
                    # Get key size before deletion
                    key_size = await self.redis_client.memory_usage(key)
                    if key_size is None:
                        key_size = 0
                    
                    # Delete the key
                    result = await self.redis_client.delete(key)
                    if result > 0:
                        removed_count += 1
                        total_bytes += key_size
                        logger.debug(f"Removed cache key: {key}")
                except Exception as e:
                    logger.error(f"Error removing key {key}: {e}")
                    continue
            
            # Update statistics
            stats["keys_removed"] = removed_count
            stats["total_bytes_freed"] = total_bytes
            stats["execution_time_ms"] = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            logger.info(f"Cache cleanup completed for tenant {tenant_id}: "
                       f"removed {removed_count}/{len(keys)} keys, "
                       f"freed {total_bytes} bytes in {stats['execution_time_ms']}ms")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error during cache cleanup for tenant {tenant_id}: {e}")
            return {
                "tenant_id": tenant_id,
                "error": str(e),
                "execution_time_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000)
            }
    
    async def cleanup_expired_tenants(self, threshold_hours: int = 6) -> List[Dict[str, Any]]:
        """
        Find tenants that have exceeded the threshold and clean up their cache
        
        Args:
            threshold_hours: Threshold in hours for cumulative active seconds
            
        Returns:
            List of cleanup statistics for each processed tenant
        """
        try:
            results = []
            
            # Get all tenants with cumulative_active_seconds > threshold
            threshold_seconds = threshold_hours * 3600
            tenants = self.db.query(Tenant).filter(
                Tenant.cumulative_active_seconds > threshold_seconds
            ).all()
            
            logger.info(f"Found {len(tenants)} tenants exceeding {threshold_hours} hours threshold")
            
            for tenant in tenants:
                try:
                    # Reset cumulative_active_seconds after cleanup
                    tenant.cumulative_active_seconds = 0
                    self.db.commit()
                    
                    # Clean up cache
                    stats = await self.cleanup_tenant_cache(tenant.id)
                    results.append(stats)
                    
                except Exception as e:
                    logger.error(f"Error processing tenant {tenant.id}: {e}")
                    results.append({
                        "tenant_id": tenant.id,
                        "error": str(e)
                    })
            
            logger.info(f"Cache cleanup task completed for {len(results)} tenants")
            return results
            
        except Exception as e:
            logger.error(f"Error in cleanup_expired_tenants: {e}")
            return [{"error": str(e)}]

# Global cleanup task instance
_cleanup_task: CacheCleanupTask = None

def get_cleanup_task() -> CacheCleanupTask:
    """Get global cache cleanup task instance"""
    global _cleanup_task
    if _cleanup_task is None:
        _cleanup_task = CacheCleanupTask()
    return _cleanup_task

# Celery task functions (would be imported from src.core.celery_tasks)
async def cleanup_tenant_cache_task(tenant_id: str, cleanup_percentage: float = 0.25) -> Dict[str, Any]:
    """
    Celery task to clean up cache for a specific tenant
    
    Args:
        tenant_id: Tenant identifier
        cleanup_percentage: Percentage of keys to remove
        
    Returns:
        Cleanup statistics
    """
    task = get_cleanup_task()
    return await task.cleanup_tenant_cache(tenant_id, cleanup_percentage)

async def cleanup_expired_tenants_task(threshold_hours: int = 6) -> List[Dict[str, Any]]:
    """
    Celery task to clean up cache for all tenants exceeding threshold
    
    Args:
        threshold_hours: Threshold in hours
        
    Returns:
        List of cleanup statistics
    """
    task = get_cleanup_task()
    return await task.cleanup_expired_tenants(threshold_hours)

# Helper function to increment tenant active seconds
async def increment_tenant_active_seconds(tenant_id: str, seconds: int = 1) -> bool:
    """
    Atomically increment tenant's cumulative active seconds
    
    Args:
        tenant_id: Tenant identifier
        seconds: Number of seconds to increment
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Use Redis atomic increment for better performance
        key = f"tenant_active_seconds:{tenant_id}"
        result = await get_redis_client().incrby(key, seconds)
        
        # Set expiration on the key (1 day)
        await get_redis_client().expire(key, 86400)
        
        logger.debug(f"Incremented tenant {tenant_id} active seconds to {result}")
        return True
        
    except Exception as e:
        logger.error(f"Error incrementing tenant active seconds {tenant_id}: {e}")
        return False
