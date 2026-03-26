"""
HubSpot MCP Tool - Production-Ready (Core Contacts Operations)

Supports:
- Authentication via Private App access token OR OAuth 2.0 with refresh
- Contacts: get_contact, create_contact, search_contacts, update_contact, delete_contact
- Rate limiting, retries, and circuit breaker via EnhancedMCPTool

Official Docs:
- Base URL: https://api.hubapi.com
- Private Apps: https://developers.hubspot.com/docs/api/private-apps
- OAuth: https://developers.hubspot.com/docs/api/oauth
- Contacts: https://developers.hubspot.com/docs/api/crm/contacts

Author: Etherion AI Platform Team
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import aiohttp

from .base_mcp_tool import (
    EnhancedMCPTool,
    MCPToolResult,
    RateLimitConfig,
    RetryConfig,
    CircuitBreakerConfig,
    InvalidCredentialsError,
    ValidationError,
    RateLimitError,
    NetworkError,
    MCPToolError,
    AuthType,
    HttpMethod,
)


logger = logging.getLogger(__name__)


# =====================================================================================
# CREDENTIALS MODEL
# =====================================================================================


@dataclass
class HubSpotOAuthCredentials:
    """HubSpot OAuth 2.0 credentials with refresh support."""

    access_token: str
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_uri: str = "https://api.hubapi.com/oauth/v1/token"
    expires_at: Optional[datetime] = None
    expires_in: int = 6 * 60 * 60  # 6 hours default
    scopes: Optional[Any] = None

    def needs_refresh(self) -> bool:
        if not self.expires_at:
            # If we do not know expiry but have refresh_token, attempt refresh proactively
            return bool(self.refresh_token)
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HubSpotOAuthCredentials":
        exp = data.get("expires_at")
        if isinstance(exp, str):
            try:
                expires_at = datetime.fromisoformat(exp)
            except Exception:
                expires_at = None
        elif isinstance(exp, datetime):
            expires_at = exp
        else:
            expires_at = None

        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            token_uri=data.get("token_uri", "https://api.hubapi.com/oauth/v1/token"),
            expires_at=expires_at,
            expires_in=int(data.get("expires_in", 6 * 60 * 60)),
            scopes=data.get("scopes"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "token_uri": self.token_uri,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "expires_in": self.expires_in,
            "scopes": self.scopes,
        }


# =====================================================================================
# HUBSPOT MCP TOOL
# =====================================================================================


class MCPHubSpotTool(EnhancedMCPTool):
    """HubSpot MCP Tool with core CRM contacts operations."""

    API_BASE = "https://api.hubapi.com"

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=8.0,  # default 100 per 10s → 10 r/s; keep conservative
        requests_per_minute=400.0,
        requests_per_hour=20000.0,
        burst_size=12,
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
        success_threshold=2,
        timeout=60.0,
        half_open_max_calls=1,
    )

    def __init__(
        self,
        rate_limit_config: Optional[RateLimitConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ) -> None:
        super().__init__(
            name="mcp_hubspot",
            description="HubSpot CRM contacts operations",
            auth_type=AuthType.BEARER_TOKEN,
            base_url=self.API_BASE,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )

        self._oauth_cache: Dict[str, HubSpotOAuthCredentials] = {}

    # ============================= Validation Schema =============================
    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        if operation == "get_contact":
            return {"contact_id": {"required": True, "type": str, "max_length": 128}}
        if operation == "create_contact":
            return {"properties": {"required": True, "type": dict}}
        if operation == "search_contacts":
            return {
                "filters": {"required": True, "type": list},
                "limit": {"required": False, "type": int},
            }
        if operation == "update_contact":
            return {
                "contact_id": {"required": True, "type": str, "max_length": 128},
                "properties": {"required": True, "type": dict},
            }
        if operation == "delete_contact":
            return {"contact_id": {"required": True, "type": str, "max_length": 128}}
        return None

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        write_ops = {"create_contact", "update_contact", "delete_contact"}
        return op in write_ops or super()._is_write_operation(operation, params)

    # ============================= Execution Router =============================
    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        try:
            headers = await self._get_hubspot_headers(tenant_id)

            if operation == "get_contact":
                return await self._handle_get_contact(headers, params)
            if operation == "create_contact":
                return await self._handle_create_contact(headers, params)
            if operation == "search_contacts":
                return await self._handle_search_contacts(headers, params)
            if operation == "update_contact":
                return await self._handle_update_contact(headers, params)
            if operation == "delete_contact":
                return await self._handle_delete_contact(headers, params)

            raise ValidationError(f"Unsupported operation: {operation}")

        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                raise InvalidCredentialsError(f"HubSpot authentication failed: {e}")
            elif e.status == 429:
                retry_after = int(e.headers.get("Retry-After", "10"))
                raise RateLimitError("HubSpot rate limit exceeded", retry_after=retry_after)
            elif e.status >= 500:
                raise NetworkError(f"HubSpot server error: {e}")
            else:
                raise MCPToolError(f"HubSpot API error: HTTP {e.status}")
        except Exception as e:
            logger.error(f"HubSpot operation {operation} failed: {e}")
            raise

    # ============================= Auth Helpers =============================
    async def _get_hubspot_headers(self, tenant_id: str) -> Dict[str, str]:
        """Get auth headers. Prefer OAuth credentials with refresh; fallback to private app token."""
        # Try OAuth credentials first
        try:
            creds_data = await self.secrets_manager.get_secret(
                tenant_id=tenant_id,
                service_name="hubspot",
                key_type="oauth_credentials",
            )
        except Exception:
            creds_data = None

        if creds_data:
            creds = self._oauth_cache.get(tenant_id) or HubSpotOAuthCredentials.from_dict(creds_data)
            if creds.needs_refresh():
                creds = await self._refresh_oauth_token(tenant_id, creds)
                await self.secrets_manager.set_secret(
                    tenant_id=tenant_id,
                    service_name="hubspot",
                    key_type="oauth_credentials",
                    secret_value=creds.to_dict(),
                )
            self._oauth_cache[tenant_id] = creds
            return {"Authorization": f"Bearer {creds.access_token}", "Content-Type": "application/json"}

        # Fallback: Private app access token
        token = await self.secrets_manager.get_secret(
            tenant_id=tenant_id, service_name="hubspot", key_type="access_token"
        )
        if not token:
            raise InvalidCredentialsError("HubSpot credentials not found for tenant")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def _refresh_oauth_token(self, tenant_id: str, creds: HubSpotOAuthCredentials) -> HubSpotOAuthCredentials:
        if not creds.refresh_token or not creds.client_id or not creds.client_secret:
            raise InvalidCredentialsError("Missing refresh credentials for HubSpot OAuth")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        }
        session = await self._get_session()
        async with session.post(creds.token_uri, data=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise InvalidCredentialsError(f"HubSpot token refresh failed: HTTP {resp.status} {text[:200]}")
            data = await resp.json()
            access = data.get("access_token")
            if not access:
                raise InvalidCredentialsError("HubSpot token refresh did not return access_token")
            creds.access_token = access
            expires_in = int(data.get("expires_in", 6 * 60 * 60))
            creds.expires_in = expires_in
            creds.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            if data.get("refresh_token"):
                creds.refresh_token = data["refresh_token"]
            return creds

    # ============================= Handlers =============================
    async def _handle_get_contact(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        contact_id = params["contact_id"]
        url = f"{self.API_BASE}/crm/v3/objects/contacts/{contact_id}"
        data = await self._make_request(HttpMethod.GET, url, headers=headers)
        return MCPToolResult(success=True, data=data)

    async def _handle_create_contact(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        url = f"{self.API_BASE}/crm/v3/objects/contacts"
        body = {"properties": params["properties"]}
        data = await self._make_request(HttpMethod.POST, url, headers=headers, json_data=body)
        return MCPToolResult(success=True, data=data)

    async def _handle_search_contacts(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        url = f"{self.API_BASE}/crm/v3/objects/contacts/search"
        body = {"filterGroups": params["filters"], "limit": int(params.get("limit", 100))}
        data = await self._make_request(HttpMethod.POST, url, headers=headers, json_data=body)
        return MCPToolResult(success=True, data=data)

    async def _handle_update_contact(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        contact_id = params["contact_id"]
        url = f"{self.API_BASE}/crm/v3/objects/contacts/{contact_id}"
        body = {"properties": params["properties"]}
        data = await self._make_request(HttpMethod.PATCH, url, headers=headers, json_data=body)
        return MCPToolResult(success=True, data=data)

    async def _handle_delete_contact(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        contact_id = params["contact_id"]
        url = f"{self.API_BASE}/crm/v3/objects/contacts/{contact_id}"
        data = await self._make_request(HttpMethod.DELETE, url, headers=headers)
        return MCPToolResult(success=True, data=data)
