import logging
import time
import asyncio
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque
from datetime import datetime, timedelta
import json

# Temporarily commented out due to dependency issues
# from src.core.caching import get_cache_manager
from src.database.db import get_db, session_scope
from src.utils.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)

class ObservationPerformanceMonitor:
    """Monitor performance overhead of the user observation system"""

    def __init__(self):
        # Temporarily commented out due to dependency issues
        # self.cache_manager = get_cache_manager()
        self.db = get_db()
        self.metrics = defaultdict(lambda: {
            'count': 0,
            'total_time': 0.0,
            'min_time': float('inf'),
            'max_time': 0.0,
            'avg_time': 0.0,
            'errors': 0,
            'last_recorded': None
        })

        # Store recent performance samples for analysis
        self.performance_samples = defaultdict(lambda: deque(maxlen=100))

        # Performance thresholds (in seconds)
        self.performance_thresholds = {
            'record_interaction': 0.1,  # 100ms max for recording
            'generate_system_instructions': 0.05,  # 50ms max for generation
            'get_user_observations': 0.02,  # 20ms max for retrieval
        }

    def start_timing(self, operation: str, user_id: int, tenant_id: int) -> str:
        """Start timing an operation"""
        timer_id = f"{operation}:{user_id}:{tenant_id}:{time.time()}"
        return timer_id

    def end_timing(self, timer_id: str, operation: str, user_id: int, tenant_id: int) -> float:
        """End timing and record metrics"""
        try:
            parts = timer_id.split(':')
            if len(parts) < 4:
                return 0.0

            start_time = float(parts[3])
            duration = time.time() - start_time

            # Record metrics
            key = f"{operation}:{tenant_id}"
            self.metrics[key]['count'] += 1
            self.metrics[key]['total_time'] += duration
            self.metrics[key]['min_time'] = min(self.metrics[key]['min_time'], duration)
            self.metrics[key]['max_time'] = max(self.metrics[key]['max_time'], duration)
            self.metrics[key]['avg_time'] = self.metrics[key]['total_time'] / self.metrics[key]['count']
            self.metrics[key]['last_recorded'] = datetime.utcnow()

            # Store sample
            self.performance_samples[key].append({
                'timestamp': datetime.utcnow(),
                'duration': duration,
                'user_id': user_id,
                'operation': operation
            })

            # Check threshold
            threshold = self.performance_thresholds.get(operation, 0.1)
            if duration > threshold:
                logger.warning(f"Performance threshold exceeded for {operation}: {duration:.3f}s (threshold: {threshold}s)")

            return duration

        except Exception as e:
            logger.error(f"Error recording performance metrics: {e}")
            return 0.0

    def record_error(self, operation: str, tenant_id: int, error: Exception) -> None:
        """Record an error in the observation system"""
        key = f"{operation}:{tenant_id}"
        self.metrics[key]['errors'] += 1
        logger.error(f"Observation system error in {operation}: {error}")

    def get_performance_metrics(self, operation: str = None, tenant_id: int = None) -> Dict[str, Any]:
        """Get performance metrics"""
        try:
            if operation and tenant_id:
                key = f"{operation}:{tenant_id}"
                return dict(self.metrics[key])

            # Return all metrics
            result = {}
            for key, metrics in self.metrics.items():
                if tenant_id:
                    if key.endswith(f":{tenant_id}"):
                        result[key] = dict(metrics)
                else:
                    result[key] = dict(metrics)

            return result

        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}

    def get_performance_summary(self, tenant_id: int = None) -> Dict[str, Any]:
        """Get a summary of performance metrics"""
        try:
            summary = {
                'total_operations': 0,
                'total_time': 0.0,
                'avg_operation_time': 0.0,
                'error_rate': 0.0,
                'operations_by_type': {},
                'performance_issues': [],
                'recommendations': []
            }

            for key, metrics in self.metrics.items():
                if tenant_id and not key.endswith(f":{tenant_id}"):
                    continue

                summary['total_operations'] += metrics['count']
                summary['total_time'] += metrics['total_time']

                op_type = key.split(':')[0]
                if op_type not in summary['operations_by_type']:
                    summary['operations_by_type'][op_type] = {
                        'count': 0,
                        'total_time': 0.0,
                        'avg_time': 0.0,
                        'error_rate': 0.0
                    }

                summary['operations_by_type'][op_type]['count'] += metrics['count']
                summary['operations_by_type'][op_type]['total_time'] += metrics['total_time']
                summary['operations_by_type'][op_type]['avg_time'] = (
                    metrics['total_time'] / metrics['count'] if metrics['count'] > 0 else 0
                )
                summary['operations_by_type'][op_type]['error_rate'] = (
                    metrics['errors'] / metrics['count'] if metrics['count'] > 0 else 0
                )

                # Check for performance issues
                threshold = self.performance_thresholds.get(op_type, 0.1)
                if metrics['avg_time'] > threshold:
                    summary['performance_issues'].append({
                        'operation': op_type,
                        'avg_time': metrics['avg_time'],
                        'threshold': threshold,
                        'severity': 'high' if metrics['avg_time'] > threshold * 2 else 'medium'
                    })

            if summary['total_operations'] > 0:
                summary['avg_operation_time'] = summary['total_time'] / summary['total_operations']
                summary['error_rate'] = sum(
                    op['error_rate'] * op['count']
                    for op in summary['operations_by_type'].values()
                ) / summary['total_operations'] if summary['total_operations'] > 0 else 0

            # Generate recommendations
            summary['recommendations'] = self._generate_recommendations(summary)

            return summary

        except Exception as e:
            logger.error(f"Error generating performance summary: {e}")
            return {}

    def _generate_recommendations(self, summary: Dict[str, Any]) -> List[str]:
        """Generate performance recommendations"""
        recommendations = []

        if summary.get('error_rate', 0) > 0.1:  # 10% error rate
            recommendations.append("High error rate detected. Consider adding retry logic and better error handling.")

        for issue in summary.get('performance_issues', []):
            if issue['severity'] == 'high':
                recommendations.append(f"Performance issue with {issue['operation']}: "
                                     f"avg {issue['avg_time']:.3f}s exceeds threshold {issue['threshold']}s by 2x+")

        if summary.get('total_operations', 0) > 1000:
            recommendations.append("High volume of observations. Consider implementing sampling or batching.")

        # Check for specific operation issues
        ops = summary.get('operations_by_type', {})
        if 'record_interaction' in ops and ops['record_interaction']['avg_time'] > 0.05:
            recommendations.append("Slow interaction recording. Consider optimizing database writes or using async operations.")

        return recommendations

    async def log_performance_report(self, tenant_id: int = None) -> None:
        """Log a performance report"""
        try:
            summary = self.get_performance_summary(tenant_id)

            if summary.get('total_operations', 0) == 0:
                logger.info("No observation system operations recorded")
                return

            logger.info("=== User Observation System Performance Report ===")
            logger.info(f"Total Operations: {summary['total_operations']}")
            logger.info(f"Total Time: {summary['total_time']:.3f}s")
            logger.info(f"Average Operation Time: {summary['avg_operation_time']:.3f}s")
            logger.info(f"Overall Error Rate: {summary['error_rate']:.2%}")

            for op_type, metrics in summary.get('operations_by_type', {}).items():
                logger.info(f"  {op_type}: {metrics['count']} ops, "
                           f"avg {metrics['avg_time']:.3f}s, "
                           f"error rate {metrics['error_rate']:.2%}")

            if summary.get('performance_issues'):
                logger.warning("Performance Issues:")
                for issue in summary['performance_issues']:
                    logger.warning(f"  {issue['operation']}: {issue['avg_time']:.3f}s "
                                  f"(threshold: {issue['threshold']}s, severity: {issue['severity']})")

            if summary.get('recommendations'):
                logger.info("Recommendations:")
                for rec in summary['recommendations']:
                    logger.info(f"  - {rec}")

        except Exception as e:
            logger.error(f"Error logging performance report: {e}")

    async def export_metrics_to_cache(self, tenant_id: int = None) -> None:
        """Export metrics to cache for monitoring dashboards"""
        try:
            summary = self.get_performance_summary(tenant_id)
            cache_key = f"observation_performance_metrics:{tenant_id or 'all'}"

            # Cache for 1 hour
            # await self.cache_manager.set_db_query(cache_key, summary, expire=3600)

            logger.debug(f"Exported observation performance metrics to cache: {cache_key}")

        except Exception as e:
            logger.error(f"Error exporting metrics to cache: {e}")

    async def cleanup_old_metrics(self, days: int = 7) -> None:
        """Clean up old performance metrics"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Remove old samples
            for key in list(self.performance_samples.keys()):
                self.performance_samples[key] = deque(
                    [sample for sample in self.performance_samples[key]
                     if sample['timestamp'] > cutoff_date],
                    maxlen=100
                )

                if not self.performance_samples[key]:
                    del self.performance_samples[key]

            # Reset metrics older than cutoff
            for key in list(self.metrics.keys()):
                if self.metrics[key]['last_recorded'] and self.metrics[key]['last_recorded'] < cutoff_date:
                    del self.metrics[key]

            logger.info(f"Cleaned up observation performance metrics older than {days} days")

        except Exception as e:
            logger.error(f"Error cleaning up old metrics: {e}")

    async def background_monitoring_task(self) -> None:
        """Background task for monitoring and alerting"""
        try:
            while True:
                # Wait for 5 minutes
                await asyncio.sleep(300)

                # Get current tenant
                tenant_id = get_tenant_context()

                # Log performance report
                await self.log_performance_report(tenant_id)

                # Export to cache
                await self.export_metrics_to_cache(tenant_id)

                # Cleanup old metrics weekly
                if datetime.utcnow().weekday() == 0:  # Monday
                    await self.cleanup_old_metrics()

        except asyncio.CancelledError:
            logger.info("Background monitoring task cancelled")
        except Exception as e:
            logger.error(f"Error in background monitoring task: {e}")

# Global performance monitor instance
_performance_monitor: Optional[ObservationPerformanceMonitor] = None

def get_observation_performance_monitor() -> ObservationPerformanceMonitor:
    """Get the global performance monitor instance"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = ObservationPerformanceMonitor()
    return _performance_monitor

# Convenience functions for performance monitoring
def start_observation_timing(operation: str, user_id: int, tenant_id: int) -> str:
    """Start timing an observation operation"""
    monitor = get_observation_performance_monitor()
    return monitor.start_timing(operation, user_id, tenant_id)

def end_observation_timing(timer_id: str, operation: str, user_id: int, tenant_id: int) -> float:
    """End timing and record metrics"""
    monitor = get_observation_performance_monitor()
    return monitor.end_timing(timer_id, operation, user_id, tenant_id)

def record_observation_error(operation: str, tenant_id: int, error: Exception) -> None:
    """Record an error in the observation system"""
    monitor = get_observation_performance_monitor()
    monitor.record_error(operation, tenant_id, error)

async def get_observation_performance_summary(tenant_id: int = None) -> Dict[str, Any]:
    """Get a summary of observation system performance"""
    monitor = get_observation_performance_monitor()
    return monitor.get_performance_summary(tenant_id)

async def log_observation_performance_report(tenant_id: int = None) -> None:
    """Log a performance report for the observation system"""
    monitor = get_observation_performance_monitor()
    await monitor.log_performance_report(tenant_id)
