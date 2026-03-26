"""
Instagram MCP Tool - Production-Ready (Graph API, Long-Lived Tokens)

Supports:
- Long-lived access tokens (60 days) with refresh after 24h (per docs)
- Core operations: get_user_profile, get_media, create_media_container, publish_media
- Rate limiting, retries, circuit breaker via EnhancedMCPTool

Official Docs:
- Graph API: https://graph.instagram.com
- Auth & Long-Lived Tokens: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login

Author: Etherion AI Platform Team
Version: 1.0.0
"""

from __future__ import annotations

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


@dataclass
class InstagramCredentials:
    access_token: str
    expires_in: int
    issued_at: Optional[datetime] = None
    app_secret: Optional[str] = None  # not needed for refresh endpoint, kept for future

    def needs_refresh(self) -> bool:
        # Refresh allowed after 24h; proactively refresh if older than 24h or within 3 days of expiry
        if not self.issued_at:
            return True
        age = datetime.utcnow() - self.issued_at
        # 60 days ≈ 5,184,000 seconds; refresh once age >= 24h
        return age >= timedelta(hours=24)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstagramCredentials":
        issued_at = None
        if isinstance(data.get("issued_at"), str):
            try:
                issued_at = datetime.fromisoformat(data["issued_at"])  # type: ignore[arg-type]
            except Exception:
                issued_at = None
        elif isinstance(data.get("issued_at"), datetime):
            issued_at = data["issued_at"]

        return cls(
            access_token=data.get("access_token", ""),
            expires_in=int(data.get("expires_in", 5184000)),
            issued_at=issued_at,
            app_secret=data.get("app_secret"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "expires_in": self.expires_in,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "app_secret": self.app_secret,
        }


class MCPInstagramTool(EnhancedMCPTool):
    """Instagram MCP Tool with long-lived token refresh and core media ops."""

    GRAPH_BASE = "https://graph.instagram.com"

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=2.0,
        requests_per_minute=120.0,
        requests_per_hour=6000.0,
        burst_size=5,
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
            name="mcp_instagram",
            description="Instagram Graph API: profile, media, create container, publish",
            auth_type=AuthType.BEARER_TOKEN,
            base_url=self.GRAPH_BASE,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )
        self._creds_cache: Dict[str, InstagramCredentials] = {}

    # ============================= Validation =============================
    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        if operation == "get_user_profile":
            return {"user_id": {"required": True, "type": str, "max_length": 32}}
        if operation == "get_media":
            return {"user_id": {"required": True, "type": str, "max_length": 32}}
        if operation == "create_media_container":
            return {
                "user_id": {"required": True, "type": str, "max_length": 32},
                "image_url": {"required": True, "type": str, "max_length": 2048},
                "caption": {"required": False, "type": str, "max_length": 2200},
            }
        if operation == "publish_media":
            return {
                "user_id": {"required": True, "type": str, "max_length": 32},
                "creation_id": {"required": True, "type": str, "max_length": 64},
            }
        return None

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        write_ops = {"create_media_container", "publish_media"}
        return op in write_ops or super()._is_write_operation(operation, params)

    # ============================= Execution =============================
    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        try:
            access_token = await self._get_valid_access_token(tenant_id)

            if operation == "get_user_profile":
                url = f"{self.GRAPH_BASE}/{params['user_id']}"
                data = await self._make_request(
                    HttpMethod.GET,
                    url,
                    params={"fields": "id,username,account_type,media_count", "access_token": access_token},
                )
                return MCPToolResult(success=True, data=data)

            if operation == "get_media":
                url = f"{self.GRAPH_BASE}/{params['user_id']}/media"
                data = await self._make_request(
                    HttpMethod.GET,
                    url,
                    params={
                        "fields": "id,caption,media_type,media_url,timestamp",
                        "access_token": access_token,
                    },
                )
                return MCPToolResult(success=True, data=data)

            if operation == "create_media_container":
                url = f"{self.GRAPH_BASE}/{params['user_id']}/media"
                data = await self._make_request(
                    HttpMethod.POST,
                    url,
                    params={
                        "image_url": params["image_url"],
                        "caption": params.get("caption"),
                        "access_token": access_token,
                    },
                )
                return MCPToolResult(success=True, data=data)

            if operation == "publish_media":
                url = f"{self.GRAPH_BASE}/{params['user_id']}/media_publish"
                data = await self._make_request(
                    HttpMethod.POST,
                    url,
                    params={
                        "creation_id": params["creation_id"],
                        "access_token": access_token,
                    },
                )
                return MCPToolResult(success=True, data=data)

            raise ValidationError(f"Unsupported operation: {operation}")

        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                raise InvalidCredentialsError(f"Instagram authentication failed: {e}")
            elif e.status == 429:
                retry_after = int(e.headers.get("Retry-After", "60"))
                raise RateLimitError("Instagram rate limit exceeded", retry_after=retry_after)
            elif e.status >= 500:
                raise NetworkError(f"Instagram server error: {e}")
            else:
                raise MCPToolError(f"Instagram API error: HTTP {e.status}")
        except Exception as e:
            logger.error(f"Instagram operation {operation} failed: {e}")
            raise

    # ============================= Auth & Refresh =============================
    async def _get_valid_access_token(self, tenant_id: str) -> str:
        creds = self._creds_cache.get(tenant_id)
        if not creds:
            try:
                creds_data = await self.secrets_manager.get_secret(
                    tenant_id=tenant_id,
                    service_name="instagram",
                    key_type="access_token_bundle",
                )
            except Exception as e:
                raise InvalidCredentialsError(f"Instagram credentials not found: {e}")
            creds = InstagramCredentials.from_dict(creds_data)

        if creds.needs_refresh():
            creds = await self._refresh_long_lived_token(creds)
            creds.issued_at = datetime.utcnow()
            await self.secrets_manager.set_secret(
                tenant_id=tenant_id,
                service_name="instagram",
                key_type="access_token_bundle",
                secret_value=creds.to_dict(),
            )

        self._creds_cache[tenant_id] = creds
        return creds.access_token

    async def _refresh_long_lived_token(self, creds: InstagramCredentials) -> InstagramCredentials:
        url = f"{self.GRAPH_BASE}/refresh_access_token"
        params = {"grant_type": "ig_refresh_token", "access_token": creds.access_token}
        session = await self._get_session()
        async with session.get(url, params=params) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise InvalidCredentialsError(f"Instagram token refresh failed: HTTP {resp.status} {text[:200]}")
            data = await resp.json()
            new_access = data.get("access_token")
            expires_in = int(data.get("expires_in", 5184000))
            if not new_access:
                raise InvalidCredentialsError("Instagram refresh did not return access_token")
            creds.access_token = new_access
            creds.expires_in = expires_in
            return creds


