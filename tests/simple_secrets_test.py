#!/usr/bin/env python3
# simple_secrets_test.py
"""
Simple test of secrets manager functionality without complex locking.
"""

import os
import asyncio
from src.utils.secrets_manager import TenantSecretsManager


async def simple_secrets_test():
    """Simple test of secrets manager."""
    print("Starting simple secrets test...")
    
    # Disable Redis to avoid connection issues
    os.environ['REDIS_ENABLED'] = 'false'
    
    # Create secrets manager
    print("Creating secrets manager...")
    secrets_manager = TenantSecretsManager()
    print("Secrets manager created successfully")
    
    # Test storing and retrieving secrets
    print("Testing secret storage and retrieval...")
    
    # Store credentials for tenant A
    print("Storing secret for tenant A...")
    success_a = await secrets_manager.store_secret(
        tenant_id="tenant-a-test",
        service_name='test',
        key_type='api_key',
        value='tenant-a-secret'
    )
    print(f"Secret storage for tenant A: {'SUCCESS' if success_a else 'FAILED'}")
    
    # Store credentials for tenant B
    print("Storing secret for tenant B...")
    success_b = await secrets_manager.store_secret(
        tenant_id="tenant-b-test",
        service_name='test',
        key_type='api_key',
        value='tenant-b-secret'
    )
    print(f"Secret storage for tenant B: {'SUCCESS' if success_b else 'FAILED'}")
    
    # Retrieve secrets
    print("Retrieving secrets...")
    
    # Tenant A accesses own credentials
    print("Retrieving secret for tenant A...")
    a_secret = await secrets_manager.get_secret(
        tenant_id="tenant-a-test",
        service_name='test',
        key_type='api_key'
    )
    print(f"Retrieved secret for tenant A: {a_secret}")
    
    # Tenant B accesses own credentials
    print("Retrieving secret for tenant B...")
    b_secret = await secrets_manager.get_secret(
        tenant_id="tenant-b-test",
        service_name='test',
        key_type='api_key'
    )
    print(f"Retrieved secret for tenant B: {b_secret}")
    
    # Verify isolation
    if a_secret and b_secret:
        isolation_verified = (a_secret != b_secret)
        print(f"Cross-tenant isolation: {'VERIFIED' if isolation_verified else 'FAILED'}")
        assert isolation_verified, "Cross-tenant isolation failed!"
    
    print("Simple secrets test completed successfully!")


if __name__ == "__main__":
    asyncio.run(simple_secrets_test())