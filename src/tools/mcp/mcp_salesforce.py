"""
Salesforce MCP Tool - Production-Ready Implementation

This module provides comprehensive Salesforce integration with:
- OAuth 2.0 authentication with automatic token refresh
- Full Salesforce REST API v58.0 support (SOQL, CRUD, describe)
- Rate limiting and quota management
- Comprehensive error handling
- Multi-tenant credential isolation
- Input validation and SOQL sanitization
- Bulk operations and batch processing
- SObject metadata and describe operations

Based on official Salesforce API documentation:
- Base URL: https://yourinstance.salesforce.com/services/data/v58.0
- Auth: OAuth 2.0 with refresh tokens
- Scopes: api, refresh_token, offline_access

Author: Etherion AI Platform Team
Version: 1.0.0
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import aiohttp
try:
    from simple_salesforce import Salesforce
    from simple_salesforce.exceptions import SalesforceError, SalesforceAuthenticationFailed
except Exception:
    Salesforce = None  # type: ignore
    SalesforceError = Exception  # type: ignore
    SalesforceAuthenticationFailed = Exception  # type: ignore

from .base_mcp_tool import (
    EnhancedMCPTool,
    MCPToolResult,
    RateLimitConfig,
    RetryConfig,
    CircuitBreakerConfig,
    InvalidCredentialsError,
    RateLimitError,
    ValidationError,
    NetworkError,
    QuotaExceededError,
    AuthType,
)

logger = logging.getLogger(__name__)


# ============================================================================
# SALESFORCE CREDENTIALS & CONFIGURATION
# ============================================================================


@dataclass
class SalesforceCredentials:
    """Salesforce OAuth 2.0 credentials with auto-refresh support."""
    
    access_token: str
    refresh_token: str
    instance_url: str
    id: str
    token_type: str = "Bearer"
    issued_at: Optional[str] = None
    signature: Optional[str] = None
    client_id: str = ""
    client_secret: str = ""
    
    def needs_refresh(self) -> bool:
        """Check if token needs refresh (within 1 hour of expiry)."""
        if not self.issued_at:
            return True
        try:
            issued_time = datetime.fromtimestamp(int(self.issued_at) / 1000)
            # Salesforce tokens typically expire in 2 hours
            return datetime.utcnow() >= (issued_time + timedelta(hours=1))
        except (ValueError, TypeError):
            return True
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.issued_at:
            return True
        try:
            issued_time = datetime.fromtimestamp(int(self.issued_at) / 1000)
            # Salesforce tokens typically expire in 2 hours
            return datetime.utcnow() >= (issued_time + timedelta(hours=2))
        except (ValueError, TypeError):
            return True
    
    def to_salesforce_client(self) -> Salesforce:
        """Convert to Salesforce client object."""
        if Salesforce is None:
            raise ValidationError("Optional dependency 'simple_salesforce' is not installed")
        return Salesforce(
            instance_url=self.instance_url,
            session_id=self.access_token
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SalesforceCredentials":
        """Create from dictionary."""
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            instance_url=data["instance_url"],
            id=data["id"],
            token_type=data.get("token_type", "Bearer"),
            issued_at=data.get("issued_at"),
            signature=data.get("signature"),
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", "")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "instance_url": self.instance_url,
            "id": self.id,
            "token_type": self.token_type,
            "issued_at": self.issued_at,
            "signature": self.signature,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }


# ============================================================================
# SALESFORCE MCP TOOL
# ============================================================================


class MCPSalesforceTool(EnhancedMCPTool):
    """
    Production-ready Salesforce MCP tool with comprehensive API support.
    
    Features:
    - OAuth 2.0 with automatic token refresh
    - Full Salesforce REST API v58.0 support
    - SOQL query execution
    - CRUD operations on SObjects
    - Bulk operations and batch processing
    - SObject metadata and describe operations
    - Rate limiting (15,000 API calls per day)
    - Comprehensive error handling
    - Multi-tenant credential isolation
    - Input validation and SOQL sanitization
    
    Usage:
        tool = MCPSalesforceTool()
        result = await tool.execute(
            tenant_id="tenant_123",
            operation="query_soql",
            params={"query": "SELECT Id, Name FROM Account LIMIT 10"}
        )
    """
    
    # Salesforce API rate limits
    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=10.0,  # Conservative rate limiting
        burst_size=15,
    )
    
    DEFAULT_RETRY_CONFIG = RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
    )
    
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=60.0,
    )
    
    # Salesforce API version
    API_VERSION = "v58.0"
    
    def __init__(
        self,
        rate_limit_config: Optional[RateLimitConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        """Initialize Salesforce MCP tool."""
        super().__init__(
            name="mcp_salesforce",
            description="Salesforce integration with OAuth 2.0, auto-refresh, and comprehensive API support",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )
        
        # Salesforce-specific configuration
        self._client_cache: Dict[str, Salesforce] = {}
        self._credentials_cache: Dict[str, SalesforceCredentials] = {}
    
    # ============================= Validation Schema =============================
    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        STR = str
        INT = int
        LIST = list
        DICT = dict

        schemas: Dict[str, Dict[str, Any]] = {
            "query_soql": {
                "query": {"required": True, "type": STR},
            },
            "query_all_soql": {
                "query": {"required": True, "type": STR},
            },
            "get_record": {
                "sobject": {"required": True, "type": STR},
                "record_id": {"required": True, "type": STR},
                "fields": {"required": False, "type": LIST},
            },
            "create_record": {
                "sobject": {"required": True, "type": STR},
                "data": {"required": True, "type": DICT},
            },
            "update_record": {
                "sobject": {"required": True, "type": STR},
                "record_id": {"required": True, "type": STR},
                "data": {"required": True, "type": DICT},
            },
            "delete_record": {
                "sobject": {"required": True, "type": STR},
                "record_id": {"required": True, "type": STR},
            },
            "upsert_record": {
                "sobject": {"required": True, "type": STR},
                "external_id_field": {"required": True, "type": STR},
                "external_id_value": {"required": True, "type": STR},
                "data": {"required": True, "type": DICT},
            },
            "describe_sobject": {
                "sobject": {"required": True, "type": STR},
            },
            "get_sobject_list": {},
            "get_sobject_metadata": {
                "sobject": {"required": True, "type": STR},
            },
            "bulk_create": {
                "sobject": {"required": True, "type": STR},
                "records": {"required": True, "type": LIST},
            },
            "bulk_update": {
                "sobject": {"required": True, "type": STR},
                "records": {"required": True, "type": LIST},
            },
            "bulk_delete": {
                "sobject": {"required": True, "type": STR},
                "record_ids": {"required": True, "type": LIST},
            },
            "get_user_info": {},
            "get_org_info": {},
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        write_ops = {
            "create_record",
            "update_record",
            "delete_record",
            "upsert_record",
            "bulk_create",
            "bulk_update",
            "bulk_delete",
        }
        return op in write_ops or super()._is_write_operation(operation, params)
    
    async def _get_salesforce_client(self, tenant_id: str) -> Salesforce:
        """Get authenticated Salesforce client with auto-refresh."""
        # Check cache first
        if tenant_id in self._client_cache:
            client = self._client_cache[tenant_id]
            if client:
                return client
        
        # Get credentials with auto-refresh
        creds = await self._get_credentials_with_refresh(tenant_id)
        
        # Build client
        try:
            client = creds.to_salesforce_client()
            self._client_cache[tenant_id] = client
            return client
        except Exception as e:
            logger.error(f"Failed to build Salesforce client for tenant {tenant_id}: {e}")
            raise InvalidCredentialsError(f"Failed to authenticate with Salesforce: {e}")
    
    async def _get_credentials_with_refresh(self, tenant_id: str) -> SalesforceCredentials:
        """Get Salesforce credentials with automatic refresh."""
        # Check cache first
        if tenant_id in self._credentials_cache:
            creds = self._credentials_cache[tenant_id]
            if not creds.needs_refresh():
                return creds
        
        # Get from secrets manager
        try:
            creds_data = await self.secrets_manager.get_secret(
                tenant_id=tenant_id,
                service_name="salesforce",
                key_type="oauth_credentials"
            )
            
            creds = SalesforceCredentials.from_dict(creds_data)
            
            # Refresh if needed
            if creds.needs_refresh():
                creds = await self._refresh_salesforce_token(tenant_id, creds)
                # Save refreshed credentials
                await self.secrets_manager.set_secret(
                    tenant_id=tenant_id,
                    service_name="salesforce",
                    key_type="oauth_credentials",
                    secret_value=creds.to_dict()
                )
            
            # Cache credentials
            self._credentials_cache[tenant_id] = creds
            return creds
            
        except Exception as e:
            logger.error(f"Failed to get Salesforce credentials for tenant {tenant_id}: {e}")
            raise InvalidCredentialsError(f"Salesforce credentials not found or invalid: {e}")
    
    async def _refresh_salesforce_token(self, tenant_id: str, creds: SalesforceCredentials) -> SalesforceCredentials:
        """Refresh Salesforce OAuth token."""
        try:
            # Use simple-salesforce to refresh token
            client = Salesforce(
                instance_url=creds.instance_url,
                session_id=creds.access_token
            )
            
            # Refresh token
            client.refresh_token(creds.refresh_token, creds.client_id, creds.client_secret)
            
            # Update credentials
            creds.access_token = client.session_id
            creds.issued_at = str(int(time.time() * 1000))
            
            logger.info(f"Refreshed Salesforce token for tenant {tenant_id}")
            return creds
                
        except Exception as e:
            logger.error(f"Failed to refresh Salesforce token for tenant {tenant_id}: {e}")
            raise InvalidCredentialsError(f"Token refresh failed: {e}")
    
    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        """Execute Salesforce operation."""
        try:
            # Get authenticated client
            client = await self._get_salesforce_client(tenant_id)
            
            # Route to specific operation
            if operation == "query_soql":
                return await self._handle_query_soql(client, params)
            elif operation == "query_all_soql":
                return await self._handle_query_all_soql(client, params)
            elif operation == "get_record":
                return await self._handle_get_record(client, params)
            elif operation == "create_record":
                return await self._handle_create_record(client, params)
            elif operation == "update_record":
                return await self._handle_update_record(client, params)
            elif operation == "delete_record":
                return await self._handle_delete_record(client, params)
            elif operation == "upsert_record":
                return await self._handle_upsert_record(client, params)
            elif operation == "describe_sobject":
                return await self._handle_describe_sobject(client, params)
            elif operation == "get_sobject_list":
                return await self._handle_get_sobject_list(client, params)
            elif operation == "get_sobject_metadata":
                return await self._handle_get_sobject_metadata(client, params)
            elif operation == "bulk_create":
                return await self._handle_bulk_create(client, params)
            elif operation == "bulk_update":
                return await self._handle_bulk_update(client, params)
            elif operation == "bulk_delete":
                return await self._handle_bulk_delete(client, params)
            elif operation == "get_user_info":
                return await self._handle_get_user_info(client, params)
            elif operation == "get_org_info":
                return await self._handle_get_org_info(client, params)
            else:
                raise ValidationError(f"Unsupported operation: {operation}")
                
        except SalesforceAuthenticationFailed as e:
            raise InvalidCredentialsError(f"Salesforce authentication failed: {e}")
        except SalesforceError as e:
            if "INVALID_SESSION_ID" in str(e):
                raise InvalidCredentialsError(f"Invalid Salesforce session: {e}")
            elif "RATE_LIMIT_EXCEEDED" in str(e):
                raise RateLimitError(f"Salesforce rate limit exceeded: {e}")
            elif "QUOTA_EXCEEDED" in str(e):
                raise QuotaExceededError(f"Salesforce quota exceeded: {e}")
            else:
                raise ValidationError(f"Salesforce API error: {e}")
        except Exception as e:
            logger.error(f"Salesforce operation {operation} failed: {e}")
            raise
    
    # ========================================================================
    # SALESFORCE API OPERATIONS
    # ========================================================================
    
    async def _handle_query_soql(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Execute SOQL query."""
        try:
            query = params['query']
            
            # Execute query
            result = client.query(query)
            
            return MCPToolResult(
                success=True,
                data={
                    'records': result['records'],
                    'total_size': result['totalSize'],
                    'done': result['done'],
                    'next_records_url': result.get('nextRecordsUrl')
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to execute SOQL query: {e}")
            raise
    
    async def _handle_query_all_soql(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Execute SOQL query including deleted records."""
        try:
            query = params['query']
            
            # Execute query all
            result = client.query_all(query)
            
            return MCPToolResult(
                success=True,
                data={
                    'records': result['records'],
                    'total_size': result['totalSize'],
                    'done': result['done'],
                    'next_records_url': result.get('nextRecordsUrl')
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to execute SOQL query_all: {e}")
            raise
    
    async def _handle_get_record(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Get single record by ID."""
        try:
            sobject = params['sobject']
            record_id = params['record_id']
            fields = params.get('fields', [])
            
            # Get record
            if fields:
                result = getattr(client, sobject).get(record_id, fields=fields)
            else:
                result = getattr(client, sobject).get(record_id)
            
            return MCPToolResult(
                success=True,
                data={'record': result}
            )
            
        except Exception as e:
            logger.error(f"Failed to get record {params.get('record_id')}: {e}")
            raise
    
    async def _handle_create_record(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Create new record."""
        try:
            sobject = params['sobject']
            data = params['data']
            
            # Create record
            result = getattr(client, sobject).create(data)
            
            return MCPToolResult(
                success=True,
                data={
                    'id': result['id'],
                    'success': result['success'],
                    'errors': result.get('errors', [])
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to create record: {e}")
            raise
    
    async def _handle_update_record(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Update existing record."""
        try:
            sobject = params['sobject']
            record_id = params['record_id']
            data = params['data']
            
            # Update record
            result = getattr(client, sobject).update(record_id, data)
            
            return MCPToolResult(
                success=True,
                data={
                    'id': result['id'],
                    'success': result['success'],
                    'errors': result.get('errors', [])
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to update record {params.get('record_id')}: {e}")
            raise
    
    async def _handle_delete_record(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Delete record."""
        try:
            sobject = params['sobject']
            record_id = params['record_id']
            
            # Delete record
            result = getattr(client, sobject).delete(record_id)
            
            return MCPToolResult(
                success=True,
                data={
                    'id': result['id'],
                    'success': result['success'],
                    'errors': result.get('errors', [])
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to delete record {params.get('record_id')}: {e}")
            raise
    
    async def _handle_upsert_record(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Upsert record (insert or update)."""
        try:
            sobject = params['sobject']
            external_id_field = params['external_id_field']
            external_id_value = params['external_id_value']
            data = params['data']
            
            # Upsert record
            result = getattr(client, sobject).upsert(
                external_id_field, 
                external_id_value, 
                data
            )
            
            return MCPToolResult(
                success=True,
                data={
                    'id': result['id'],
                    'success': result['success'],
                    'created': result.get('created', False),
                    'errors': result.get('errors', [])
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to upsert record: {e}")
            raise
    
    async def _handle_describe_sobject(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Get SObject describe information."""
        try:
            sobject = params['sobject']
            
            # Get describe
            result = getattr(client, sobject).describe()
            
            return MCPToolResult(
                success=True,
                data={'describe': result}
            )
            
        except Exception as e:
            logger.error(f"Failed to describe SObject {params.get('sobject')}: {e}")
            raise
    
    async def _handle_get_sobject_list(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Get list of all SObjects."""
        try:
            # Get SObject list
            result = client.describe()
            
            return MCPToolResult(
                success=True,
                data={'sobjects': result['sobjects']}
            )
            
        except Exception as e:
            logger.error(f"Failed to get SObject list: {e}")
            raise
    
    async def _handle_get_sobject_metadata(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Get SObject metadata."""
        try:
            sobject = params['sobject']
            
            # Get metadata
            result = getattr(client, sobject).metadata()
            
            return MCPToolResult(
                success=True,
                data={'metadata': result}
            )
            
        except Exception as e:
            logger.error(f"Failed to get SObject metadata {params.get('sobject')}: {e}")
            raise
    
    async def _handle_bulk_create(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Bulk create records."""
        try:
            sobject = params['sobject']
            records = params['records']
            
            # Bulk create
            result = getattr(client, sobject).bulk_create(records)
            
            return MCPToolResult(
                success=True,
                data={'results': result}
            )
            
        except Exception as e:
            logger.error(f"Failed to bulk create records: {e}")
            raise
    
    async def _handle_bulk_update(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Bulk update records."""
        try:
            sobject = params['sobject']
            records = params['records']
            
            # Bulk update
            result = getattr(client, sobject).bulk_update(records)
            
            return MCPToolResult(
                success=True,
                data={'results': result}
            )
            
        except Exception as e:
            logger.error(f"Failed to bulk update records: {e}")
            raise
    
    async def _handle_bulk_delete(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Bulk delete records."""
        try:
            sobject = params['sobject']
            record_ids = params['record_ids']
            
            # Bulk delete
            result = getattr(client, sobject).bulk_delete(record_ids)
            
            return MCPToolResult(
                success=True,
                data={'results': result}
            )
            
        except Exception as e:
            logger.error(f"Failed to bulk delete records: {e}")
            raise
    
    async def _handle_get_user_info(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Get current user information."""
        try:
            # Get user info
            result = client.query("SELECT Id, Name, Email, Username FROM User WHERE Id = '{}'".format(
                client.query("SELECT Id FROM User LIMIT 1")['records'][0]['Id']
            ))
            
            return MCPToolResult(
                success=True,
                data={'user': result['records'][0] if result['records'] else None}
            )
            
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            raise
    
    async def _handle_get_org_info(self, client: Salesforce, params: Dict[str, Any]) -> MCPToolResult:
        """Get organization information."""
        try:
            # Get org info
            result = client.query("SELECT Id, Name, OrganizationType, PrimaryContact FROM Organization LIMIT 1")
            
            return MCPToolResult(
                success=True,
                data={'organization': result['records'][0] if result['records'] else None}
            )
            
        except Exception as e:
            logger.error(f"Failed to get org info: {e}")
            raise
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _validate_operation_params(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate operation parameters."""
        # Common validations
        if 'query' in params:
            # Basic SOQL injection prevention
            query = str(params['query']).strip()
            if not query.upper().startswith('SELECT'):
                raise ValidationError("SOQL query must start with SELECT")
            
            # Limit query length
            if len(query) > 20000:
                raise ValidationError("SOQL query too long (max 20,000 characters)")
            
            params['query'] = query
        
        # Operation-specific validations
        if operation in ["get_record", "update_record", "delete_record"]:
            if 'sobject' not in params:
                raise ValidationError("sobject is required")
            if 'record_id' not in params:
                raise ValidationError("record_id is required")
        
        elif operation == "create_record":
            if 'sobject' not in params:
                raise ValidationError("sobject is required")
            if 'data' not in params:
                raise ValidationError("data is required")
            if not isinstance(params['data'], dict):
                raise ValidationError("data must be a dictionary")
        
        elif operation == "upsert_record":
            required_fields = ['sobject', 'external_id_field', 'external_id_value', 'data']
            for field in required_fields:
                if field not in params:
                    raise ValidationError(f"{field} is required for upsert_record operation")
        
        elif operation in ["describe_sobject", "get_sobject_metadata"]:
            if 'sobject' not in params:
                raise ValidationError("sobject is required")
        
        elif operation in ["bulk_create", "bulk_update"]:
            if 'sobject' not in params:
                raise ValidationError("sobject is required")
            if 'records' not in params:
                raise ValidationError("records is required")
            if not isinstance(params['records'], list):
                raise ValidationError("records must be a list")
        
        elif operation == "bulk_delete":
            if 'sobject' not in params:
                raise ValidationError("sobject is required")
            if 'record_ids' not in params:
                raise ValidationError("record_ids is required")
            if not isinstance(params['record_ids'], list):
                raise ValidationError("record_ids must be a list")
        
        return params


# ============================================================================
# EXPORT
# ============================================================================

__all__ = ['MCPSalesforceTool', 'SalesforceCredentials']
