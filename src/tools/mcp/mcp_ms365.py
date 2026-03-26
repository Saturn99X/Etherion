"""
Microsoft 365 MCP Tool - Production-Ready Implementation

This module provides comprehensive Microsoft 365 integration with:
- OAuth 2.0 authentication with automatic token refresh
- Full Microsoft Graph API v1.0 support (mail, calendar, drive, users, teams)
- Rate limiting and quota management
- Comprehensive error handling
- Multi-tenant credential isolation
- Input validation and permission scoping
- SharePoint and Teams integration
- OneDrive file operations

Based on official Microsoft Graph API documentation:
- Base URL: https://graph.microsoft.com/v1.0
- Auth: OAuth 2.0 with MSAL
- Scopes: User.Read, Mail.Read, Calendars.ReadWrite, Files.ReadWrite.All

Author: Etherion AI Platform Team
Version: 1.0.0
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import aiohttp
try:
    from msal import ConfidentialClientApplication
except Exception:
    ConfidentialClientApplication = None  # type: ignore

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
# MICROSOFT 365 CREDENTIALS & CONFIGURATION
# ============================================================================


@dataclass
class MS365Credentials:
    """Microsoft 365 OAuth 2.0 credentials with auto-refresh support."""
    
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_at: Optional[datetime] = None
    expires_in: int = 3600
    scope: str = ""
    client_id: str = ""
    client_secret: str = ""
    tenant_id: str = ""
    
    def needs_refresh(self) -> bool:
        """Check if token needs refresh (within 1 hour of expiry)."""
        if not self.expires_at:
            return True
        return datetime.utcnow() >= (self.expires_at - timedelta(hours=1))
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expires_at:
            return True
        return datetime.utcnow() >= self.expires_at
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MS365Credentials":
        """Create from dictionary."""
        expires_at = None
        if data.get("expires_at"):
            if isinstance(data["expires_at"], str):
                expires_at = datetime.fromisoformat(data["expires_at"])
            else:
                expires_at = data["expires_at"]
        
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            expires_in=data.get("expires_in", 3600),
            scope=data.get("scope", ""),
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
            tenant_id=data.get("tenant_id", "")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "expires_in": self.expires_in,
            "scope": self.scope,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "tenant_id": self.tenant_id
        }


# ============================================================================
# MICROSOFT 365 MCP TOOL
# ============================================================================


class MCPMS365Tool(EnhancedMCPTool):
    """
    Production-ready Microsoft 365 MCP tool with comprehensive API support.
    
    Features:
    - OAuth 2.0 with automatic token refresh using MSAL
    - Full Microsoft Graph API v1.0 support
    - Mail, Calendar, OneDrive, Users, Teams operations
    - Rate limiting (10,000 requests per 10 minutes)
    - Comprehensive error handling
    - Multi-tenant credential isolation
    - Input validation and permission scoping
    - SharePoint and Teams integration
    
    Usage:
        tool = MCPMS365Tool()
        result = await tool.execute(
            tenant_id="tenant_123",
            operation="get_user_profile",
            params={}
        )
    """
    
    # Microsoft Graph API rate limits
    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=16.0,  # 10,000 per 10 minutes = ~16.7 per second
        burst_size=20,
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
    
    # Microsoft Graph API base URL
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    
    def __init__(
        self,
        rate_limit_config: Optional[RateLimitConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        """Initialize Microsoft 365 MCP tool."""
        super().__init__(
            name="mcp_ms365",
            description="Microsoft 365 integration with OAuth 2.0, auto-refresh, and comprehensive Graph API support",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.GRAPH_API_BASE,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )
        
        # Microsoft 365-specific configuration
        self._credentials_cache: Dict[str, MS365Credentials] = {}
    
    # ============================= Validation Schema =============================
    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        STR = str
        INT = int
        BOOL = bool
        LIST = list
        DICT = dict

        schemas: Dict[str, Dict[str, Any]] = {
            # Mail
            "get_user_profile": {},
            "list_messages": {
                "folder": {"required": False, "type": STR},
                "top": {"required": False, "type": INT},
                "select": {"required": False, "type": STR},
            },
            "get_message": {
                "message_id": {"required": True, "type": STR},
            },
            "send_mail": {
                "subject": {"required": True, "type": STR},
                "body": {"required": True, "type": STR},
                "to_recipients": {"required": True, "type": LIST},
                "content_type": {"required": False, "type": STR},
                "save_to_sent_items": {"required": False, "type": BOOL},
            },
            # Calendar
            "list_events": {
                "start_date": {"required": False, "type": STR},
                "end_date": {"required": False, "type": STR},
                "select": {"required": False, "type": STR},
            },
            "create_event": {
                "subject": {"required": True, "type": STR},
                "start_datetime": {"required": True, "type": STR},
                "end_datetime": {"required": True, "type": STR},
                "timezone": {"required": False, "type": STR},
                "location": {"required": False, "type": STR},
                "attendees": {"required": False, "type": LIST},
            },
            "update_event": {
                "event_id": {"required": True, "type": STR},
                "update_data": {"required": True, "type": DICT},
            },
            "delete_event": {
                "event_id": {"required": True, "type": STR},
            },
            # Drive
            "list_drive_items": {
                "folder_id": {"required": False, "type": STR},
                "select": {"required": False, "type": STR},
            },
            "upload_file": {
                "file_path": {"required": True, "type": STR},
                "content": {"required": True, "type": bytes},
                "content_type": {"required": False, "type": STR},
            },
            "download_file": {
                "file_id": {"required": True, "type": STR},
            },
            "create_folder": {
                "folder_name": {"required": True, "type": STR},
                "parent_id": {"required": False, "type": STR},
            },
            # Teams
            "list_teams": {},
            "get_team": {
                "team_id": {"required": True, "type": STR},
            },
            "list_team_channels": {
                "team_id": {"required": True, "type": STR},
            },
            "send_team_message": {
                "team_id": {"required": True, "type": STR},
                "channel_id": {"required": True, "type": STR},
                "message_content": {"required": True, "type": STR},
            },
            # SharePoint
            "list_sharepoint_sites": {},
            "get_sharepoint_site": {
                "site_id": {"required": True, "type": STR},
            },
            "list_sharepoint_lists": {
                "site_id": {"required": True, "type": STR},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        write_ops = {
            "send_mail",
            "create_event",
            "update_event",
            "delete_event",
            "upload_file",
            "create_folder",
            "send_team_message",
        }
        return op in write_ops or super()._is_write_operation(operation, params)
    
    async def _get_graph_headers(self, tenant_id: str) -> Dict[str, str]:
        """Get Microsoft Graph auth headers with auto-refresh."""
        # Get credentials with auto-refresh
        creds = await self._get_credentials_with_refresh(tenant_id)
        
        return {
            "Authorization": f"Bearer {creds.access_token}",
            "Content-Type": "application/json"
        }
    
    async def _get_credentials_with_refresh(self, tenant_id: str) -> MS365Credentials:
        """Get Microsoft 365 credentials with automatic refresh."""
        # Check cache first
        if tenant_id in self._credentials_cache:
            creds = self._credentials_cache[tenant_id]
            if not creds.needs_refresh():
                return creds
        
        # Get from secrets manager
        try:
            creds_data = await self.secrets_manager.get_secret(
                tenant_id=tenant_id,
                service_name="ms365",
                key_type="oauth_credentials"
            )
            
            creds = MS365Credentials.from_dict(creds_data)
            
            # Refresh if needed
            if creds.needs_refresh():
                creds = await self._refresh_ms365_token(tenant_id, creds)
                # Save refreshed credentials
                await self.secrets_manager.set_secret(
                    tenant_id=tenant_id,
                    service_name="ms365",
                    key_type="oauth_credentials",
                    secret_value=creds.to_dict()
                )
            
            # Cache credentials
            self._credentials_cache[tenant_id] = creds
            return creds
            
        except Exception as e:
            logger.error(f"Failed to get Microsoft 365 credentials for tenant {tenant_id}: {e}")
            raise InvalidCredentialsError(f"Microsoft 365 credentials not found or invalid: {e}")
    
    async def _refresh_ms365_token(self, tenant_id: str, creds: MS365Credentials) -> MS365Credentials:
        """Refresh Microsoft 365 OAuth token using MSAL."""
        try:
            if ConfidentialClientApplication is None:
                raise ValidationError("Optional dependency 'msal' is not installed")

            # Initialize MSAL app
            app = ConfidentialClientApplication(
                client_id=creds.client_id,
                client_credential=creds.client_secret,
                authority=f"https://login.microsoftonline.com/{creds.tenant_id}"
            )
            
            # Refresh token
            result = app.acquire_token_by_refresh_token(
                refresh_token=creds.refresh_token,
                scopes=creds.scope.split()
            )
            
            if "access_token" not in result:
                raise InvalidCredentialsError(f"Token refresh failed: {result.get('error_description', 'Unknown error')}")
            
            # Update credentials
            creds.access_token = result["access_token"]
            creds.refresh_token = result.get("refresh_token", creds.refresh_token)
            creds.expires_in = result.get("expires_in", 3600)
            creds.expires_at = datetime.utcnow() + timedelta(seconds=creds.expires_in)
            
            logger.info(f"Refreshed Microsoft 365 token for tenant {tenant_id}")
            return creds
                
        except Exception as e:
            logger.error(f"Failed to refresh Microsoft 365 token for tenant {tenant_id}: {e}")
            raise InvalidCredentialsError(f"Token refresh failed: {e}")
    
    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        """Execute Microsoft 365 operation."""
        try:
            # Get auth headers
            headers = await self._get_graph_headers(tenant_id)
            
            # Route to specific operation
            if operation == "get_user_profile":
                return await self._handle_get_user_profile(headers, params)
            elif operation == "list_messages":
                return await self._handle_list_messages(headers, params)
            elif operation == "get_message":
                return await self._handle_get_message(headers, params)
            elif operation == "send_mail":
                return await self._handle_send_mail(headers, params)
            elif operation == "list_events":
                return await self._handle_list_events(headers, params)
            elif operation == "create_event":
                return await self._handle_create_event(headers, params)
            elif operation == "update_event":
                return await self._handle_update_event(headers, params)
            elif operation == "delete_event":
                return await self._handle_delete_event(headers, params)
            elif operation == "list_drive_items":
                return await self._handle_list_drive_items(headers, params)
            elif operation == "upload_file":
                return await self._handle_upload_file(headers, params)
            elif operation == "download_file":
                return await self._handle_download_file(headers, params)
            elif operation == "create_folder":
                return await self._handle_create_folder(headers, params)
            elif operation == "list_teams":
                return await self._handle_list_teams(headers, params)
            elif operation == "get_team":
                return await self._handle_get_team(headers, params)
            elif operation == "list_team_channels":
                return await self._handle_list_team_channels(headers, params)
            elif operation == "send_team_message":
                return await self._handle_send_team_message(headers, params)
            elif operation == "list_sharepoint_sites":
                return await self._handle_list_sharepoint_sites(headers, params)
            elif operation == "get_sharepoint_site":
                return await self._handle_get_sharepoint_site(headers, params)
            elif operation == "list_sharepoint_lists":
                return await self._handle_list_sharepoint_lists(headers, params)
            else:
                raise ValidationError(f"Unsupported operation: {operation}")
                
        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                raise InvalidCredentialsError(f"Microsoft Graph authentication failed: {e}")
            elif e.status == 429:
                retry_after = e.headers.get('Retry-After', 60)
                raise RateLimitError(f"Microsoft Graph rate limit exceeded: {e}", retry_after=int(retry_after))
            elif e.status == 403:
                raise QuotaExceededError(f"Microsoft Graph quota exceeded: {e}")
            elif e.status >= 500:
                raise NetworkError(f"Microsoft Graph server error: {e}")
            else:
                raise ValidationError(f"Microsoft Graph API error: {e}")
        except Exception as e:
            logger.error(f"Microsoft 365 operation {operation} failed: {e}")
            raise
    
    # ========================================================================
    # MICROSOFT GRAPH API OPERATIONS
    # ========================================================================
    
    async def _handle_get_user_profile(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Get current user profile."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me",
                    headers=headers
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'user': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            raise
    
    async def _handle_list_messages(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """List user messages."""
        try:
            folder = params.get('folder', 'inbox')
            top = min(params.get('top', 10), 100)
            select = params.get('select', 'subject,from,receivedDateTime')
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me/mailFolders/{folder}/messages",
                    headers=headers,
                    params={"$top": top, "$select": select}
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={
                            'messages': data.get('value', []),
                            'count': len(data.get('value', [])),
                            'next_link': data.get('@odata.nextLink')
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Failed to list messages: {e}")
            raise
    
    async def _handle_get_message(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Get specific message."""
        try:
            message_id = params['message_id']
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me/messages/{message_id}",
                    headers=headers
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'message': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to get message {params.get('message_id')}: {e}")
            raise
    
    async def _handle_send_mail(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Send email message."""
        try:
            message = {
                "message": {
                    "subject": params["subject"],
                    "body": {
                        "contentType": params.get("content_type", "HTML"),
                        "content": params["body"]
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": addr}} for addr in params["to_recipients"]
                    ]
                },
                "saveToSentItems": params.get("save_to_sent_items", True)
            }
            
            # Add CC and BCC if provided
            if "cc_recipients" in params:
                message["message"]["ccRecipients"] = [
                    {"emailAddress": {"address": addr}} for addr in params["cc_recipients"]
                ]
            
            if "bcc_recipients" in params:
                message["message"]["bccRecipients"] = [
                    {"emailAddress": {"address": addr}} for addr in params["bcc_recipients"]
                ]
            
            # Add deterministic Idempotency-Key header
            idempotency_key = self._generate_idempotency_key("send_mail", params)
            headers_with_idempotency = {
                **headers,
                "Idempotency-Key": idempotency_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.GRAPH_API_BASE}/me/sendMail",
                    headers=headers_with_idempotency,
                    json=message
                ) as response:
                    return MCPToolResult(
                        success=response.status == 202,
                        data={'status': response.status}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to send mail: {e}")
            raise
    
    async def _handle_list_events(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """List calendar events."""
        try:
            start_date = params.get('start_date', datetime.utcnow().isoformat())
            end_date = params.get('end_date', (datetime.utcnow() + timedelta(days=30)).isoformat())
            select = params.get('select', 'subject,start,end,location')
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me/calendarView",
                    headers=headers,
                    params={
                        "startDateTime": start_date,
                        "endDateTime": end_date,
                        "$select": select
                    }
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={
                            'events': data.get('value', []),
                            'count': len(data.get('value', [])),
                            'next_link': data.get('@odata.nextLink')
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Failed to list events: {e}")
            raise
    
    async def _handle_create_event(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Create calendar event."""
        try:
            event = {
                "subject": params["subject"],
                "start": {
                    "dateTime": params["start_datetime"],
                    "timeZone": params.get("timezone", "UTC")
                },
                "end": {
                    "dateTime": params["end_datetime"],
                    "timeZone": params.get("timezone", "UTC")
                },
                "location": {"displayName": params.get("location", "")},
                "attendees": [
                    {"emailAddress": {"address": addr}, "type": "required"}
                    for addr in params.get("attendees", [])
                ]
            }
            
            # Add optional fields
            if "body" in params:
                event["body"] = {
                    "contentType": "HTML",
                    "content": params["body"]
                }
            
            if "is_all_day" in params:
                event["isAllDay"] = params["is_all_day"]
            
            # Add deterministic Idempotency-Key header
            idempotency_key = self._generate_idempotency_key("create_event", params)
            headers_with_idempotency = {
                **headers,
                "Idempotency-Key": idempotency_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.GRAPH_API_BASE}/me/events",
                    headers=headers_with_idempotency,
                    json=event
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'event': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            raise
    
    async def _handle_update_event(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Update calendar event."""
        try:
            event_id = params['event_id']
            update_data = params['update_data']
            
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    f"{self.GRAPH_API_BASE}/me/events/{event_id}",
                    headers=headers,
                    json=update_data
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'event': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to update event {params.get('event_id')}: {e}")
            raise
    
    async def _handle_delete_event(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Delete calendar event."""
        try:
            event_id = params['event_id']
            
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.GRAPH_API_BASE}/me/events/{event_id}",
                    headers=headers
                ) as response:
                    return MCPToolResult(
                        success=response.status == 204,
                        data={'status': response.status}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to delete event {params.get('event_id')}: {e}")
            raise
    
    async def _handle_list_drive_items(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """List OneDrive items."""
        try:
            folder_id = params.get('folder_id', 'root')
            select = params.get('select', 'id,name,size,lastModifiedDateTime')
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me/drive/items/{folder_id}/children",
                    headers=headers,
                    params={"$select": select}
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={
                            'items': data.get('value', []),
                            'count': len(data.get('value', [])),
                            'next_link': data.get('@odata.nextLink')
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Failed to list drive items: {e}")
            raise
    
    async def _handle_upload_file(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Upload file to OneDrive."""
        try:
            file_path = params['file_path']
            content = params['content']
            content_type = params.get('content_type', 'application/octet-stream')
            
            # Update headers for file upload
            upload_headers = {**headers, "Content-Type": content_type}
            
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.GRAPH_API_BASE}/me/drive/root:/{file_path}:/content",
                    headers=upload_headers,
                    data=content
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'file': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise
    
    async def _handle_download_file(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Download file from OneDrive."""
        try:
            file_id = params['file_id']
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me/drive/items/{file_id}/content",
                    headers=headers
                ) as response:
                    content = await response.read()
                    
                    return MCPToolResult(
                        success=True,
                        data={'content': content}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to download file {params.get('file_id')}: {e}")
            raise
    
    async def _handle_create_folder(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Create folder in OneDrive."""
        try:
            folder_name = params['folder_name']
            parent_id = params.get('parent_id', 'root')
            
            folder_data = {
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.GRAPH_API_BASE}/me/drive/items/{parent_id}/children",
                    headers=headers,
                    json=folder_data
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'folder': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to create folder: {e}")
            raise
    
    async def _handle_list_teams(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """List user's teams."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me/joinedTeams",
                    headers=headers
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={
                            'teams': data.get('value', []),
                            'count': len(data.get('value', []))
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Failed to list teams: {e}")
            raise
    
    async def _handle_get_team(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Get specific team."""
        try:
            team_id = params['team_id']
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/teams/{team_id}",
                    headers=headers
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'team': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to get team {params.get('team_id')}: {e}")
            raise
    
    async def _handle_list_team_channels(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """List team channels."""
        try:
            team_id = params['team_id']
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/teams/{team_id}/channels",
                    headers=headers
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={
                            'channels': data.get('value', []),
                            'count': len(data.get('value', []))
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Failed to list team channels: {e}")
            raise
    
    async def _handle_send_team_message(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Send message to Teams channel."""
        try:
            team_id = params['team_id']
            channel_id = params['channel_id']
            message_content = params['message_content']
            
            message_data = {
                "body": {
                    "contentType": "html",
                    "content": message_content
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.GRAPH_API_BASE}/teams/{team_id}/channels/{channel_id}/messages",
                    headers=headers,
                    json=message_data
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'message': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to send team message: {e}")
            raise
    
    async def _handle_list_sharepoint_sites(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """List SharePoint sites."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/sites",
                    headers=headers
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={
                            'sites': data.get('value', []),
                            'count': len(data.get('value', []))
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Failed to list SharePoint sites: {e}")
            raise
    
    async def _handle_get_sharepoint_site(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """Get specific SharePoint site."""
        try:
            site_id = params['site_id']
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/sites/{site_id}",
                    headers=headers
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={'site': data}
                    )
                    
        except Exception as e:
            logger.error(f"Failed to get SharePoint site {params.get('site_id')}: {e}")
            raise
    
    async def _handle_list_sharepoint_lists(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """List SharePoint lists."""
        try:
            site_id = params['site_id']
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GRAPH_API_BASE}/sites/{site_id}/lists",
                    headers=headers
                ) as response:
                    data = await response.json()
                    
                    return MCPToolResult(
                        success=True,
                        data={
                            'lists': data.get('value', []),
                            'count': len(data.get('value', []))
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Failed to list SharePoint lists: {e}")
            raise
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _generate_idempotency_key(self, operation: str, params: Dict[str, Any]) -> str:
        """Generate deterministic Idempotency-Key for Microsoft Graph operations."""
        # Create a deterministic key based on operation and key parameters
        key_data = {
            "operation": operation,
            "timestamp": int(time.time() // 300) * 300,  # 5-minute window
        }
        
        # Add operation-specific parameters for uniqueness
        if operation == "send_mail":
            key_data.update({
                "subject": params.get("subject", ""),
                "to_recipients": sorted(params.get("to_recipients", [])),
                "body": params.get("body", "")[:100]  # First 100 chars for uniqueness
            })
        elif operation == "create_event":
            key_data.update({
                "subject": params.get("subject", ""),
                "start_datetime": params.get("start_datetime", ""),
                "end_datetime": params.get("end_datetime", ""),
                "attendees": sorted(params.get("attendees", []))
            })
        
        # Create deterministic hash
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]
    
    def _validate_operation_params(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate operation parameters."""
        # Common validations
        if 'top' in params:
            params['top'] = min(max(params['top'], 1), 100)
        
        if 'select' in params:
            # Limit select fields to prevent overly long queries
            select_fields = params['select'].split(',')
            if len(select_fields) > 20:
                params['select'] = ','.join(select_fields[:20])
        
        # Operation-specific validations
        if operation == "get_message":
            if 'message_id' not in params:
                raise ValidationError("message_id is required for get_message operation")
        
        elif operation == "send_mail":
            required_fields = ['subject', 'body', 'to_recipients']
            for field in required_fields:
                if field not in params:
                    raise ValidationError(f"{field} is required for send_mail operation")
            
            # Validate email addresses
            for email_list in ['to_recipients', 'cc_recipients', 'bcc_recipients']:
                if email_list in params:
                    if not isinstance(params[email_list], list):
                        raise ValidationError(f"{email_list} must be a list")
                    for email in params[email_list]:
                        if '@' not in email:
                            raise ValidationError(f"Invalid email address: {email}")
        
        elif operation == "create_event":
            required_fields = ['subject', 'start_datetime', 'end_datetime']
            for field in required_fields:
                if field not in params:
                    raise ValidationError(f"{field} is required for create_event operation")
        
        elif operation in ["update_event", "delete_event"]:
            if 'event_id' not in params:
                raise ValidationError("event_id is required")
        
        elif operation == "upload_file":
            if 'file_path' not in params or 'content' not in params:
                raise ValidationError("file_path and content are required for upload_file operation")
        
        elif operation == "download_file":
            if 'file_id' not in params:
                raise ValidationError("file_id is required for download_file operation")
        
        elif operation == "create_folder":
            if 'folder_name' not in params:
                raise ValidationError("folder_name is required for create_folder operation")
        
        elif operation in ["get_team", "list_team_channels", "send_team_message"]:
            if 'team_id' not in params:
                raise ValidationError("team_id is required")
        
        elif operation == "send_team_message":
            if 'channel_id' not in params or 'message_content' not in params:
                raise ValidationError("channel_id and message_content are required for send_team_message operation")
        
        elif operation in ["get_sharepoint_site", "list_sharepoint_lists"]:
            if 'site_id' not in params:
                raise ValidationError("site_id is required")
        
        return params


# ============================================================================
# EXPORT
# ============================================================================

__all__ = ['MCPMS365Tool', 'MS365Credentials']
