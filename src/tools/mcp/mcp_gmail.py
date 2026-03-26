"""
Gmail MCP Tool - Production-Ready Implementation

This module provides comprehensive Gmail integration with:
- OAuth 2.0 authentication with automatic token refresh
- Full Gmail API v1 support (messages, threads, labels, attachments)
- Rate limiting and quota management
- Comprehensive error handling
- Multi-tenant credential isolation
- Input validation and sanitization
- Attachment handling with base64 encoding
- MIME message construction and parsing

Based on official Gmail API documentation:
- Base URL: https://gmail.googleapis.com/gmail/v1
- Auth: OAuth 2.0 with refresh tokens
- Scopes: gmail.readonly, gmail.send, gmail.modify

Author: Etherion AI Platform Team
Date: January 15, 2025
Version: 1.0.0
"""

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import aiohttp
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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
# GMAIL CREDENTIALS & CONFIGURATION
# ============================================================================


@dataclass
class GmailCredentials:
    """Gmail OAuth 2.0 credentials with auto-refresh support."""
    
    access_token: str
    refresh_token: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    client_id: str = ""
    client_secret: str = ""
    scopes: List[str] = None
    expiry: Optional[datetime] = None
    
    def __post_init__(self):
        if self.scopes is None:
            self.scopes = [
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/gmail.send',
                'https://www.googleapis.com/auth/gmail.modify'
            ]
    
    def needs_refresh(self) -> bool:
        """Check if token needs refresh (within 1 hour of expiry)."""
        if not self.expiry:
            return True
        return datetime.utcnow() >= (self.expiry - timedelta(hours=1))
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expiry:
            return True
        return datetime.utcnow() >= self.expiry
    
    def to_credentials(self) -> Credentials:
        """Convert to Google Credentials object."""
        return Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GmailCredentials":
        """Create from dictionary."""
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
            scopes=data.get("scopes", [
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/gmail.send',
                'https://www.googleapis.com/auth/gmail.modify'
            ]),
            expiry=datetime.fromisoformat(data["expiry"]) if data.get("expiry") else None
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_uri": self.token_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scopes": self.scopes,
            "expiry": self.expiry.isoformat() if self.expiry else None
        }


# ============================================================================
# GMAIL MCP TOOL
# ============================================================================


