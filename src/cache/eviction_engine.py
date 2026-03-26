"""
Cache eviction engine with intelligent eviction policies.
Implements LRU, semantic cache eviction, and cache warming strategies.
"""

import asyncio
import logging
import time
import hashlib
from typing import Any, Dict, List, Optional, Set, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from collections import OrderedDict, defaultdict
import threading
import json

from .cache_engine import CacheLevel, CacheEntry, ThreeLayerCache

logger = logging.getLogger(__name__)


class EvictionStrategy(Enum):
    """Eviction strategy enumeration."""
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"
    SEMANTIC = "semantic"
    SIZE_BASED = "size_based"


@dataclass
class EvictionMetrics:
    """Metrics for eviction operations."""
    evicted_count: int = 0
    evicted_size_bytes: int = 0
    eviction_reasons: Dict[str, int] = None
    last_eviction_time: Optional[datetime] = None
    
    def __post_init__(self):
        if self.eviction_reasons is None:
            self.eviction_reasons = defaultdict(int)


@dataclass
class SemanticCacheEntry:
    """Enhanced cache entry with semantic information."""
    key: str
    value: Any
    semantic_hash: str
    access_pattern: List[datetime]
    related_keys: Set[str]
    importance_score: float
    created_at: datetime
    last_accessed: datetime
    access_count: int
    ttl: float
    tenant_id: Optional[str] = None


class SemanticEvictionEngine:
    """Semantic cache eviction based on content similarity and access patterns."""
    
    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold
        self.semantic_index: Dict[str, SemanticCacheEntry] = {}
        self.similarity_cache: Dict[str, Dict[str, float]] = {}
        self._lock = threading.RLock()
    
    def _calculate_semantic_hash(self, value: Any) -> str:
        """Calculate semantic hash for cache value."""
        try:
            if isinstance(value, (dict, list)):
                # Normalize structure for consistent hashing
                normalized = json.dumps(value, sort_keys=True, default=str)
            else:
                normalized = str(value)
            
            # Create hash from normalized content
            return hashlib.sha256(normalized.encode()).hexdigest()[:16]
        except Exception as e:
            logger.warning(f"Failed to calculate semantic hash: {e}")
            return hashlib.sha256(str(value).encode()).hexdigest()[:16]
    
    def _calculate_similarity(self, hash1: str, hash2: str) -> float:
        """Calculate similarity between two semantic hashes."""
        if hash1 == hash2:
            return 1.0
        
        # Simple similarity based on common prefixes
        # In production, this could use more sophisticated algorithms
        common_chars = sum(1 for a, b in zip(hash1, hash2) if a == b)
        return common_chars / max(len(hash1), len(hash2))
    
    def add_entry(self, key: str, value: Any, tenant_id: Optional[str] = None) -> None:
        """Add entry to semantic index."""
        with self._lock:
            semantic_hash = self._calculate_semantic_hash(value)
            
            entry = SemanticCacheEntry(
                key=key,
                value=value,
                semantic_hash=semantic_hash,
                access_pattern=[datetime.utcnow()],
                related_keys=set(),
                importance_score=1.0,
                created_at=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                access_count=1,
                ttl=3600.0,
                tenant_id=tenant_id
            )
            
            self.semantic_index[key] = entry
            
            # Find similar entries
            for other_key, other_entry in self.semantic_index.items():
                if other_key != key:
                    similarity = self._calculate_similarity(semantic_hash, other_entry.semantic_hash)
                    if similarity > self.similarity_threshold:
                        entry.related_keys.add(other_key)
                        other_entry.related_keys.add(key)
    
    def update_access(self, key: str) -> None:
        """Update access pattern for entry."""
        with self._lock:
            if key in self.semantic_index:
                entry = self.semantic_index[key]
                entry.last_accessed = datetime.utcnow()
                entry.access_count += 1
                entry.access_pattern.append(datetime.utcnow())
                
                # Keep only recent access patterns (last 100)
                if len(entry.access_pattern) > 100:
                    entry.access_pattern = entry.access_pattern[-100:]
    
    def get_eviction_candidates(self, max_evict: int = 10) -> List[str]:
        """Get candidates for eviction based on semantic analysis."""
        with self._lock:
            candidates = []
            
            for key, entry in self.semantic_index.items():
                # Calculate eviction score based on multiple factors
                age_score = (datetime.utcnow() - entry.created_at).total_seconds() / 3600
                access_score = 1.0 / max(entry.access_count, 1)
                recency_score = (datetime.utcnow() - entry.last_accessed).total_seconds() / 3600
                similarity_score = len(entry.related_keys) * 0.1  # Penalize if many similar entries exist
                
                eviction_score = age_score + access_score + recency_score + similarity_score
                
                candidates.append((key, eviction_score))
            
            # Sort by eviction score (highest first)
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            return [key for key, _ in candidates[:max_evict]]
    
    def remove_entry(self, key: str) -> None:
        """Remove entry from semantic index."""
        with self._lock:
            if key in self.semantic_index:
                entry = self.semantic_index[key]
                
                # Remove from related entries
                for related_key in entry.related_keys:
                    if related_key in self.semantic_index:
                        self.semantic_index[related_key].related_keys.discard(key)
                
                del self.semantic_index[key]


