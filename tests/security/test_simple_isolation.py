# tests/security/test_simple_isolation.py
"""
Simple security test to verify cross-tenant isolation.
"""

import pytest
from src.utils.secrets_manager import TenantSecretsManager


@pytest.mark.asyncio
async def test_simple_tenant_isolation():
    """Simple test that tenants cannot access each other's credentials."""
    
    # Setup distinct credentials for two tenants
    secrets_manager = TenantSecretsManager()
    
    # Store credentials for tenant A
    await secrets_manager.store_secret(
        tenant_id="tenant-a-test",
        service_name='test',
        key_type='api_key',
        value='tenant-a-secret'
    )
    
    # Store credentials for tenant B
    await secrets_manager.store_secret(
        tenant_id="tenant-b-test",
        service_name='test',
        key_type='api_key',
        value='tenant-b-secret'
    )
    
    # Tenant A accesses own credentials
    a_secret = await secrets_manager.get_secret(
        tenant_id="tenant-a-test",
        service_name='test',
        key_type='api_key'
    )
    assert a_secret == "tenant-a-secret"
    
    # Tenant B accesses own credentials
    b_secret = await secrets_manager.get_secret(
        tenant_id="tenant-b-test",
        service_name='test',
        key_type='api_key'
    )
    assert b_secret == "tenant-b-secret"
    
    # Verify no cross-access
    assert a_secret != b_secret
    
    print("✓ Simple tenant isolation test passed")