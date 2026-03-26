"""
Unit tests for Salesforce MCP Tool.

Tests all Salesforce operations with mocked Salesforce API responses.
Uses VCR.py compatible fixtures for integration testing.

Author: Etherion AI Platform Team
Date: January 15, 2025
Version: 1.0.0
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.tools.mcp.mcp_salesforce import MCPSalesforceTool, SalesforceCredentials
from src.tools.mcp.base_mcp_tool import (
    MCPToolResult,
    InvalidCredentialsError,
    RateLimitError,
    ValidationError,
    NetworkError,
    QuotaExceededError
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def salesforce_tool():
    """Create Salesforce MCP tool instance."""
    return MCPSalesforceTool()


@pytest.fixture
def mock_credentials():
    """Create mock Salesforce credentials."""
    return SalesforceCredentials(
        access_token="00D50000000IZ3Z!...",
        refresh_token="5Aep861TSESvWeug_xvFHRBTTbf...",
        instance_url="https://na50.salesforce.com",
        id="https://login.salesforce.com/id/00D.../005...",
        token_type="Bearer",
        issued_at="1642012345678",
        signature="abc123...",
        client_id="3MVG9...",
        client_secret="ABC123..."
    )


@pytest.fixture
def mock_salesforce_client():
    """Create mock Salesforce client."""
    client = MagicMock()
    
    # Mock query results
    client.query.return_value = {
        'records': [
            {'Id': '001000000000001', 'Name': 'Test Account 1'},
            {'Id': '001000000000002', 'Name': 'Test Account 2'}
        ],
        'totalSize': 2,
        'done': True
    }
    
    client.query_all.return_value = {
        'records': [
            {'Id': '001000000000001', 'Name': 'Test Account 1', 'IsDeleted': False},
            {'Id': '001000000000002', 'Name': 'Test Account 2', 'IsDeleted': True}
        ],
        'totalSize': 2,
        'done': True
    }
    
    # Mock SObject operations
    mock_account = MagicMock()
    mock_account.get.return_value = {'Id': '001000000000001', 'Name': 'Test Account'}
    mock_account.create.return_value = {'id': '001000000000003', 'success': True}
    mock_account.update.return_value = {'id': '001000000000001', 'success': True}
    mock_account.delete.return_value = {'id': '001000000000001', 'success': True}
    mock_account.upsert.return_value = {'id': '001000000000001', 'success': True, 'created': False}
    mock_account.describe.return_value = {
        'name': 'Account',
        'label': 'Account',
        'fields': [
            {'name': 'Id', 'type': 'id', 'label': 'Account ID'},
            {'name': 'Name', 'type': 'string', 'label': 'Account Name'}
        ]
    }
    mock_account.metadata.return_value = {
        'fullName': 'Account',
        'label': 'Account',
        'pluralLabel': 'Accounts'
    }
    mock_account.bulk_create.return_value = [
        {'id': '001000000000003', 'success': True},
        {'id': '001000000000004', 'success': True}
    ]
    mock_account.bulk_update.return_value = [
        {'id': '001000000000001', 'success': True},
        {'id': '001000000000002', 'success': True}
    ]
    mock_account.bulk_delete.return_value = [
        {'id': '001000000000001', 'success': True},
        {'id': '001000000000002', 'success': True}
    ]
    
    client.Account = mock_account
    
    # Mock describe
    client.describe.return_value = {
        'sobjects': [
            {'name': 'Account', 'label': 'Account'},
            {'name': 'Contact', 'label': 'Contact'},
            {'name': 'Lead', 'label': 'Lead'}
        ]
    }
    
    return client


# ============================================================================
# CREDENTIALS TESTS
# ============================================================================


class TestSalesforceCredentials:
    """Test Salesforce credentials handling."""
    
    def test_credentials_creation(self):
        """Test credentials creation from dict."""
        data = {
            "access_token": "00D50000000IZ3Z!...",
            "refresh_token": "5Aep861TSESvWeug_xvFHRBTTbf...",
            "instance_url": "https://na50.salesforce.com",
            "id": "https://login.salesforce.com/id/00D.../005...",
            "token_type": "Bearer",
            "issued_at": "1642012345678",
            "signature": "abc123..."
        }
        
        creds = SalesforceCredentials.from_dict(data)
        assert creds.access_token == "00D50000000IZ3Z!..."
        assert creds.refresh_token == "5Aep861TSESvWeug_xvFHRBTTbf..."
        assert creds.instance_url == "https://na50.salesforce.com"
    
    def test_credentials_needs_refresh(self, mock_credentials):
        """Test token refresh detection."""
        # Token issued 1.5 hours ago - should need refresh
        mock_credentials.issued_at = str(int((datetime.utcnow() - timedelta(hours=1.5)).timestamp() * 1000))
        assert mock_credentials.needs_refresh() is True
        
        # Token issued 30 minutes ago - should not need refresh
        mock_credentials.issued_at = str(int((datetime.utcnow() - timedelta(minutes=30)).timestamp() * 1000))
        assert mock_credentials.needs_refresh() is False
    
    def test_credentials_is_expired(self, mock_credentials):
        """Test token expiration detection."""
        # Expired token (2.5 hours old)
        mock_credentials.issued_at = str(int((datetime.utcnow() - timedelta(hours=2.5)).timestamp() * 1000))
        assert mock_credentials.is_expired() is True
        
        # Valid token (1 hour old)
        mock_credentials.issued_at = str(int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000))
        assert mock_credentials.is_expired() is False
    
    def test_credentials_to_dict(self, mock_credentials):
        """Test credentials serialization."""
        data = mock_credentials.to_dict()
        assert data["access_token"] == mock_credentials.access_token
        assert data["refresh_token"] == mock_credentials.refresh_token
        assert data["instance_url"] == mock_credentials.instance_url


# ============================================================================
# SALESFORCE TOOL TESTS
# ============================================================================


class TestMCPSalesforceTool:
    """Test Salesforce MCP tool operations."""
    
    @pytest.mark.asyncio
    async def test_query_soql(self, salesforce_tool, mock_salesforce_client):
        """Test SOQL query execution."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_query_soql(
                mock_salesforce_client,
                {'query': 'SELECT Id, Name FROM Account LIMIT 10'}
            )
            
            assert result.success is True
            assert 'records' in result.data
            assert len(result.data['records']) == 2
            assert result.data['total_size'] == 2
            assert result.data['done'] is True
    
    @pytest.mark.asyncio
    async def test_query_all_soql(self, salesforce_tool, mock_salesforce_client):
        """Test SOQL query_all execution."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_query_all_soql(
                mock_salesforce_client,
                {'query': 'SELECT Id, Name FROM Account LIMIT 10'}
            )
            
            assert result.success is True
            assert 'records' in result.data
            assert len(result.data['records']) == 2
            assert result.data['total_size'] == 2
    
    @pytest.mark.asyncio
    async def test_get_record(self, salesforce_tool, mock_salesforce_client):
        """Test getting single record."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_get_record(
                mock_salesforce_client,
                {
                    'sobject': 'Account',
                    'record_id': '001000000000001',
                    'fields': ['Id', 'Name']
                }
            )
            
            assert result.success is True
            assert 'record' in result.data
            assert result.data['record']['Id'] == '001000000000001'
    
    @pytest.mark.asyncio
    async def test_create_record(self, salesforce_tool, mock_salesforce_client):
        """Test creating new record."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_create_record(
                mock_salesforce_client,
                {
                    'sobject': 'Account',
                    'data': {'Name': 'New Account', 'Type': 'Customer'}
                }
            )
            
            assert result.success is True
            assert 'id' in result.data
            assert result.data['id'] == '001000000000003'
            assert result.data['success'] is True
    
    @pytest.mark.asyncio
    async def test_update_record(self, salesforce_tool, mock_salesforce_client):
        """Test updating existing record."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_update_record(
                mock_salesforce_client,
                {
                    'sobject': 'Account',
                    'record_id': '001000000000001',
                    'data': {'Name': 'Updated Account'}
                }
            )
            
            assert result.success is True
            assert 'id' in result.data
            assert result.data['id'] == '001000000000001'
            assert result.data['success'] is True
    
    @pytest.mark.asyncio
    async def test_delete_record(self, salesforce_tool, mock_salesforce_client):
        """Test deleting record."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_delete_record(
                mock_salesforce_client,
                {
                    'sobject': 'Account',
                    'record_id': '001000000000001'
                }
            )
            
            assert result.success is True
            assert 'id' in result.data
            assert result.data['id'] == '001000000000001'
            assert result.data['success'] is True
    
    @pytest.mark.asyncio
    async def test_upsert_record(self, salesforce_tool, mock_salesforce_client):
        """Test upserting record."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_upsert_record(
                mock_salesforce_client,
                {
                    'sobject': 'Account',
                    'external_id_field': 'External_Id__c',
                    'external_id_value': 'EXT123',
                    'data': {'Name': 'Upserted Account'}
                }
            )
            
            assert result.success is True
            assert 'id' in result.data
            assert result.data['id'] == '001000000000001'
            assert result.data['success'] is True
            assert result.data['created'] is False
    
    @pytest.mark.asyncio
    async def test_describe_sobject(self, salesforce_tool, mock_salesforce_client):
        """Test describing SObject."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_describe_sobject(
                mock_salesforce_client,
                {'sobject': 'Account'}
            )
            
            assert result.success is True
            assert 'describe' in result.data
            assert result.data['describe']['name'] == 'Account'
            assert result.data['describe']['label'] == 'Account'
    
    @pytest.mark.asyncio
    async def test_get_sobject_list(self, salesforce_tool, mock_salesforce_client):
        """Test getting SObject list."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_get_sobject_list(
                mock_salesforce_client,
                {}
            )
            
            assert result.success is True
            assert 'sobjects' in result.data
            assert len(result.data['sobjects']) == 3
    
    @pytest.mark.asyncio
    async def test_get_sobject_metadata(self, salesforce_tool, mock_salesforce_client):
        """Test getting SObject metadata."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_get_sobject_metadata(
                mock_salesforce_client,
                {'sobject': 'Account'}
            )
            
            assert result.success is True
            assert 'metadata' in result.data
            assert result.data['metadata']['fullName'] == 'Account'
    
    @pytest.mark.asyncio
    async def test_bulk_create(self, salesforce_tool, mock_salesforce_client):
        """Test bulk creating records."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_bulk_create(
                mock_salesforce_client,
                {
                    'sobject': 'Account',
                    'records': [
                        {'Name': 'Bulk Account 1'},
                        {'Name': 'Bulk Account 2'}
                    ]
                }
            )
            
            assert result.success is True
            assert 'results' in result.data
            assert len(result.data['results']) == 2
    
    @pytest.mark.asyncio
    async def test_bulk_update(self, salesforce_tool, mock_salesforce_client):
        """Test bulk updating records."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_bulk_update(
                mock_salesforce_client,
                {
                    'sobject': 'Account',
                    'records': [
                        {'Id': '001000000000001', 'Name': 'Updated 1'},
                        {'Id': '001000000000002', 'Name': 'Updated 2'}
                    ]
                }
            )
            
            assert result.success is True
            assert 'results' in result.data
            assert len(result.data['results']) == 2
    
    @pytest.mark.asyncio
    async def test_bulk_delete(self, salesforce_tool, mock_salesforce_client):
        """Test bulk deleting records."""
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_bulk_delete(
                mock_salesforce_client,
                {
                    'sobject': 'Account',
                    'record_ids': ['001000000000001', '001000000000002']
                }
            )
            
            assert result.success is True
            assert 'results' in result.data
            assert len(result.data['results']) == 2
    
    @pytest.mark.asyncio
    async def test_get_user_info(self, salesforce_tool, mock_salesforce_client):
        """Test getting user information."""
        # Mock user query
        mock_salesforce_client.query.side_effect = [
            {'records': [{'Id': '005000000000001'}]},  # First query for user ID
            {'records': [{'Id': '005000000000001', 'Name': 'Test User', 'Email': 'test@example.com'}]}  # User info
        ]
        
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_get_user_info(
                mock_salesforce_client,
                {}
            )
            
            assert result.success is True
            assert 'user' in result.data
            assert result.data['user']['Name'] == 'Test User'
    
    @pytest.mark.asyncio
    async def test_get_org_info(self, salesforce_tool, mock_salesforce_client):
        """Test getting organization information."""
        # Mock org query
        mock_salesforce_client.query.return_value = {
            'records': [{'Id': '00D000000000001', 'Name': 'Test Org', 'OrganizationType': 'Developer Edition'}]
        }
        
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            result = await salesforce_tool._handle_get_org_info(
                mock_salesforce_client,
                {}
            )
            
            assert result.success is True
            assert 'organization' in result.data
            assert result.data['organization']['Name'] == 'Test Org'


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestSalesforceErrorHandling:
    """Test Salesforce error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_authentication_failed_error(self, salesforce_tool, mock_salesforce_client):
        """Test authentication failed error handling."""
        from simple_salesforce.exceptions import SalesforceAuthenticationFailed
        
        error = SalesforceAuthenticationFailed("Invalid session ID")
        mock_salesforce_client.query.side_effect = error
        
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            with pytest.raises(InvalidCredentialsError):
                await salesforce_tool._handle_query_soql(mock_salesforce_client, {'query': 'SELECT Id FROM Account'})
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, salesforce_tool, mock_salesforce_client):
        """Test rate limit error handling."""
        from simple_salesforce.exceptions import SalesforceError
        
        error = SalesforceError("RATE_LIMIT_EXCEEDED")
        mock_salesforce_client.query.side_effect = error
        
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            with pytest.raises(RateLimitError):
                await salesforce_tool._handle_query_soql(mock_salesforce_client, {'query': 'SELECT Id FROM Account'})
    
    @pytest.mark.asyncio
    async def test_quota_exceeded_error(self, salesforce_tool, mock_salesforce_client):
        """Test quota exceeded error handling."""
        from simple_salesforce.exceptions import SalesforceError
        
        error = SalesforceError("QUOTA_EXCEEDED")
        mock_salesforce_client.query.side_effect = error
        
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            with pytest.raises(QuotaExceededError):
                await salesforce_tool._handle_query_soql(mock_salesforce_client, {'query': 'SELECT Id FROM Account'})
    
    @pytest.mark.asyncio
    async def test_invalid_session_error(self, salesforce_tool, mock_salesforce_client):
        """Test invalid session error handling."""
        from simple_salesforce.exceptions import SalesforceError
        
        error = SalesforceError("INVALID_SESSION_ID")
        mock_salesforce_client.query.side_effect = error
        
        with patch.object(salesforce_tool, '_get_salesforce_client', return_value=mock_salesforce_client):
            with pytest.raises(InvalidCredentialsError):
                await salesforce_tool._handle_query_soql(mock_salesforce_client, {'query': 'SELECT Id FROM Account'})


