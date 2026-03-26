import pytest
import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.provisioning_api import (
    create_tenant_database_role,
    drop_tenant_database_role,
    check_tenant_role_status
)


@pytest.mark.integration
def test_database_role_creation_mock():
    """Test database role creation with mocked PostgreSQL connection."""
    
    # Mock environment variables
    with patch.dict(os.environ, {
        'DB_SUPERUSER_URI': 'postgresql://superuser:password@localhost/test'
    }):
        
        # Mock asyncpg connection
        with patch('asyncpg.connect') as mock_connect:
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            
            # Mock role existence check (role doesn't exist)
            mock_conn.fetchval.return_value = None
            
            # Mock role creation
            mock_conn.execute.return_value = None
            
            # Run the test
            result = asyncio.run(create_tenant_database_role(123))
            
            # Assertions
            assert result["success"] is True
            assert result["tenant_id"] == 123
            assert result["role_name"] == "tenant_123"
            
            # Verify connection was established
            mock_connect.assert_called_once()
            
            # Verify role creation SQL was executed
            mock_conn.execute.assert_called()


@pytest.mark.integration
def test_database_role_creation_existing_role():
    """Test database role creation when role already exists."""
    
    with patch.dict(os.environ, {
        'DB_SUPERUSER_URI': 'postgresql://superuser:password@localhost/test'
    }):
        
        with patch('asyncpg.connect') as mock_connect:
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            
            # Mock role existence check (role exists)
            mock_conn.fetchval.return_value = 1
            
            # Run the test
            result = asyncio.run(create_tenant_database_role(123))
            
            # Assertions
            assert result["success"] is True
            assert result["action"] == "skipped"
            assert result["role_name"] == "tenant_123"


@pytest.mark.integration
def test_database_role_creation_missing_env():
    """Test database role creation with missing environment variable."""
    
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="DB_SUPERUSER_URI environment variable must be set"):
            asyncio.run(create_tenant_database_role(123))


@pytest.mark.integration
def test_database_role_deletion():
    """Test database role deletion."""
    
    with patch.dict(os.environ, {
        'DB_SUPERUSER_URI': 'postgresql://superuser:password@localhost/test'
    }):
        
        with patch('asyncpg.connect') as mock_connect:
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            
            # Mock role existence check (role exists)
            mock_conn.fetchval.return_value = 1
            
            # Mock role deletion
            mock_conn.execute.return_value = None
            
            # Run the test
            result = asyncio.run(drop_tenant_database_role(123))
            
            # Assertions
            assert result["success"] is True
            assert result["tenant_id"] == 123
            assert result["role_name"] == "tenant_123"
            assert result["action"] == "deleted"


@pytest.mark.integration
def test_database_role_deletion_nonexistent():
    """Test database role deletion when role doesn't exist."""
    
    with patch.dict(os.environ, {
        'DB_SUPERUSER_URI': 'postgresql://superuser:password@localhost/test'
    }):
        
        with patch('asyncpg.connect') as mock_connect:
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            
            # Mock role existence check (role doesn't exist)
            mock_conn.fetchval.return_value = None
            
            # Run the test
            result = asyncio.run(drop_tenant_database_role(123))
            
            # Assertions
            assert result["success"] is True
            assert result["action"] == "skipped"


@pytest.mark.integration
def test_tenant_role_permissions():
    """Test that tenant roles have correct permissions."""
    
    with patch.dict(os.environ, {
        'DB_SUPERUSER_URI': 'postgresql://superuser:password@localhost/test'
    }):
        
        with patch('asyncpg.connect') as mock_connect:
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            
            # Mock role existence check (role doesn't exist)
            mock_conn.fetchval.return_value = None
            
            # Run the test
            result = asyncio.run(create_tenant_database_role(123))
            
            # Verify the role creation SQL includes proper permissions
            calls = mock_conn.execute.call_args_list
            
            # Check that role creation includes proper permissions
            role_creation_calls = [call for call in calls if 'CREATE ROLE' in str(call)]
            assert len(role_creation_calls) > 0
            
            # Check that grants include table permissions
            grant_calls = [call for call in calls if 'GRANT' in str(call)]
            assert len(grant_calls) > 0


@pytest.mark.integration
def test_tenant_role_isolation():
    """Test that tenant roles are properly isolated."""
    
    with patch.dict(os.environ, {
        'DB_SUPERUSER_URI': 'postgresql://superuser:password@localhost/test'
    }):
        
        with patch('asyncpg.connect') as mock_connect:
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            
            # Mock role existence check (role doesn't exist)
            mock_conn.fetchval.return_value = None
            
            # Create roles for different tenants
            result1 = asyncio.run(create_tenant_database_role(123))
            result2 = asyncio.run(create_tenant_database_role(456))
            
            # Assertions
            assert result1["success"] is True
            assert result2["success"] is True
            assert result1["role_name"] == "tenant_123"
            assert result2["role_name"] == "tenant_456"
            assert result1["role_name"] != result2["role_name"]


@pytest.mark.integration
def test_tenant_role_naming_convention():
    """Test that tenant roles follow proper naming convention."""
    
    with patch.dict(os.environ, {
        'DB_SUPERUSER_URI': 'postgresql://superuser:password@localhost/test'
    }):
        
        with patch('asyncpg.connect') as mock_connect:
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            
            # Mock role existence check (role doesn't exist)
            mock_conn.fetchval.return_value = None
            
            # Test various tenant IDs
            test_cases = [1, 123, 999, 1000]
            
            for tenant_id in test_cases:
                result = asyncio.run(create_tenant_database_role(tenant_id))
                
                # Assertions
                assert result["success"] is True
                assert result["role_name"] == f"tenant_{tenant_id}"
                assert result["role_name"].startswith("tenant_")
                assert result["role_name"].replace("tenant_", "").isdigit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
