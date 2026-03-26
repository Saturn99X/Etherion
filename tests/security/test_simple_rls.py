import pytest
from sqlalchemy import text

from src.database.db import get_db
from src.database.models import Job, JobStatus
from src.database.ts_models import Tenant, Project
from src.utils.tenant_context import set_tenant_context, get_tenant_context


@pytest.mark.integration
def test_tenant_context_variable_works():
    """Test that the tenant context variable works correctly."""
    # Test setting and getting tenant context
    set_tenant_context(123)
    assert get_tenant_context() == 123
    
    # Test clearing tenant context
    set_tenant_context(None)
    assert get_tenant_context() is None
    
    # Test setting different tenant
    set_tenant_context(456)
    assert get_tenant_context() == 456


@pytest.mark.integration
def test_database_connection_with_tenant_context():
    """Test that database connection works with tenant context."""
    # Set tenant context
    set_tenant_context(123)
    
    # Get database connection
    db = get_db()
    try:
        # Test that we can execute a simple query
        result = db.execute(text("SELECT 1 as test"))
        assert result.fetchone()[0] == 1
        
        # Test that tenant context is available
        current_tenant = get_tenant_context()
        assert current_tenant == 123
        
    finally:
        db.close()


@pytest.mark.integration
def test_tenant_isolation_basic():
    """Test basic tenant isolation functionality."""
    # Create two different tenant contexts
    set_tenant_context(100)
    tenant_100 = get_tenant_context()
    
    set_tenant_context(200)
    tenant_200 = get_tenant_context()
    
    # Verify they are different
    assert tenant_100 != tenant_200
    assert tenant_100 == 100
    assert tenant_200 == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
