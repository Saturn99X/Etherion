#!/usr/bin/env python3
"""
Test script to verify tenant utility functions.
"""

import os
import sys
import uuid
from datetime import datetime
from sqlmodel import Session, select

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database.db import engine
from src.database.models import Tenant, User, Project
from src.database.tenant_utils import (
    get_tenant_from_subdomain,
    get_tenant_aware_records,
    get_tenant_aware_record_by_id,
    create_tenant_aware_record
)


def test_tenant_utilities():
    """Test tenant utility functions."""
    # Generate unique identifiers for testing
    unique_id = str(uuid.uuid4())[:8]
    test_subdomain = f"testcompany-{unique_id}"
    test_user_id = f"test_user_{unique_id}"
    test_project_name = f"Test Project {unique_id}"
    
    with Session(engine) as session:
        # Create a new tenant
        tenant = Tenant(
            tenant_id=Tenant.generate_unique_id(),
            subdomain=test_subdomain,
            name="Test Company",
            admin_email="admin@testcompany.com",
            created_at=datetime.utcnow()
        )
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        print(f"Created tenant: {tenant.name} with ID: {tenant.id}")

        # Test get_tenant_from_subdomain
        retrieved_tenant = get_tenant_from_subdomain(test_subdomain, session)
        assert retrieved_tenant.id == tenant.id, "Failed to retrieve tenant by subdomain"
        print("✓ get_tenant_from_subdomain works correctly")

        # Create a user associated with the tenant
        user = User(
            user_id=test_user_id,
            email="user@testcompany.com",
            name="Test User",
            provider="google",
            tenant_id=tenant.id,
            created_at=datetime.utcnow()
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        print(f"Created user: {user.name} associated with tenant ID: {user.tenant_id}")

        # Test create_tenant_aware_record for a project
        project = Project(
            name=test_project_name,
            user_id=user.id,
            created_at=datetime.utcnow()
        )
        created_project = create_tenant_aware_record(session, tenant.id, project)
        assert created_project.tenant_id == tenant.id, "Failed to create tenant-aware project"
        print("✓ create_tenant_aware_record works correctly")

        # Test get_tenant_aware_records
        projects = get_tenant_aware_records(session, tenant.id, Project)
        assert len(projects) == 1, "Failed to retrieve tenant-aware records"
        assert projects[0].id == created_project.id, "Retrieved incorrect project"
        print("✓ get_tenant_aware_records works correctly")

        # Test get_tenant_aware_record_by_id
        retrieved_project = get_tenant_aware_record_by_id(session, tenant.id, Project, created_project.id)
        assert retrieved_project is not None, "Failed to retrieve tenant-aware record by ID"
        assert retrieved_project.id == created_project.id, "Retrieved incorrect project by ID"
        print("✓ get_tenant_aware_record_by_id works correctly")

        # Test that we can't retrieve records from other tenants
        other_tenant_projects = get_tenant_aware_records(session, 999999, Project)  # Non-existent tenant
        assert len(other_tenant_projects) == 0, "Should not retrieve records from non-existent tenant"
        print("✓ Tenant isolation works correctly")

        # Clean up - delete the test data
        session.delete(created_project)
        session.delete(user)
        session.delete(tenant)
        session.commit()
        print("Cleaned up test data")


if __name__ == "__main__":
    test_tenant_utilities()
    print("All tenant utility tests completed successfully!")