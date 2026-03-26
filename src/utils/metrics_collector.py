# src/utils/metrics_collector.py
import time
import threading
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
from datetime import datetime, timedelta
import json


@dataclass
class Metric:
    """Represents a single metric data point."""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)
    unit: str = ""


@dataclass
class AggregatedMetric:
    """Represents an aggregated metric over a time period."""
    name: str
    count: int
    sum: float
    min: float
    max: float
    avg: float
    tags: Dict[str, str] = field(default_factory=dict)
    unit: str = ""


class MetricsCollector:
    """Collects and aggregates application metrics."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(MetricsCollector, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the metrics collector."""
        self.metrics_buffer: List[Metric] = []
        self.buffer_lock = threading.RLock()
        self.retention_period = int(os.getenv('METRICS_RETENTION_HOURS', '24')) * 3600
        self.max_buffer_size = int(os.getenv('METRICS_BUFFER_SIZE', '10000'))
        
        # For real-time aggregation
        self.aggregators: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        self.aggregation_window = int(os.getenv('METRICS_AGGREGATION_WINDOW', '60'))  # 1 minute
        
        # Start cleanup thread
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """Start a background thread to clean up old metrics."""
        def cleanup_old_metrics():
            while True:
                time.sleep(300)  # Run every 5 minutes
                self._cleanup_old_metrics()
        
        cleanup_thread = threading.Thread(target=cleanup_old_metrics, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_old_metrics(self):
        """Remove metrics older than retention period."""
        cutoff_time = time.time() - self.retention_period
        
        with self.buffer_lock:
            # Remove old metrics from buffer
            self.metrics_buffer = [
                metric for metric in self.metrics_buffer 
                if metric.timestamp > cutoff_time
            ]
            
            # Remove old data from aggregators
            current_time = time.time()
            for metric_name, tag_aggregators in self.aggregators.items():
                for tag_key, time_series in tag_aggregators.items():
                    # Remove data points older than aggregation window
                    while time_series and time_series[0][0] < current_time - self.aggregation_window:
                        time_series.popleft()
    
    def record_metric(self, name: str, value: float, unit: str = "", **tags):
        """Record a metric data point."""
        metric = Metric(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags,
            unit=unit
        )
        
        with self.buffer_lock:
            self.metrics_buffer.append(metric)
            
            # Maintain buffer size
            if len(self.metrics_buffer) > self.max_buffer_size:
                # Remove oldest metrics
                self.metrics_buffer = self.metrics_buffer[-self.max_buffer_size:]
            
            # Add to real-time aggregators
            tag_key = json.dumps(tags, sort_keys=True)
            self.aggregators[name][tag_key].append((time.time(), value))
            
            # Maintain aggregator window size
            current_time = time.time()
            time_series = self.aggregators[name][tag_key]
            while time_series and time_series[0][0] < current_time - self.aggregation_window:
                time_series.popleft()
    
    def get_metrics(self, since: Optional[float] = None) -> List[Metric]:
        """Get metrics from the buffer."""
        if since is None:
            since = time.time() - 3600  # Last hour by default
        
        with self.buffer_lock:
            return [metric for metric in self.metrics_buffer if metric.timestamp >= since]
    
    def get_aggregated_metrics(self, metric_name: str, **tags) -> Optional[AggregatedMetric]:
        """Get aggregated metrics for a specific metric and tags."""
        tag_key = json.dumps(tags, sort_keys=True)
        
        with self.buffer_lock:
            if metric_name not in self.aggregators or tag_key not in self.aggregators[metric_name]:
                return None
            
            time_series = self.aggregators[metric_name][tag_key]
            if not time_series:
                return None
            
            values = [value for _, value in time_series]
            if not values:
                return None
            
            return AggregatedMetric(
                name=metric_name,
                count=len(values),
                sum=sum(values),
                min=min(values),
                max=max(values),
                avg=sum(values) / len(values),
                tags=tags
            )
    
    def get_recent_metrics_summary(self, window_seconds: int = 60) -> Dict[str, AggregatedMetric]:
        """Get a summary of recent metrics for all metric types."""
        cutoff_time = time.time() - window_seconds
        summary = {}
        
        with self.buffer_lock:
            # Group metrics by name and tags
            metric_groups = defaultdict(list)
            for metric in self.metrics_buffer:
                if metric.timestamp >= cutoff_time:
                    tag_key = json.dumps(metric.tags, sort_keys=True)
                    group_key = f"{metric.name}:{tag_key}"
                    metric_groups[group_key].append(metric)
            
            # Calculate aggregates for each group
            for group_key, metrics in metric_groups.items():
                if not metrics:
                    continue
                
                name = metrics[0].name
                tags = metrics[0].tags
                values = [m.value for m in metrics]
                
                summary[group_key] = AggregatedMetric(
                    name=name,
                    count=len(values),
                    sum=sum(values),
                    min=min(values),
                    max=max(values),
                    avg=sum(values) / len(values),
                    tags=tags,
                    unit=metrics[0].unit
                )
        
        return summary
    
    def get_error_rate(self, component: str = None, window_seconds: int = 300) -> float:
        """Calculate error rate for a component or overall."""
        cutoff_time = time.time() - window_seconds
        error_count = 0
        total_count = 0
        
        with self.buffer_lock:
            for metric in self.metrics_buffer:
                if metric.timestamp < cutoff_time:
                    continue
                
                if component and metric.tags.get('component') != component:
                    continue
                
                if metric.name == 'operation_result':
                    total_count += 1
                    if metric.tags.get('status') == 'error':
                        error_count += 1
        
        return error_count / max(total_count, 1) if total_count > 0 else 0.0
    
    def get_percentile(self, metric_name: str, percentile: float, 
                      window_seconds: int = 300, **tags) -> Optional[float]:
        """Calculate percentile for a metric."""
        cutoff_time = time.time() - window_seconds
        values = []
        
        with self.buffer_lock:
            for metric in self.metrics_buffer:
                if (metric.timestamp >= cutoff_time and 
                    metric.name == metric_name and
                    all(metric.tags.get(k) == v for k, v in tags.items())):
                    values.append(metric.value)
        
        if not values:
            return None
        
        values.sort()
        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]