class CacheEvictionEngine:
    """Main cache eviction engine with multiple strategies."""
    
    def __init__(self, cache: ThreeLayerCache):
        self.cache = cache
        self.semantic_engine = SemanticEvictionEngine()
        self.metrics = EvictionMetrics()
        self._lock = threading.RLock()
        
        # Eviction thresholds
        self.l1_size_threshold = 0.9  # Evict when 90% full
        self.l2_size_threshold = 0.85  # Evict when 85% full
        self.ttl_cleanup_interval = 300  # 5 minutes
        self.semantic_cleanup_interval = 600  # 10 minutes
        
        # Start background cleanup tasks
        self._cleanup_task = None
        self._running = False
    
    async def start(self) -> None:
        """Start the eviction engine background tasks."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._background_cleanup())
        logger.info("Cache eviction engine started")
    
    async def stop(self) -> None:
        """Stop the eviction engine background tasks."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Cache eviction engine stopped")
    
    async def _background_cleanup(self) -> None:
        """Background cleanup task."""
        while self._running:
            try:
                await asyncio.sleep(self.ttl_cleanup_interval)
                await self.cleanup_expired_entries()
                
                await asyncio.sleep(self.semantic_cleanup_interval)
                await self.semantic_eviction()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background cleanup: {e}")
    
    async def evict_lru(self, level: CacheLevel, max_evict: int = 10) -> EvictionMetrics:
        """Evict entries using LRU strategy."""
        with self._lock:
            metrics = EvictionMetrics()
            
            if level == CacheLevel.L1_MEMORY:
                # L1 cache LRU eviction
                l1_cache = self.cache.l1_cache
                if len(l1_cache._cache) > l1_cache.max_size * self.l1_size_threshold:
                    evicted = 0
                    for key in list(l1_cache._access_order.keys())[:max_evict]:
                        if l1_cache.delete(key):
                            evicted += 1
                            metrics.evicted_count += 1
                            self.semantic_engine.remove_entry(key)
                    
                    metrics.eviction_reasons["lru_l1"] = evicted
            
            elif level == CacheLevel.L2_REDIS:
                # L2 cache LRU eviction (Redis handles this automatically)
                # We can trigger Redis memory eviction
                await self.cache.l2_cache.redis_client.memory_purge()
                metrics.eviction_reasons["lru_l2"] = 1
            
            metrics.last_eviction_time = datetime.utcnow()
            self._update_metrics(metrics)
            return metrics
    
    async def evict_by_ttl(self, level: CacheLevel) -> EvictionMetrics:
        """Evict expired entries."""
        with self._lock:
            metrics = EvictionMetrics()
            
            if level == CacheLevel.L1_MEMORY:
                l1_cache = self.cache.l1_cache
                expired_keys = []
                
                for key, entry in l1_cache._cache.items():
                    if entry.is_expired():
                        expired_keys.append(key)
                
                for key in expired_keys:
                    if l1_cache.delete(key):
                        metrics.evicted_count += 1
                        self.semantic_engine.remove_entry(key)
                
                metrics.eviction_reasons["ttl_l1"] = len(expired_keys)
            
            elif level == CacheLevel.L2_REDIS:
                # Redis handles TTL automatically, but we can clean up our semantic index
                # This is a simplified approach - in production, you'd want to check Redis TTL
                pass
            
            metrics.last_eviction_time = datetime.utcnow()
            self._update_metrics(metrics)
            return metrics
    
    async def semantic_eviction(self, max_evict: int = 20) -> EvictionMetrics:
        """Evict entries based on semantic similarity."""
        with self._lock:
            metrics = EvictionMetrics()
            
            candidates = self.semantic_engine.get_eviction_candidates(max_evict)
            evicted = 0
            
            for key in candidates:
                # Try to evict from all levels
                deleted = await self.cache.delete(key)
                if deleted:
                    evicted += 1
                    metrics.evicted_count += 1
                    self.semantic_engine.remove_entry(key)
            
            metrics.eviction_reasons["semantic"] = evicted
            metrics.last_eviction_time = datetime.utcnow()
            self._update_metrics(metrics)
            return metrics
    
    async def cleanup_expired_entries(self) -> EvictionMetrics:
        """Clean up expired entries from all levels."""
        metrics = EvictionMetrics()
        
        # Clean L1 cache
        l1_metrics = await self.evict_by_ttl(CacheLevel.L1_MEMORY)
        metrics.evicted_count += l1_metrics.evicted_count
        metrics.eviction_reasons.update(l1_metrics.eviction_reasons)
        
        # Clean L2 cache (Redis handles TTL automatically)
        # Clean L3 cache if implemented
        
        metrics.last_eviction_time = datetime.utcnow()
        self._update_metrics(metrics)
        return metrics
    
    async def evict_tenant_data(self, tenant_id: str) -> EvictionMetrics:
        """Evict all data for a specific tenant."""
        with self._lock:
            metrics = EvictionMetrics()
            
            # Clear tenant data from all cache levels
            result = await self.cache.clear_tenant(tenant_id)
            
            # Remove from semantic index
            tenant_keys = [key for key, entry in self.semantic_engine.semantic_index.items() 
                          if entry.tenant_id == tenant_id]
            
            for key in tenant_keys:
                self.semantic_engine.remove_entry(key)
            
            metrics.evicted_count = result.get("total_evicted", 0)
            metrics.eviction_reasons["tenant_clear"] = metrics.evicted_count
            metrics.last_eviction_time = datetime.utcnow()
            self._update_metrics(metrics)
            return metrics
    
    def add_to_semantic_index(self, key: str, value: Any, tenant_id: Optional[str] = None) -> None:
        """Add entry to semantic index for intelligent eviction."""
        self.semantic_engine.add_entry(key, value, tenant_id)
    
    def update_semantic_access(self, key: str) -> None:
        """Update access pattern in semantic index."""
        self.semantic_engine.update_access(key)
    
    def _update_metrics(self, new_metrics: EvictionMetrics) -> None:
        """Update global eviction metrics."""
        self.metrics.evicted_count += new_metrics.evicted_count
        self.metrics.evicted_size_bytes += new_metrics.evicted_size_bytes
        
        for reason, count in new_metrics.eviction_reasons.items():
            self.metrics.eviction_reasons[reason] += count
        
        self.metrics.last_eviction_time = new_metrics.last_eviction_time
    
    def get_metrics(self) -> EvictionMetrics:
        """Get current eviction metrics."""
        return self.metrics
    
    async def warm_cache(self, warming_strategy: Callable[[], List[tuple[str, Any]]]) -> None:
        """Warm cache using provided strategy."""
        try:
            warming_data = warming_strategy()
            
            for key, value in warming_data:
                await self.cache.set(key, value)
                self.add_to_semantic_index(key, value)
            
            logger.info(f"Cache warmed with {len(warming_data)} entries")
            
        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        stats = {
            "l1_cache": {
                "size": len(self.cache.l1_cache._cache),
                "max_size": self.cache.l1_cache.max_size,
                "utilization": len(self.cache.l1_cache._cache) / self.cache.l1_cache.max_size
            },
            "semantic_index": {
                "size": len(self.semantic_engine.semantic_index),
                "similarity_threshold": self.semantic_engine.similarity_threshold
            },
            "eviction_metrics": {
                "total_evicted": self.metrics.evicted_count,
                "eviction_reasons": dict(self.metrics.eviction_reasons),
                "last_eviction": self.metrics.last_eviction_time.isoformat() if self.metrics.last_eviction_time else None
            }
        }
        
        # Add Redis stats if available
        try:
            if self.cache.l2_cache.redis_client:
                redis_info = await self.cache.l2_cache.redis_client.info("memory")
                stats["l2_cache"] = {
                    "used_memory": redis_info.get("used_memory", 0),
                    "max_memory": redis_info.get("maxmemory", 0),
                    "utilization": redis_info.get("used_memory", 0) / max(redis_info.get("maxmemory", 1), 1)
                }
        except Exception as e:
            logger.warning(f"Could not get Redis stats: {e}")
            stats["l2_cache"] = {"error": str(e)}
        
        return stats

