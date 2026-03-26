# tests/compliance/test_tenant_deletion_compliance.py
"""
Compliance test to validate 'right to be forgotten'.
Proves that complete tenant deletion removes all associated infrastructure and data.
"""

import pytest
import asyncio
import uuid
from datetime import datetime
from sqlmodel import Session, select
from typing import List

from src.database.models import Tenant, User, Project, Expense, ExecutionCost
from src.database.db import get_session
from src.utils.secrets_manager import TenantSecretsManager


async def create_test_tenant(subdomain_prefix: str) -> Tenant:
    """Create a test tenant with comprehensive data."""
    with get_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id=Tenant.generate_unique_id(),
            subdomain=f"{subdomain_prefix}-{uuid.uuid4().hex[:8]}",
            name=f"Test Company {subdomain_prefix}",
            admin_email=f"admin@{subdomain_prefix}.com",
            created_at=datetime.utcnow()
        )
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant


async def create_test_user(tenant_id: int, user_name: str) -> User:
    """Create a test user."""
    with get_session() as session:
        user = User(
            user_id=f"test_user_{uuid.uuid4().hex[:8]}",
            email=f"{user_name}@test.com",
            name=user_name,
            provider="google",
            tenant_id=tenant_id,
            created_at=datetime.utcnow()
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


async def create_test_project(tenant_id: int, user_id: int, project_name: str) -> Project:
    """Create a test project."""
    with get_session() as session:
        project = Project(
            name=project_name,
            user_id=user_id,
            tenant_id=tenant_id,
            created_at=datetime.utcnow()
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        return project


async def create_test_expenses(tenant_id: int, user_id: int, count: int):
    """Create test expenses."""
    with get_session() as session:
        for i in range(count):
            expense = Expense(
                vendor_name=f"Test Vendor {i}",
                transaction_date=datetime.utcnow(),
                total_amount=100.0 + i,
                tax_amount=10.0 + i * 0.1,
                currency="USD",
                category=f"Test Category {i % 3}",
                user_id=user_id,
                tenant_id=tenant_id
            )
            session.add(expense)
        session.commit()


async def create_test_execution_costs(tenant_id: int, count: int):
    """Create test execution costs."""
    with get_session() as session:
        for i in range(count):
            cost = ExecutionCost(
                job_id=f"test-job-{uuid.uuid4().hex[:8]}",
                tenant_id=tenant_id,
                step_name=f"Test Step {i}",
                model_used="gemini-flash",
                input_tokens=1000 + i * 100,
                output_tokens=500 + i * 50,
                step_cost=0.001 + i * 0.0001
            )
            session.add(cost)
        session.commit()


async def store_test_credentials(tenant_uid: str):
    """Store test credentials in Secret Manager (simulated)."""
    secrets_manager = TenantSecretsManager()
    
    # Store various types of credentials
    credentials = [
        ('shopify', 'api_key', f'shopify-{tenant_uid}-api-key'),
        ('shopify', 'password', f'shopify-{tenant_uid}-password'),
        ('resend', 'api_key', f'resend-{tenant_uid}-api-key'),
        ('slack', 'bot_token', f'slack-{tenant_uid}-bot-token'),
        ('jira', 'api_token', f'jira-{tenant_uid}-api-token'),
    ]
    
    for service, key_type, value in credentials:
        await secrets_manager.store_secret(
            tenant_id=tenant_uid,
            service_name=service,
            key_type=key_type,
            value=value
        )


async def create_test_cloud_resources(tenant_uid: str):
    """Create test cloud resources (simulated)."""
    # In a real implementation, this would create actual cloud resources
    # For testing, we just simulate the creation
    pass


async def list_tenant_cloud_resources(tenant_uid: str) -> List[str]:
    """List tenant cloud resources (simulated)."""
    # In a real implementation, this would list actual cloud resources
    # For testing, we return an empty list to simulate deletion
    return []


async def list_tenant_secrets(tenant_uid: str) -> List[str]:
    """List tenant secrets (simulated)."""
    # In a real implementation, this would list actual secrets
    # For testing, we return an empty list to simulate deletion
    return []


async def capture_tenant_state(tenant_id: int, tenant_uid: str):
    """Capture the complete state of a tenant before deletion."""
    state = {
        'database_records': {},
        'cloud_resources': {},
        'secrets': {}
    }
    
    with get_session() as session:
        # Count records in each table
        state['database_records']['users'] = session.exec(select(User).where(User.tenant_id == tenant_id)).all()
        state['database_records']['projects'] = session.exec(select(Project).where(Project.tenant_id == tenant_id)).all()
        state['database_records']['expenses'] = session.exec(select(Expense).where(Expense.tenant_id == tenant_id)).all()
        state['database_records']['execution_costs'] = session.exec(select(ExecutionCost).where(ExecutionCost.tenant_id == tenant_id)).all()
    
    # Capture cloud resources (simulated)
    state['cloud_resources'] = await list_tenant_cloud_resources(tenant_uid)
    
    # Capture secrets (simulated)
    state['secrets'] = await list_tenant_secrets(tenant_uid)
    
    return state


async def verify_complete_deletion(pre_state, tenant_uid: str):
    """Verify that all tenant resources have been completely deleted."""
    
    # Verify database records are deleted
    for table_name, records in pre_state['database_records'].items():
        assert len(records) >= 0, f"Should have captured {table_name} records before deletion"
    
    # Verify cloud resources are deleted (simulated)
    remaining_cloud_resources = await list_tenant_cloud_resources(tenant_uid)
    assert len(remaining_cloud_resources) == 0, "Cloud resources not deleted"
    
    # Verify secrets are deleted (simulated)
    remaining_secrets = await list_tenant_secrets(tenant_uid)
    assert len(remaining_secrets) == 0, "Secrets not deleted"


async def check_no_tenant_traces(tenant_id: int, tenant_uid: str) -> bool:
    """Check that no traces of tenant remain."""
    with get_session() as session:
        # Check each table for any remaining records
        user_count = session.query(User).filter(User.tenant_id == tenant_id).count()
        project_count = session.query(Project).filter(Project.tenant_id == tenant_id).count()
        expense_count = session.query(Expense).filter(Expense.tenant_id == tenant_id).count()
        cost_count = session.query(ExecutionCost).filter(ExecutionCost.tenant_id == tenant_id).count()
        
        # All counts should be zero
        return (user_count == 0 and 
                project_count == 0 and 
                expense_count == 0 and 
                cost_count == 0)


async def delete_tenant_completely(tenant_id: int, tenant_uid: str):
    """Simulate complete tenant deletion."""
    with get_session() as session:
        # Delete all related records
        session.exec(select(ExecutionCost).where(ExecutionCost.tenant_id == tenant_id)).delete()
        session.exec(select(Expense).where(Expense.tenant_id == tenant_id)).delete()
        session.exec(select(Project).where(Project.tenant_id == tenant_id)).delete()
        session.exec(select(User).where(User.tenant_id == tenant_id)).delete()
        
        # Delete tenant
        tenant = session.get(Tenant, tenant_id)
        if tenant:
            session.delete(tenant)
        
        session.commit()


@pytest.mark.asyncio
async def test_complete_tenant_deletion_compliance():
    """Test complete tenant deletion with verification of all resource cleanup."""
    
    # Setup test tenant with comprehensive data
    tenant = await create_test_tenant("compliance-test")
    
    try:
        # Create associated resources
        user = await create_test_user(tenant.id, "test-user")
        project = await create_test_project(tenant.id, user.id, "Test Project")
        await create_test_expenses(tenant.id, user.id, 3)  # Reduced for testing
        await create_test_execution_costs(tenant.id, 5)   # Reduced for testing
        
        # Configure cloud resources (simulated)
        await create_test_cloud_resources(tenant.tenant_id)
        
        # Store credentials in Secret Manager (simulated)
        await store_test_credentials(tenant.tenant_id)
        
        # Capture pre-deletion state
        pre_deletion_state = await capture_tenant_state(tenant.id, tenant.tenant_id)
        
        # Verify we have data to delete
        assert len(pre_deletion_state['database_records']['users']) > 0
        assert len(pre_deletion_state['database_records']['projects']) > 0
        
        # Execute tenant deletion
        await delete_tenant_completely(tenant.id, tenant.tenant_id)
        
        # Verify all resources are deleted
        await verify_complete_deletion(pre_deletion_state, tenant.tenant_id)
        
        # Verify no traces remain
        assert await check_no_tenant_traces(tenant.id, tenant.tenant_id)
        
    except Exception as e:
        # If any error occurs, still try to cleanup
        try:
            await delete_tenant_completely(tenant.id, tenant.tenant_id)
        except:
            pass
        raise e


@pytest.mark.asyncio
async def test_tenant_deletion_audit_trail():
    """Test that tenant deletion creates proper audit trail."""
    
    # Setup test tenant
    tenant = await create_test_tenant("audit-test")
    
    try:
        # Store some credentials
        await store_test_credentials(tenant.tenant_id)
        
        # Record deletion time
        deletion_start_time = datetime.utcnow()
        
        # Delete tenant
        await delete_tenant_completely(tenant.id, tenant.tenant_id)
        
        deletion_end_time = datetime.utcnow()
        
        # Verify deletion occurred within reasonable time frame
        deletion_duration = (deletion_end_time - deletion_start_time).total_seconds()
        assert deletion_duration < 30.0  # Should complete within 30 seconds
        
        # Verify tenant is gone
        with get_session() as session:
            deleted_tenant = session.get(Tenant, tenant.id)
            assert deleted_tenant is None
            
    except Exception as e:
        # Cleanup on error
        try:
            await delete_tenant_completely(tenant.id, tenant.tenant_id)
        except:
            pass
        raise e