# Global metrics collector instance
metrics_collector = MetricsCollector()


def record_api_call_latency(api_name: str, latency: float, success: bool = True, **tags):
    """Record API call latency metric."""
    metrics_collector.record_metric(
        'api_latency',
        latency,
        unit='ms',
        api_name=api_name,
        success=str(success).lower(),
        **tags
    )


def record_cache_operation(operation: str, hit: bool, duration: float = 0.0, **tags):
    """Record cache operation metric."""
    metrics_collector.record_metric(
        'cache_operation',
        1.0,
        operation=operation,
        hit=str(hit).lower(),
        **tags
    )
    
    if duration > 0:
        metrics_collector.record_metric(
            'cache_latency',
            duration,
            unit='ms',
            operation=operation,
            hit=str(hit).lower(),
            **tags
        )


def record_credential_access(service: str, success: bool = True, **tags):
    """Record credential access metric."""
    metrics_collector.record_metric(
        'credential_access',
        1.0,
        service=service,
        success=str(success).lower(),
        **tags
    )


def record_error(component: str, error_type: str, **tags):
    """Record error metric."""
    metrics_collector.record_metric(
        'error_occurrence',
        1.0,
        component=component,
        error_type=error_type,
        **tags
    )


def record_operation_result(operation: str, success: bool = True, duration: float = 0.0, **tags):
    """Record operation result metric."""
    metrics_collector.record_metric(
        'operation_result',
        1.0,
        operation=operation,
        status='success' if success else 'error',
        **tags
    )
    
    if duration > 0:
        metrics_collector.record_metric(
            'operation_latency',
            duration,
            unit='ms',
            operation=operation,
            status='success' if success else 'error',
            **tags
        )