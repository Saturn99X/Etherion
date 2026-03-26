"""
Cache metrics and monitoring system.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
from src.cache.cache_engine import ThreeLayerCache, CacheLevel

logger = logging.getLogger(__name__)


@dataclass
class CacheMetrics:
    """Cache metrics data structure."""
    timestamp: float
    level: str
    tenant_id: Optional[str]
    operation: str  # 'get', 'set', 'delete', 'miss', 'hit'
    key: str
    response_time_ms: float
    cache_size: int
    hit_rate: float
    memory_usage: int


@dataclass
class CacheStats:
    """Aggregated cache statistics."""
    total_operations: int
    total_hits: int
    total_misses: int
    hit_rate: float
    average_response_time_ms: float
    total_memory_usage: int
    tenant_stats: Dict[str, Dict[str, Any]]
    level_stats: Dict[str, Dict[str, Any]]
    operation_stats: Dict[str, int]


class CacheMetricsCollector:
    """Collects and aggregates cache metrics."""
    
    def __init__(self, max_metrics_history: int = 10000):
        self.max_metrics_history = max_metrics_history
        self.metrics_history: deque = deque(maxlen=max_metrics_history)
        self.tenant_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'operations': 0,
            'hits': 0,
            'misses': 0,
            'response_times': deque(maxlen=1000),
            'memory_usage': 0
        })
        self.level_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'operations': 0,
            'hits': 0,
            'misses': 0,
            'response_times': deque(maxlen=1000),
            'cache_size': 0
        })
        self.operation_stats: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
    
    async def record_metric(self, metric: CacheMetrics) -> None:
        """Record a cache metric."""
        async with self._lock:
            # Add to history
            self.metrics_history.append(metric)
            
            # Update tenant stats
            tenant_id = metric.tenant_id or 'global'
            tenant_stat = self.tenant_stats[tenant_id]
            tenant_stat['operations'] += 1
            tenant_stat['response_times'].append(metric.response_time_ms)
            tenant_stat['memory_usage'] = metric.memory_usage
            
            if metric.operation == 'hit':
                tenant_stat['hits'] += 1
            elif metric.operation == 'miss':
                tenant_stat['misses'] += 1
            
            # Update level stats
            level_stat = self.level_stats[metric.level]
            level_stat['operations'] += 1
            level_stat['response_times'].append(metric.response_time_ms)
            level_stat['cache_size'] = metric.cache_size
            
            if metric.operation == 'hit':
                level_stat['hits'] += 1
            elif metric.operation == 'miss':
                level_stat['misses'] += 1
            
            # Update operation stats
            self.operation_stats[metric.operation] += 1
    
    async def get_stats(self, tenant_id: Optional[str] = None, 
                       time_window_minutes: int = 60) -> CacheStats:
        """Get aggregated cache statistics."""
        async with self._lock:
            cutoff_time = time.time() - (time_window_minutes * 60)
            
            # Filter metrics by time window
            recent_metrics = [
                m for m in self.metrics_history 
                if m.timestamp >= cutoff_time
            ]
            
            # Filter by tenant if specified
            if tenant_id:
                recent_metrics = [
                    m for m in recent_metrics 
                    if m.tenant_id == tenant_id
                ]
            
            # Calculate totals
            total_operations = len(recent_metrics)
            total_hits = sum(1 for m in recent_metrics if m.operation == 'hit')
            total_misses = sum(1 for m in recent_metrics if m.operation == 'miss')
            hit_rate = total_hits / (total_hits + total_misses) if (total_hits + total_misses) > 0 else 0.0
            
            # Calculate average response time
            response_times = [m.response_time_ms for m in recent_metrics]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
            
            # Calculate total memory usage
            total_memory = sum(m.memory_usage for m in recent_metrics)
            
            # Prepare tenant stats
            tenant_stats = {}
            for tid, stats in self.tenant_stats.items():
                if tenant_id is None or tid == tenant_id:
                    tenant_stats[tid] = {
                        'operations': stats['operations'],
                        'hits': stats['hits'],
                        'misses': stats['misses'],
                        'hit_rate': stats['hits'] / (stats['hits'] + stats['misses']) if (stats['hits'] + stats['misses']) > 0 else 0.0,
                        'avg_response_time_ms': sum(stats['response_times']) / len(stats['response_times']) if stats['response_times'] else 0.0,
                        'memory_usage': stats['memory_usage']
                    }
            
            # Prepare level stats
            level_stats = {}
            for level, stats in self.level_stats.items():
                level_stats[level] = {
                    'operations': stats['operations'],
                    'hits': stats['hits'],
                    'misses': stats['misses'],
                    'hit_rate': stats['hits'] / (stats['hits'] + stats['misses']) if (stats['hits'] + stats['misses']) > 0 else 0.0,
                    'avg_response_time_ms': sum(stats['response_times']) / len(stats['response_times']) if stats['response_times'] else 0.0,
                    'cache_size': stats['cache_size']
                }
            
            return CacheStats(
                total_operations=total_operations,
                total_hits=total_hits,
                total_misses=total_misses,
                hit_rate=hit_rate,
                average_response_time_ms=avg_response_time,
                total_memory_usage=total_memory,
                tenant_stats=tenant_stats,
                level_stats=level_stats,
                operation_stats=dict(self.operation_stats)
            )
    
    async def get_tenant_metrics(self, tenant_id: str, 
                                time_window_minutes: int = 60) -> Dict[str, Any]:
        """Get metrics for a specific tenant."""
        stats = await self.get_stats(tenant_id, time_window_minutes)
        return {
            'tenant_id': tenant_id,
            'time_window_minutes': time_window_minutes,
            'total_operations': stats.total_operations,
            'hit_rate': stats.hit_rate,
            'average_response_time_ms': stats.average_response_time_ms,
            'memory_usage': stats.total_memory_usage
        }
    
    async def get_performance_alerts(self, threshold_hit_rate: float = 0.8,
                                   threshold_response_time_ms: float = 100.0) -> List[Dict[str, Any]]:
        """Get performance alerts based on thresholds."""
        alerts = []
        
        # Check overall performance
        stats = await self.get_stats()
        if stats.hit_rate < threshold_hit_rate:
            alerts.append({
                'type': 'low_hit_rate',
                'severity': 'warning',
                'message': f'Cache hit rate ({stats.hit_rate:.2%}) is below threshold ({threshold_hit_rate:.2%})',
                'value': stats.hit_rate,
                'threshold': threshold_hit_rate
            })
        
        if stats.average_response_time_ms > threshold_response_time_ms:
            alerts.append({
                'type': 'high_response_time',
                'severity': 'warning',
                'message': f'Average response time ({stats.average_response_time_ms:.2f}ms) exceeds threshold ({threshold_response_time_ms}ms)',
                'value': stats.average_response_time_ms,
                'threshold': threshold_response_time_ms
            })
        
        # Check tenant-specific performance
        for tenant_id, tenant_stat in stats.tenant_stats.items():
            if tenant_stat['hit_rate'] < threshold_hit_rate:
                alerts.append({
                    'type': 'tenant_low_hit_rate',
                    'severity': 'warning',
                    'tenant_id': tenant_id,
                    'message': f'Tenant {tenant_id} hit rate ({tenant_stat["hit_rate"]:.2%}) is below threshold',
                    'value': tenant_stat['hit_rate'],
                    'threshold': threshold_hit_rate
                })
        
        return alerts


class CacheMetricsMiddleware:
    """Middleware for automatically collecting cache metrics."""
    
    def __init__(self, cache: ThreeLayerCache, metrics_collector: CacheMetricsCollector):
        self.cache = cache
        self.metrics_collector = metrics_collector
    
    async def get_with_metrics(self, key: str, tenant_id: Optional[str] = None) -> Optional[Any]:
        """Get value with metrics collection."""
        start_time = time.time()
        
        try:
            result = await self.cache.get(key, tenant_id)
            operation = 'hit' if result is not None else 'miss'
            
            # Get cache stats
            cache_stats = await self.cache.get_stats()
            level_stats = cache_stats.get('l1', {})
            
            metric = CacheMetrics(
                timestamp=time.time(),
                level='l1',
                tenant_id=tenant_id,
                operation=operation,
                key=key,
                response_time_ms=(time.time() - start_time) * 1000,
                cache_size=level_stats.get('size', 0),
                hit_rate=level_stats.get('hit_rate', 0.0),
                memory_usage=level_stats.get('memory_usage', 0)
            )
            
            await self.metrics_collector.record_metric(metric)
            return result
            
        except Exception as e:
            logger.error(f"Error in get_with_metrics: {e}")
            return None
    
    async def set_with_metrics(self, key: str, value: Any, ttl: Optional[float] = None,
                              tenant_id: Optional[str] = None, 
                              levels: List[CacheLevel] = None) -> None:
        """Set value with metrics collection."""
        start_time = time.time()
        
        try:
            await self.cache.set(key, value, ttl, tenant_id, levels)
            
            # Get cache stats
            cache_stats = await self.cache.get_stats()
            level_stats = cache_stats.get('l1', {})
            
            metric = CacheMetrics(
                timestamp=time.time(),
                level='l1',
                tenant_id=tenant_id,
                operation='set',
                key=key,
                response_time_ms=(time.time() - start_time) * 1000,
                cache_size=level_stats.get('size', 0),
                hit_rate=level_stats.get('hit_rate', 0.0),
                memory_usage=level_stats.get('memory_usage', 0)
            )
            
            await self.metrics_collector.record_metric(metric)
            
        except Exception as e:
            logger.error(f"Error in set_with_metrics: {e}")


# Global metrics collector instance
_metrics_collector: Optional[CacheMetricsCollector] = None


def get_metrics_collector() -> CacheMetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = CacheMetricsCollector()
    return _metrics_collector


async def get_cache_metrics(tenant_id: Optional[str] = None, 
                           time_window_minutes: int = 60) -> Dict[str, Any]:
    """Get cache metrics for monitoring dashboard."""
    collector = get_metrics_collector()
    stats = await collector.get_stats(tenant_id, time_window_minutes)
    
    return {
        'timestamp': datetime.utcnow().isoformat(),
        'time_window_minutes': time_window_minutes,
        'tenant_id': tenant_id,
        'overall_stats': asdict(stats),
        'alerts': await collector.get_performance_alerts()
    }
