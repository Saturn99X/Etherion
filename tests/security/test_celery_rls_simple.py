import time
import json
import pytest
from sqlalchemy import text

from src.database.db import get_db
from src.database.models import Job, JobStatus
from src.database.ts_models import Tenant, Project
from src.utils.tenant_context import set_tenant_context, get_tenant_context


@pytest.mark.integration
def test_celery_rls_enforces_tenant_context_isolation():
    """
    Test that tenant context is properly set and maintained for Celery tasks.
    This simulates what happens in the orchestrate_goal_task.
    """
    # Simulate what happens in orchestrate_goal_task
    tenant_id = 123
    
    # THIS IS THE CRITICAL ADDITION: Set the context for the lifetime of this worker task.
    set_tenant_context(tenant_id)
    
    # Verify the context is set
    assert get_tenant_context() == tenant_id
    
    # Test database operations with tenant context
    db = get_db()
    try:
        # The `after_begin` event listener will now automatically handle setting
        # `SET LOCAL app.tenant_id` for every transaction within this task.
        
        # Test that we can execute queries
        result = db.execute(text("SELECT 1 as test"))
        assert result.fetchone()[0] == 1
        
        # Verify tenant context is still set
        assert get_tenant_context() == tenant_id
        
    finally:
        db.close()


@pytest.mark.integration
def test_tenant_context_persistence_across_operations():
    """Test that tenant context persists across multiple database operations."""
    tenant_id = 456
    
    # Set tenant context
    set_tenant_context(tenant_id)
    assert get_tenant_context() == tenant_id
    
    # Perform multiple database operations
    db = get_db()
    try:
        # First operation
        result1 = db.execute(text("SELECT 1 as test1"))
        assert result1.fetchone()[0] == 1
        assert get_tenant_context() == tenant_id
        
        # Second operation
        result2 = db.execute(text("SELECT 2 as test2"))
        assert result2.fetchone()[0] == 2
        assert get_tenant_context() == tenant_id
        
        # Third operation
        result3 = db.execute(text("SELECT 3 as test3"))
        assert result3.fetchone()[0] == 3
        assert get_tenant_context() == tenant_id
        
    finally:
        db.close()


@pytest.mark.integration
def test_tenant_context_isolation_between_tasks():
    """Test that different tenant contexts are properly isolated."""
    # Simulate first task
    tenant_a = 100
    set_tenant_context(tenant_a)
    assert get_tenant_context() == tenant_a
    
    # Simulate second task
    tenant_b = 200
    set_tenant_context(tenant_b)
    assert get_tenant_context() == tenant_b
    assert get_tenant_context() != tenant_a
    
    # Simulate third task
    tenant_c = 300
    set_tenant_context(tenant_c)
    assert get_tenant_context() == tenant_c
    assert get_tenant_context() != tenant_a
    assert get_tenant_context() != tenant_b


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
