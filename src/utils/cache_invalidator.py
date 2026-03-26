import logging
from typing import Optional, List
from src.core.caching import get_cache_manager
from src.utils.tenant_context import get_current_tenant_id

logger = logging.getLogger(__name__)

class CacheInvalidator:
    """Utility class for cache invalidation operations"""
    
    def __init__(self):
        self.cache_manager = get_cache_manager()
    
    async def invalidate(self, cache_type: str, key: str) -> bool:
        """
        Invalidate a specific cache entry
        
        Args:
            cache_type: Type of cache ('db_query', 'agent_response', 'semantic')
            key: Cache key to invalidate
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            result = await self.cache_manager.invalidate(cache_type, key)
            if result:
                logger.info(f"Successfully invalidated {cache_type} cache for key: {key}")
            else:
                logger.warning(f"Failed to invalidate {cache_type} cache for key: {key}")
            return result
        except Exception as e:
            logger.error(f"Error invalidating cache {cache_type}:{key}: {e}")
            return False
    
    async def invalidate_project(self, project_id: str) -> bool:
        """
        Invalidate all cache entries related to a specific project
        
        Args:
            project_id: Project identifier
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Invalidate different cache types for this project
            cache_keys = [
                f"project:{project_id}",
                f"project_data:{project_id}",
                f"project_settings:{project_id}",
                f"project_kb:{project_id}"
            ]
            
            success = True
            for cache_type in ["db_query", "agent_response", "semantic"]:
                for key in cache_keys:
                    if not await self.invalidate(cache_type, key):
                        success = False
            
            if success:
                logger.info(f"Successfully invalidated all cache for project: {project_id}")
            else:
                logger.warning(f"Partially invalidated cache for project: {project_id}")
            
            return success
        except Exception as e:
            logger.error(f"Error invalidating project cache {project_id}: {e}")
            return False
    
    async def invalidate_tenant_all(self) -> bool:
        """
        Invalidate all cache entries for the current tenant
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            result = await self.cache_manager.invalidate_tenant_all()
            if result:
                tenant_id = get_current_tenant_id()
                logger.info(f"Successfully invalidated all cache for tenant: {tenant_id}")
            else:
                logger.warning("Failed to invalidate tenant cache")
            return result
        except Exception as e:
            logger.error(f"Error invalidating tenant cache: {e}")
            return False
    
    async def invalidate_user_session(self, user_id: str) -> bool:
        """
        Invalidate cache entries related to a specific user session
        
        Args:
            user_id: User identifier
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            session_keys = [
                f"user_session:{user_id}",
                f"user_preferences:{user_id}",
                f"user_projects:{user_id}"
            ]
            
            success = True
            for key in session_keys:
                if not await self.invalidate("db_query", key):
                    success = False
            
            if success:
                logger.info(f"Successfully invalidated session cache for user: {user_id}")
            else:
                logger.warning(f"Partially invalidated session cache for user: {user_id}")
            
            return success
        except Exception as e:
            logger.error(f"Error invalidating user session cache {user_id}: {e}")
            return False
    
    async def invalidate_agent_response(self, agent_name: str, context_hash: str) -> bool:
        """
        Invalidate a specific agent response cache entry
        
        Args:
            agent_name: Name of the agent
            context_hash: Hash of the context used for the response
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            key = f"agent:{agent_name}:context:{context_hash}"
            result = await self.invalidate("agent_response", key)
            
            if result:
                logger.info(f"Successfully invalidated agent response for {agent_name} with context hash {context_hash}")
            else:
                logger.warning(f"Failed to invalidate agent response for {agent_name} with context hash {context_hash}")
            
            return result
        except Exception as e:
            logger.error(f"Error invalidating agent response cache: {e}")
            return False

# Global cache invalidator instance
_cache_invalidator: Optional[CacheInvalidator] = None

def get_cache_invalidator() -> CacheInvalidator:
    """Get global cache invalidator instance"""
    global _cache_invalidator
    if _cache_invalidator is None:
        _cache_invalidator = CacheInvalidator()
    return _cache_invalidator

# Convenience functions for direct use
async def invalidate_cache(cache_type: str, key: str) -> bool:
    """Convenience function to invalidate cache"""
    invalidator = get_cache_invalidator()
    return await invalidator.invalidate(cache_type, key)

async def invalidate_project_cache(project_id: str) -> bool:
    """Convenience function to invalidate project cache"""
    invalidator = get_cache_invalidator()
    return await invalidator.invalidate_project(project_id)

async def invalidate_tenant_cache_all() -> bool:
    """Convenience function to invalidate all tenant cache"""
    invalidator = get_cache_invalidator()
    return await invalidator.invalidate_tenant_all()

async def invalidate_user_session_cache(user_id: str) -> bool:
    """Convenience function to invalidate user session cache"""
    invalidator = get_cache_invalidator()
    return await invalidator.invalidate_user_session(user_id)

async def invalidate_agent_response_cache(agent_name: str, context_hash: str) -> bool:
    """Convenience function to invalidate agent response cache"""
    invalidator = get_cache_invalidator()
    return await invalidator.invalidate_agent_response(agent_name, context_hash)
