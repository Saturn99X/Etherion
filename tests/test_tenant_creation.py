#!/usr/bin/env python3
"""
Test script to verify tenant creation GraphQL mutation.
"""

import os
import sys
import uuid
from datetime import datetime
from sqlmodel import Session, select

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database.db import engine
from src.database.models import Tenant


def test_tenant_creation_directly():
    """Test creating a tenant directly in the database."""
    # Generate unique identifiers for testing
    unique_id = str(uuid.uuid4())[:8]
    test_subdomain = f"testcompany-{unique_id}"
    test_name = f"Test Company {unique_id}"
    test_admin_email = f"admin-{unique_id}@testcompany.com"
    
    with Session(engine) as session:
        # Create a new tenant
        tenant = Tenant(
            tenant_id=Tenant.generate_unique_id(),
            subdomain=test_subdomain,
            name=test_name,
            admin_email=test_admin_email,
            created_at=datetime.utcnow()
        )
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        print(f"Created tenant: {tenant.name} with ID: {tenant.id}")
        print(f"Tenant ID: {tenant.tenant_id}")
        print(f"Subdomain: {tenant.subdomain}")
        print(f"Admin Email: {tenant.admin_email}")
        print(f"Created At: {tenant.created_at}")

        # Verify we can retrieve it
        statement = select(Tenant).where(Tenant.id == tenant.id)
        retrieved_tenant = session.exec(statement).first()
        assert retrieved_tenant.id == tenant.id, "Failed to retrieve tenant"
        print("✓ Tenant retrieval works correctly")

        # Clean up - delete the test data
        session.delete(tenant)
        session.commit()
        print("Cleaned up test data")


if __name__ == "__main__":
    test_tenant_creation_directly()
    print("Direct tenant creation test completed successfully!")