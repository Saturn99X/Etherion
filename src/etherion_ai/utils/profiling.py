# src/etherion_ai/utils/profiling.py
import time
import functools
from typing import Any, Callable, Dict, Optional
import os
import logging

# Try to import Google Cloud Profiler
try:
    from google.cloud import profiler
    PROFILER_AVAILABLE = True
except ImportError:
    PROFILER_AVAILABLE = False
    profiler = None


class PerformanceProfiler:
    """Utility for performance profiling and monitoring."""

    def __init__(self, project_id: Optional[str] = None):
        """Initialize the performance profiler."""
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID")
        self.logger = logging.getLogger(__name__)
        self.profiler_enabled = False

    def initialize_profiler(self) -> None:
        """Initialize Google Cloud Profiler."""
        if not self.project_id:
            self.logger.warning("GCP_PROJECT_ID not set. Profiler not initialized.")
            return

        if not PROFILER_AVAILABLE:
            self.logger.warning("Google Cloud Profiler not available. Profiler not initialized.")
            return

        try:
            # Initialize the profiler
            profiler.start(
                service="etherion-ai",
                service_version=os.environ.get("SERVICE_VERSION", "1.0.0"),
                project_id=self.project_id,
            )
            self.profiler_enabled = True
            self.logger.info("Google Cloud Profiler initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Cloud Profiler: {str(e)}")

    def profile_function(self, func: Callable) -> Callable:
        """Decorator to profile a function's execution time."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.time()
                execution_time = end_time - start_time
                self.logger.info(
                    f"Function {func.__name__} executed in {execution_time:.4f} seconds",
                    extra={
                        "function_name": func.__name__,
                        "execution_time": execution_time,
                        "function_module": func.__module__
                    }
                )
        return wrapper

    def record_latency_metric(self, metric_name: str, latency: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a latency metric."""
        self.logger.info(
            f"Latency metric recorded: {metric_name} = {latency:.4f}s",
            extra={
                "metric_name": metric_name,
                "latency": latency,
                "labels": labels or {}
            }
        )

    def record_counter_metric(self, metric_name: str, value: int, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a counter metric."""
        self.logger.info(
            f"Counter metric recorded: {metric_name} = {value}",
            extra={
                "metric_name": metric_name,
                "value": value,
                "labels": labels or {}
            }
        )


# Global profiler instance
profiler_instance: Optional[PerformanceProfiler] = None


def initialize_performance_profiler(project_id: Optional[str] = None) -> None:
    """Initialize the global performance profiler."""
    global profiler_instance
    profiler_instance = PerformanceProfiler(project_id)
    profiler_instance.initialize_profiler()


def get_performance_profiler() -> Optional[PerformanceProfiler]:
    """Get the global performance profiler."""
    return profiler_instance


def profile_execute_goal(func: Callable) -> Callable:
    """Decorator to profile the executeGoal mutation."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        profiler = get_performance_profiler()
        if profiler:
            # Profile the function execution
            return await profiler.profile_function(func)(*args, **kwargs)
        else:
            # If profiler is not available, just execute the function
            return await func(*args, **kwargs)
    return wrapper


def record_end_to_end_latency(latency: float, labels: Optional[Dict[str, str]] = None) -> None:
    """Record the end-to-end latency of the executeGoal mutation."""
    profiler = get_performance_profiler()
    if profiler:
        profiler.record_latency_metric("execute_goal_end_to_end_latency", latency, labels)
    else:
        logging.info(f"End-to-end latency recorded: {latency:.4f}s", extra={"latency": latency, "labels": labels or {}})