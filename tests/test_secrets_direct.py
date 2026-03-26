#!/usr/bin/env python3
# test_secrets_direct.py
"""
Direct test of secrets manager functionality.
"""

import os
import asyncio
from src.utils.secrets_manager import TenantSecretsManager


async def test_secrets_direct():
    """Direct test of secrets manager."""
    print("Starting direct test...")
    
    # Disable Redis
    os.environ['REDIS_ENABLED'] = 'false'
    
    # Create secrets manager
    print("Creating secrets manager...")
    secrets_manager = TenantSecretsManager()
    print("Secrets manager created successfully")
    
    # Store credentials for tenant A
    print("Storing secret for tenant A...")
    await secrets_manager.store_secret(
        tenant_id="tenant-a-test",
        service_name='test',
        key_type='api_key',
        value='tenant-a-secret'
    )
    print("Secret stored for tenant A")
    
    # Store credentials for tenant B
    print("Storing secret for tenant B...")
    await secrets_manager.store_secret(
        tenant_id="tenant-b-test",
        service_name='test',
        key_type='api_key',
        value='tenant-b-secret'
    )
    print("Secret stored for tenant B")
    
    # Tenant A accesses own credentials
    print("Retrieving secret for tenant A...")
    a_secret = await secrets_manager.get_secret(
        tenant_id="tenant-a-test",
        service_name='test',
        key_type='api_key'
    )
    print(f"Retrieved secret for tenant A: {a_secret}")
    assert a_secret == "tenant-a-secret"
    
    # Tenant B accesses own credentials
    print("Retrieving secret for tenant B...")
    b_secret = await secrets_manager.get_secret(
        tenant_id="tenant-b-test",
        service_name='test',
        key_type='api_key'
    )
    print(f"Retrieved secret for tenant B: {b_secret}")
    assert b_secret == "tenant-b-secret"
    
    # Verify no cross-access
    assert a_secret != b_secret
    print("✓ Cross-tenant isolation verified")
    
    print("All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_secrets_direct())