class MCPGmailTool(EnhancedMCPTool):
    """
    Production-ready Gmail MCP tool with comprehensive API support.
    
    Features:
    - OAuth 2.0 with automatic token refresh
    - Full Gmail API v1 support
    - Rate limiting (250 QPS per user)
    - Attachment handling
    - MIME message construction
    - Comprehensive error handling
    - Multi-tenant credential isolation
    - Input validation and sanitization
    
    Usage:
        tool = MCPGmailTool()
        result = await tool.execute(
            tenant_id="tenant_123",
            operation="list_messages",
            params={"query": "is:unread", "max_results": 10}
        )
    """
    
    # Gmail API rate limits
    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=250.0,  # Per user limit
        burst_size=300,
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
    
    # Gmail API base URL
    GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
    
    def __init__(
        self,
        rate_limit_config: Optional[RateLimitConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        """Initialize Gmail MCP tool."""
        super().__init__(
            name="mcp_gmail",
            description="Gmail integration with OAuth 2.0, auto-refresh, and comprehensive API support",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.GMAIL_API_BASE,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )
        
        # Gmail-specific configuration
        self._service_cache: Dict[str, Any] = {}
        self._credentials_cache: Dict[str, GmailCredentials] = {}

    # ============================= Validation Schema =============================
    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        """Explicit parameter schemas for supported Gmail operations."""
        STR = str
        INT = int
        BOOL = bool
        LIST = list
        DICT = dict

        schemas: Dict[str, Dict[str, Any]] = {
            "list_messages": {
                "query": {"required": False, "type": STR},
                "max_results": {"required": False, "type": INT},
                "include_spam_trash": {"required": False, "type": BOOL},
                "label_ids": {"required": False, "type": LIST},
            },
            "get_message": {
                "message_id": {"required": True, "type": STR},
                "format": {"required": False, "type": STR},
            },
            "send_message": {
                "to": {"required": True, "type": (LIST,)},
                "subject": {"required": True, "type": STR},
                "from": {"required": False, "type": STR},
                "cc": {"required": False, "type": (LIST,)},
                "bcc": {"required": False, "type": (LIST,)},
                "reply_to": {"required": False, "type": STR},
                "text_body": {"required": False, "type": STR},
                "html_body": {"required": False, "type": STR},
                "attachments": {"required": False, "type": LIST},  # list of {filename, content_type, data}
                "thread_id": {"required": False, "type": STR},
            },
            "search_messages": {
                "query": {"required": False, "type": STR},
                "max_results": {"required": False, "type": INT},
                "include_details": {"required": False, "type": BOOL},
            },
            "get_thread": {
                "thread_id": {"required": True, "type": STR},
                "format": {"required": False, "type": STR},
            },
            "modify_message": {
                "message_id": {"required": True, "type": STR},
                "add_labels": {"required": False, "type": LIST},
                "remove_labels": {"required": False, "type": LIST},
            },
            "get_labels": {},
            "create_label": {
                "name": {"required": True, "type": STR},
                "label_list_visibility": {"required": False, "type": STR},
                "message_list_visibility": {"required": False, "type": STR},
            },
            "get_profile": {},
            "get_attachment": {
                "message_id": {"required": True, "type": STR},
                "attachment_id": {"required": True, "type": STR},
                "filename": {"required": False, "type": STR},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        """Classify Gmail writes to enforce confirm_action when applicable."""
        op = (operation or "").lower()
        write_ops = {"send_message", "modify_message", "create_label"}
        return op in write_ops or super()._is_write_operation(operation, params)
    
    async def _get_gmail_service(self, tenant_id: str):
        """Get authenticated Gmail service with auto-refresh."""
        # Check cache first
        if tenant_id in self._service_cache:
            service = self._service_cache[tenant_id]
            if service:
                return service
        
        # Get credentials with auto-refresh
        creds = await self._get_credentials_with_refresh(tenant_id)
        
        # Build service
        try:
            service = build('gmail', 'v1', credentials=creds.to_credentials())
            self._service_cache[tenant_id] = service
            return service
        except Exception as e:
            logger.error(f"Failed to build Gmail service for tenant {tenant_id}: {e}")
            raise InvalidCredentialsError(f"Failed to authenticate with Gmail: {e}")
    
    async def _get_credentials_with_refresh(self, tenant_id: str) -> GmailCredentials:
        """Get Gmail credentials with automatic refresh."""
        # Check cache first
        if tenant_id in self._credentials_cache:
            creds = self._credentials_cache[tenant_id]
            if not creds.needs_refresh():
                return creds
        
        # Get from secrets manager (prefer unified provider=google, fallback to legacy gmail)
        try:
            creds_data = None
            # Try unified provider first
            try:
                unified = await self.secrets_manager.get_secret(
                    tenant_id=tenant_id,
                    service_name="google",
                    key_type="oauth_tokens",
                )
                if isinstance(unified, dict) and unified.get("access_token"):
                    creds_data = unified
            except Exception:
                pass

            # Legacy fallback
            if not creds_data:
                legacy = await self.secrets_manager.get_secret(
                    tenant_id=tenant_id,
                    service_name="gmail",
                    key_type="oauth_credentials",
                )
                creds_data = legacy
            
            creds = GmailCredentials.from_dict(creds_data)
            
            # Refresh if needed
            if creds.needs_refresh():
                creds = await self._refresh_gmail_token(tenant_id, creds)
                # Save refreshed credentials
                try:
                    # Persist to unified provider store
                    await self.secrets_manager.set_secret(
                        tenant_id=tenant_id,
                        service_name="google",
                        key_type="oauth_tokens",
                        secret_value=creds.to_dict(),
                    )
                except Exception:
                    # Fallback persist to legacy location
                    await self.secrets_manager.set_secret(
                        tenant_id=tenant_id,
                        service_name="gmail",
                        key_type="oauth_credentials",
                        secret_value=creds.to_dict(),
                    )
            
            # Cache credentials
            self._credentials_cache[tenant_id] = creds
            return creds
            
        except Exception as e:
            logger.error(f"Failed to get Gmail credentials for tenant {tenant_id}: {e}")
            raise InvalidCredentialsError(f"Gmail credentials not found or invalid: {e}")
    
    async def _refresh_gmail_token(self, tenant_id: str, creds: GmailCredentials) -> GmailCredentials:
        """Refresh Gmail OAuth token."""
        try:
            # Create credentials object
            google_creds = creds.to_credentials()
            
            # Refresh if expired
            if google_creds.expired and google_creds.refresh_token:
                google_creds.refresh(Request())
                
                # Update credentials
                creds.access_token = google_creds.token
                creds.expiry = google_creds.expiry
                
                logger.info(f"Refreshed Gmail token for tenant {tenant_id}")
                return creds
            else:
                return creds
                
        except Exception as e:
            logger.error(f"Failed to refresh Gmail token for tenant {tenant_id}: {e}")
            raise InvalidCredentialsError(f"Token refresh failed: {e}")
    
    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        """Execute Gmail operation."""
        try:
            # Get authenticated service
            service = await self._get_gmail_service(tenant_id)
            
            # Route to specific operation
            if operation == "list_messages":
                return await self._handle_list_messages(service, params)
            elif operation == "get_message":
                return await self._handle_get_message(service, params)
            elif operation == "send_message":
                return await self._handle_send_message(service, params)
            elif operation == "search_messages":
                return await self._handle_search_messages(service, params)
            elif operation == "get_thread":
                return await self._handle_get_thread(service, params)
            elif operation == "modify_message":
                return await self._handle_modify_message(service, params)
            elif operation == "get_labels":
                return await self._handle_get_labels(service, params)
            elif operation == "create_label":
                return await self._handle_create_label(service, params)
            elif operation == "get_profile":
                return await self._handle_get_profile(service, params)
            elif operation == "get_attachment":
                return await self._handle_get_attachment(service, params)
            else:
                raise ValidationError(f"Unsupported operation: {operation}")
                
        except HttpError as e:
            if e.resp.status == 429:
                raise RateLimitError(f"Gmail API rate limit exceeded: {e}")
            elif e.resp.status == 403:
                if "quota" in str(e).lower():
                    raise QuotaExceededError(f"Gmail API quota exceeded: {e}")
                else:
                    raise InvalidCredentialsError(f"Gmail API access denied: {e}")
            elif e.resp.status == 500:
                # Google 500s are transient - retry with exponential backoff
                raise NetworkError(f"Gmail API internal server error (transient): {e}", retry_after=5)
            elif e.resp.status >= 500:
                raise NetworkError(f"Gmail API server error: {e}")
            else:
                raise ValidationError(f"Gmail API error: {e}")
        except Exception as e:
            logger.error(f"Gmail operation {operation} failed: {e}")
            raise
    
    # ========================================================================
    # GMAIL API OPERATIONS
    # ========================================================================
    
    async def _handle_list_messages(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """List messages with optional filtering."""
        try:
            # Build query parameters
            query_params = {
                'userId': 'me',
                'q': params.get('query', ''),
                'maxResults': min(params.get('max_results', 100), 500),
                'includeSpamTrash': params.get('include_spam_trash', False)
            }
            
            # Add label IDs if provided
            if 'label_ids' in params:
                query_params['labelIds'] = params['label_ids']
            
            # Execute API call
            results = service.users().messages().list(**query_params).execute()
            
            return MCPToolResult(
                success=True,
                data={
                    'messages': results.get('messages', []),
                    'next_page_token': results.get('nextPageToken'),
                    'result_size_estimate': results.get('resultSizeEstimate', 0)
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to list messages: {e}")
            raise
    
    async def _handle_get_message(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Get detailed message information."""
        try:
            message_id = params['message_id']
            format_type = params.get('format', 'full')  # full, minimal, raw, metadata
            
            # Build query parameters
            query_params = {
                'userId': 'me',
                'id': message_id,
                'format': format_type
            }
            
            # Execute API call
            message = service.users().messages().get(**query_params).execute()
            
            return MCPToolResult(
                success=True,
                data={'message': message}
            )
            
        except Exception as e:
            logger.error(f"Failed to get message {params.get('message_id')}: {e}")
            raise
    
    async def _handle_send_message(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Send email message."""
        try:
            # Build MIME message
            message = self._build_mime_message(params)
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Build request body
            body = {'raw': raw_message}
            
            # Add thread ID if replying
            if 'thread_id' in params:
                body['threadId'] = params['thread_id']
            
            # Execute API call
            result = service.users().messages().send(
                userId='me',
                body=body
            ).execute()
            
            return MCPToolResult(
                success=True,
                data={
                    'message_id': result['id'],
                    'thread_id': result['threadId'],
                    'label_ids': result.get('labelIds', [])
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise
    
    async def _handle_search_messages(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Search messages with Gmail search syntax."""
        try:
            # Build search query
            query = params.get('query', '')
            max_results = min(params.get('max_results', 10), 500)
            
            # Execute search
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            # Get detailed message info if requested
            messages = results.get('messages', [])
            if params.get('include_details', False) and messages:
                detailed_messages = []
                for msg in messages[:10]:  # Limit to 10 for performance
                    try:
                        detail = service.users().messages().get(
                            userId='me',
                            id=msg['id'],
                            format='metadata',
                            metadataHeaders=['From', 'To', 'Subject', 'Date']
                        ).execute()
                        detailed_messages.append(detail)
                    except Exception as e:
                        logger.warning(f"Failed to get details for message {msg['id']}: {e}")
                        detailed_messages.append(msg)
                
                return MCPToolResult(
                    success=True,
                    data={
                        'messages': detailed_messages,
                        'next_page_token': results.get('nextPageToken'),
                        'result_size_estimate': results.get('resultSizeEstimate', 0)
                    }
                )
            else:
                return MCPToolResult(
                    success=True,
                    data={
                        'messages': messages,
                        'next_page_token': results.get('nextPageToken'),
                        'result_size_estimate': results.get('resultSizeEstimate', 0)
                    }
                )
                
        except Exception as e:
            logger.error(f"Failed to search messages: {e}")
            raise
    
    async def _handle_get_thread(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Get email thread."""
        try:
            thread_id = params['thread_id']
            format_type = params.get('format', 'full')
            
            # Execute API call
            thread = service.users().threads().get(
                userId='me',
                id=thread_id,
                format=format_type
            ).execute()
            
            return MCPToolResult(
                success=True,
                data={'thread': thread}
            )
            
        except Exception as e:
            logger.error(f"Failed to get thread {params.get('thread_id')}: {e}")
            raise
    
    async def _handle_modify_message(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Modify message (add/remove labels, mark as read/unread)."""
        try:
            message_id = params['message_id']
            add_labels = params.get('add_labels', [])
            remove_labels = params.get('remove_labels', [])
            
            # Build request body
            body = {}
            if add_labels:
                body['addLabelIds'] = add_labels
            if remove_labels:
                body['removeLabelIds'] = remove_labels
            
            # Execute API call
            result = service.users().messages().modify(
                userId='me',
                id=message_id,
                body=body
            ).execute()
            
            return MCPToolResult(
                success=True,
                data={
                    'message_id': result['id'],
                    'thread_id': result['threadId'],
                    'label_ids': result.get('labelIds', [])
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to modify message {params.get('message_id')}: {e}")
            raise
    
    async def _handle_get_labels(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Get Gmail labels."""
        try:
            # Execute API call
            labels = service.users().labels().list(userId='me').execute()
            
            return MCPToolResult(
                success=True,
                data={'labels': labels.get('labels', [])}
            )
            
        except Exception as e:
            logger.error(f"Failed to get labels: {e}")
            raise
    
    async def _handle_create_label(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Create new Gmail label."""
        try:
            name = params['name']
            label_list_visibility = params.get('label_list_visibility', 'labelShow')
            message_list_visibility = params.get('message_list_visibility', 'show')
            
            # Build label object
            label = {
                'name': name,
                'labelListVisibility': label_list_visibility,
                'messageListVisibility': message_list_visibility
            }
            
            # Execute API call
            result = service.users().labels().create(
                userId='me',
                body=label
            ).execute()
            
            return MCPToolResult(
                success=True,
                data={'label': result}
            )
            
        except Exception as e:
            logger.error(f"Failed to create label: {e}")
            raise
    
    async def _handle_get_profile(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Get Gmail profile information."""
        try:
            # Execute API call
            profile = service.users().getProfile(userId='me').execute()
            
            return MCPToolResult(
                success=True,
                data={'profile': profile}
            )
            
        except Exception as e:
            logger.error(f"Failed to get profile: {e}")
            raise
    
    async def _handle_get_attachment(self, service, params: Dict[str, Any]) -> MCPToolResult:
        """Get message attachment."""
        try:
            message_id = params['message_id']
            attachment_id = params['attachment_id']
            
            # Execute API call
            attachment = service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()
            
            # Decode attachment data
            file_data = base64.urlsafe_b64decode(attachment['data'])
            
            return MCPToolResult(
                success=True,
                data={
                    'attachment_id': attachment_id,
                    'size': attachment.get('size', 0),
                    'data': file_data,
                    'filename': params.get('filename', f'attachment_{attachment_id}')
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to get attachment: {e}")
            raise
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _build_mime_message(self, params: Dict[str, Any]) -> MIMEMultipart:
        """Build MIME message from parameters."""
        # Create message
        msg = MIMEMultipart('alternative')
        
        # Set headers
        msg['To'] = params.get('to', '')
        msg['From'] = params.get('from', '')
        msg['Subject'] = params.get('subject', '')
        
        # Add CC and BCC if provided
        if 'cc' in params:
            msg['Cc'] = params['cc']
        if 'bcc' in params:
            msg['Bcc'] = params['bcc']
        
        # Add Reply-To if provided
        if 'reply_to' in params:
            msg['Reply-To'] = params['reply_to']
        
        # Add text content
        if 'text_body' in params:
            text_part = MIMEText(params['text_body'], 'plain', 'utf-8')
            msg.attach(text_part)
        
        # Add HTML content
        if 'html_body' in params:
            html_part = MIMEText(params['html_body'], 'html', 'utf-8')
            msg.attach(html_part)
        
        # Add attachments
        if 'attachments' in params:
            for attachment in params['attachments']:
                self._add_attachment(msg, attachment)
        
        return msg
    
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]) -> None:
        """Add attachment to MIME message."""
        try:
            filename = attachment.get('filename', 'attachment')
            content_type = attachment.get('content_type', 'application/octet-stream')
            data = attachment.get('data', b'')
            
            # Create attachment
            part = MIMEBase(*content_type.split('/'))
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{filename}"'
            )
            
            msg.attach(part)
            
        except Exception as e:
            logger.warning(f"Failed to add attachment {attachment.get('filename', 'unknown')}: {e}")
    
    def _validate_operation_params(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate operation parameters."""
        # Common validations
        if 'max_results' in params:
            params['max_results'] = min(max(params['max_results'], 1), 500)
        
        if 'query' in params:
            params['query'] = str(params['query'])[:1000]  # Limit query length
        
        # Operation-specific validations
        if operation == "get_message":
            if 'message_id' not in params:
                raise ValidationError("message_id is required for get_message operation")
        
        elif operation == "send_message":
            required_fields = ['to', 'subject']
            for field in required_fields:
                if field not in params:
                    raise ValidationError(f"{field} is required for send_message operation")
            
            # Validate email addresses
            if 'to' in params:
                if isinstance(params['to'], str):
                    params['to'] = [params['to']]
                for email in params['to']:
                    if '@' not in email:
                        raise ValidationError(f"Invalid email address: {email}")
        
        elif operation == "get_thread":
            if 'thread_id' not in params:
                raise ValidationError("thread_id is required for get_thread operation")
        
        elif operation == "modify_message":
            if 'message_id' not in params:
                raise ValidationError("message_id is required for modify_message operation")
        
        elif operation == "create_label":
            if 'name' not in params:
                raise ValidationError("name is required for create_label operation")
        
        elif operation == "get_attachment":
            if 'message_id' not in params or 'attachment_id' not in params:
                raise ValidationError("message_id and attachment_id are required for get_attachment operation")
        
        return params


# ============================================================================
# EXPORT
# ============================================================================

__all__ = ['MCPGmailTool', 'GmailCredentials']