# ============================================================================
# VALIDATION TESTS
# ============================================================================


class TestSalesforceValidation:
    """Test Salesforce parameter validation."""
    
    def test_validate_operation_params_query_soql(self, salesforce_tool):
        """Test parameter validation for query_soql."""
        # Valid query
        params = {'query': 'SELECT Id, Name FROM Account LIMIT 10'}
        validated = salesforce_tool._validate_operation_params('query_soql', params)
        assert validated['query'] == 'SELECT Id, Name FROM Account LIMIT 10'
        
        # Invalid query (doesn't start with SELECT)
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('query_soql', {'query': 'UPDATE Account SET Name = "Test"'})
        
        # Query too long
        long_query = 'SELECT Id FROM Account WHERE ' + ' AND '.join([f'Name LIKE "%test{i}%"' for i in range(1000)])
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('query_soql', {'query': long_query})
    
    def test_validate_operation_params_get_record(self, salesforce_tool):
        """Test parameter validation for get_record."""
        # Missing sobject
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('get_record', {'record_id': '001'})
        
        # Missing record_id
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('get_record', {'sobject': 'Account'})
    
    def test_validate_operation_params_create_record(self, salesforce_tool):
        """Test parameter validation for create_record."""
        # Missing sobject
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('create_record', {'data': {'Name': 'Test'}})
        
        # Missing data
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('create_record', {'sobject': 'Account'})
        
        # Invalid data type
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('create_record', {
                'sobject': 'Account',
                'data': 'invalid_data'
            })
    
    def test_validate_operation_params_upsert_record(self, salesforce_tool):
        """Test parameter validation for upsert_record."""
        # Missing required fields
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('upsert_record', {'sobject': 'Account'})
        
        # Missing external_id_field
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('upsert_record', {
                'sobject': 'Account',
                'external_id_value': 'EXT123',
                'data': {'Name': 'Test'}
            })
    
    def test_validate_operation_params_bulk_operations(self, salesforce_tool):
        """Test parameter validation for bulk operations."""
        # Missing sobject
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('bulk_create', {'records': []})
        
        # Missing records
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('bulk_create', {'sobject': 'Account'})
        
        # Invalid records type
        with pytest.raises(ValidationError):
            salesforce_tool._validate_operation_params('bulk_create', {
                'sobject': 'Account',
                'records': 'invalid_records'
            })


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestSalesforceIntegration:
    """Test Salesforce tool integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, salesforce_tool, mock_credentials):
        """Test complete Salesforce workflow."""
        # Mock secrets manager
        with patch.object(salesforce_tool.secrets_manager, 'get_secret', return_value=mock_credentials.to_dict()):
            # Mock Salesforce client
            with patch.object(salesforce_tool, '_get_salesforce_client') as mock_get_client:
                mock_client = MagicMock()
                mock_get_client.return_value = mock_client
                
                # Mock query
                mock_client.query.return_value = {
                    'records': [{'Id': '001000000000001', 'Name': 'Test Account'}],
                    'totalSize': 1,
                    'done': True
                }
                
                # Execute workflow
                result = await salesforce_tool.execute(
                    tenant_id="tenant_123",
                    operation="query_soql",
                    params={'query': 'SELECT Id, Name FROM Account LIMIT 1'}
                )
                
                assert result.success is True
                assert 'records' in result.data
    
    @pytest.mark.asyncio
    async def test_credential_refresh_workflow(self, salesforce_tool, mock_credentials):
        """Test credential refresh workflow."""
        # Set credentials to need refresh
        mock_credentials.issued_at = str(int((datetime.utcnow() - timedelta(hours=2)).timestamp() * 1000))
        
        # Mock secrets manager
        with patch.object(salesforce_tool.secrets_manager, 'get_secret', return_value=mock_credentials.to_dict()):
            with patch.object(salesforce_tool.secrets_manager, 'set_secret') as mock_set_secret:
                with patch.object(salesforce_tool, '_refresh_salesforce_token') as mock_refresh:
                    # Mock refreshed credentials
                    refreshed_creds = SalesforceCredentials(
                        access_token="new_token",
                        refresh_token=mock_credentials.refresh_token,
                        instance_url=mock_credentials.instance_url,
                        id=mock_credentials.id,
                        issued_at=str(int(time.time() * 1000))
                    )
                    mock_refresh.return_value = refreshed_creds
                    
                    # Mock Salesforce client
                    with patch.object(salesforce_tool, '_get_salesforce_client') as mock_get_client:
                        mock_client = MagicMock()
                        mock_get_client.return_value = mock_client
                        mock_client.query.return_value = {'records': [], 'totalSize': 0, 'done': True}
                        
                        # Execute operation
                        result = await salesforce_tool.execute(
                            tenant_id="tenant_123",
                            operation="query_soql",
                            params={'query': 'SELECT Id FROM Account'}
                        )
                        
                        # Verify refresh was called
                        mock_refresh.assert_called_once()
                        mock_set_secret.assert_called_once()
                        assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__])
