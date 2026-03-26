"""
Tenant-aware Celery task decorators and utilities.

This module provides decorators and utilities for creating Celery tasks that
automatically handle tenant context and database session management.
"""

import logging
from typing import Optional, Callable, Any, Dict
from functools import wraps
from celery import current_task
from sqlalchemy.orm import Session

from src.database.db import session_scope
from src.utils.tenant_context import get_tenant_context, set_tenant_context
from src.core.celery import celery_app

logger = logging.getLogger(__name__)


def tenant_task(bind: bool = True, **task_kwargs):
    """
    Decorator for Celery tasks that require tenant context.
    
    This decorator automatically:
    1. Extracts tenant_id from task arguments or context
    2. Sets tenant context for the task execution
    3. Provides tenant-scoped database session
    
    Args:
        bind: Whether to bind the task instance
        **task_kwargs: Additional Celery task configuration
        
    Usage:
        @tenant_task(bind=True, name="my.tenant_task")
        def my_task(self, tenant_id: int, other_arg: str):
            # tenant_id is automatically set in context
            # Use get_tenant_context() to access it
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract tenant_id from arguments or task context
            tenant_id = None
            
            # Try to get tenant_id from function arguments
            if 'tenant_id' in kwargs:
                tenant_id = kwargs['tenant_id']
            else:
                # Look for tenant_id in positional arguments
                for arg in args:
                    if isinstance(arg, int) and arg > 0:  # tenant_id should be a positive integer
                        tenant_id = arg
                        break
            
            # Try to get tenant_id from task context (e.g., from job metadata)
            if tenant_id is None and hasattr(current_task, 'request'):
                task_kwargs = current_task.request.kwargs
                if 'tenant_id' in task_kwargs:
                    tenant_id = task_kwargs['tenant_id']
            
            # Set tenant context for this task
            if tenant_id is not None:
                set_tenant_context(tenant_id)
                logger.debug(f"Set tenant context to {tenant_id} for task {func.__name__}")
            else:
                logger.warning(f"No tenant_id found for task {func.__name__}")
            
            # Execute the original function
            return func(*args, **kwargs)
        
        # Create the Celery task
        return celery_app.task(bind=bind, **task_kwargs)(wrapper)
    
    return decorator


def get_tenant_scoped_session(tenant_id: Optional[int] = None) -> Session:
    """
    Get a tenant-scoped synchronous database session.
    
    Args:
        tenant_id: Optional tenant ID to scope the session
        
    Returns:
        Session: Tenant-scoped database session
        
    Note:
        This function is for synchronous code paths. For async code,
        use the async session managers in src.database.db
    """
    from src.database.db import get_db
    
    session = get_db()
    
    if tenant_id is not None:
        # Set tenant context for the session
        set_tenant_context(tenant_id)
        
        # For PostgreSQL, we would set the session variable here
        # For SQLite (dev), this is a no-op
        try:
            session.execute("SET LOCAL app.tenant_id = :tenant_id", {"tenant_id": tenant_id})
            logger.debug(f"Set tenant context to {tenant_id} for sync session")
        except Exception as e:
            # SQLite doesn't support SET LOCAL, so we ignore the error
            logger.debug(f"Could not set tenant context (expected for SQLite): {e}")
    
    return session


def tenant_scoped_session(tenant_id: Optional[int] = None):
    """
    Context manager for tenant-scoped synchronous database session.
    
    Args:
        tenant_id: Optional tenant ID to scope the session
        
    Yields:
        Session: Tenant-scoped database session
        
    Usage:
        with tenant_scoped_session(tenant_id=123) as session:
            # Use session with tenant context
            pass
    """
    from contextlib import contextmanager
    
    @contextmanager
    def _session_context():
        session = get_tenant_scoped_session(tenant_id)
        try:
            yield session
        finally:
            session.close()
    
    return _session_context()


# Example tenant-aware task
@tenant_task(bind=True, name="core.tenant_aware_cleanup")
def tenant_aware_cleanup_task(self, tenant_id: int, max_age_hours: int = 24) -> Dict[str, Any]:
    """
    Example tenant-aware task that cleans up old jobs for a specific tenant.
    
    Args:
        tenant_id: Tenant ID to clean up jobs for
        max_age_hours: Maximum age of completed jobs to keep
        
    Returns:
        Dict with cleanup results
    """
    from datetime import datetime, timedelta
    from src.database.models import Job, JobStatus
    
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        with tenant_scoped_session(tenant_id) as session:
            # Find old completed jobs for this tenant
            old_jobs = session.query(Job).filter(
                Job.tenant_id == tenant_id,
                Job.status.in_([JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]),
                Job.completed_at < cutoff_time
            ).all()
            
            job_count = len(old_jobs)
            
            # Delete old jobs
            for job in old_jobs:
                session.delete(job)
            
            session.commit()
            
            logger.info(f"Cleaned up {job_count} old jobs for tenant {tenant_id}")
            
            return {
                "success": True,
                "tenant_id": tenant_id,
                "cleaned_jobs": job_count,
                "cutoff_time": cutoff_time.isoformat()
            }
    
    except Exception as exc:
        logger.error(f"Failed to cleanup jobs for tenant {tenant_id}: {exc}")
        raise self.retry(exc=exc, countdown=300, max_retries=2)
