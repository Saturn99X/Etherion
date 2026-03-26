"""
Core module for Etherion AI Platform.

This module contains core infrastructure components including:
- Celery configuration and task management
- Redis client utilities
- Background task definitions
"""

from .celery import celery_app, get_celery_app, get_task_status, health_check_task
from .redis import RedisClient, get_redis_client, publish_job_status, subscribe_to_job_status

__all__ = [
    "celery_app",
    "get_celery_app",
    "get_task_status",
    "health_check_task",
    "RedisClient",
    "get_redis_client",
    "publish_job_status",
    "subscribe_to_job_status"
]
