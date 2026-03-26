#!/usr/bin/env python3
"""
Test script to verify tenant functionality.
"""

import os
import sys
import uuid
from datetime import datetime
from sqlmodel import Session, select

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database.db import engine
from src.database.models import Tenant, User


def test_tenant_creation():
    """Test creating a tenant and associating a user with it."""
    # Generate unique identifiers for testing
    unique_id = str(uuid.uuid4())[:8]
    test_subdomain = f"testcompany-{unique_id}"
    test_user_id = f"test_user_{unique_id}"
    
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

        # Verify the relationship
        statement = select(Tenant).where(Tenant.id == user.tenant_id)
        retrieved_tenant = session.exec(statement).first()
        print(f"User's tenant: {retrieved_tenant.name}")

        # Clean up - delete the test data
        session.delete(user)
        session.delete(tenant)
        session.commit()
        print("Cleaned up test data")


if __name__ == "__main__":
    test_tenant_creation()
    print("Tenant functionality test completed successfully!")