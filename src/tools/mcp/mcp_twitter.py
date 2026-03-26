"""
Twitter (X) MCP Tool - Production-Ready (Core Operations)

Supports:
- Bearer token (App-only) or OAuth 2.0 user context with refresh
- Core operations: get_tweet, create_tweet, search_tweets
- Rate limiting, retries, circuit breaker via EnhancedMCPTool

Official Docs:
- Base URL: https://api.x.com/2
- OAuth 2.0: https://developer.x.com/en/docs/authentication/oauth-2-0

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
class TwitterOAuthCredentials:
    access_token: str
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    token_uri: str = "https://api.x.com/2/oauth2/token"
    expires_at: Optional[datetime] = None
    expires_in: int = 7200  # 2 hours

    def needs_refresh(self) -> bool:
        if not self.expires_at:
            return bool(self.refresh_token)
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TwitterOAuthCredentials":
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
            token_uri=data.get("token_uri", "https://api.x.com/2/oauth2/token"),
            expires_at=expires_at,
            expires_in=int(data.get("expires_in", 7200)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "token_uri": self.token_uri,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "expires_in": self.expires_in,
        }


class MCPTwitterTool(EnhancedMCPTool):
    """Twitter (X) MCP Tool with core tweet operations."""

    API_BASE = "https://api.x.com/2"

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
        tenant_id: Optional[int] = None,
        job_id: Optional[str] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ) -> None:
        super().__init__(
            name="mcp_twitter",
            description="Twitter (X) operations: get_tweet, create_tweet, search_tweets",
            auth_type=AuthType.BEARER_TOKEN,
            base_url=self.API_BASE,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )
        self._oauth_cache: Dict[str, TwitterOAuthCredentials] = {}

    def list_operations(self, max_ops: int = 50):
        ops = ["get_tweet", "create_tweet", "search_tweets"]
        return ops[: max(0, int(max_ops or 0))] if max_ops is not None else ops

    # ============================= Validation =============================
    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        if operation == "get_tweet":
            return {"tweet_id": {"required": True, "type": str, "max_length": 40}}
        if operation == "create_tweet":
            return {"text": {"required": True, "type": str, "max_length": 280}}
        if operation == "search_tweets":
            return {
                "query": {"required": True, "type": str, "max_length": 512},
                "max_results": {"required": False, "type": int},
            }
        return None

    # ============================= Execution =============================
    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        try:
            headers = await self._get_twitter_headers(tenant_id)

            if operation == "get_tweet":
                tweet_id = params["tweet_id"]
                url = f"{self.API_BASE}/tweets/{tweet_id}"
                data = await self._make_request(
                    HttpMethod.GET,
                    url,
                    headers=headers,
                    params={"tweet.fields": "created_at,author_id,public_metrics"},
                )
                return MCPToolResult(success=True, data=data)

            if operation == "create_tweet":
                url = f"{self.API_BASE}/tweets"
                payload = {"text": params["text"]}
                data = await self._make_request(HttpMethod.POST, url, headers=headers, json_data=payload)
                return MCPToolResult(success=True, data=data)

            if operation == "search_tweets":
                url = f"{self.API_BASE}/tweets/search/recent"
                max_results = min(max(int(params.get("max_results", 10)), 10), 100)
                data = await self._make_request(
                    HttpMethod.GET,
                    url,
                    headers=headers,
                    params={"query": params["query"], "max_results": max_results},
                )
                return MCPToolResult(success=True, data=data)

            raise ValidationError(f"Unsupported operation: {operation}")

        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                raise InvalidCredentialsError(f"Twitter authentication failed: {e}")
            elif e.status == 429:
                retry_after = int(e.headers.get("Retry-After", "60"))
                raise RateLimitError("Twitter rate limit exceeded", retry_after=retry_after)
            elif e.status >= 500:
                raise NetworkError(f"Twitter server error: {e}")
            else:
                raise MCPToolError(f"Twitter API error: HTTP {e.status}")
        except Exception as e:
            logger.error(f"Twitter operation {operation} failed: {e}")
            raise

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        write_ops = {"create_tweet"}
        return op in write_ops or super()._is_write_operation(operation, params)

    # ============================= Auth =============================
    async def _get_twitter_headers(self, tenant_id: str) -> Dict[str, str]:
        # Prefer OAuth credentials if present (user context)
        creds_data: Optional[Dict[str, Any]]
        try:
            creds_data = await self.secrets_manager.get_secret(
                tenant_id=tenant_id,
                service_name="twitter",
                key_type="oauth_credentials",
            )
        except Exception:
            creds_data = None

        if creds_data:
            creds = self._oauth_cache.get(tenant_id) or TwitterOAuthCredentials.from_dict(creds_data)
            if creds.needs_refresh():
                creds = await self._refresh_oauth_token(creds)
                await self.secrets_manager.set_secret(
                    tenant_id=tenant_id,
                    service_name="twitter",
                    key_type="oauth_credentials",
                    secret_value=creds.to_dict(),
                )
            self._oauth_cache[tenant_id] = creds
            return {"Authorization": f"Bearer {creds.access_token}", "Content-Type": "application/json"}

        # Fallback to app-only bearer token
        token = await self.secrets_manager.get_secret(
            tenant_id=tenant_id, service_name="twitter", key_type="bearer_token"
        )
        if not token:
            raise InvalidCredentialsError("Twitter credentials not found for tenant")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def _refresh_oauth_token(self, creds: TwitterOAuthCredentials) -> TwitterOAuthCredentials:
        if not creds.refresh_token or not creds.client_id:
            raise InvalidCredentialsError("Missing Twitter refresh credentials")
        session = await self._get_session()
        data = {
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": creds.client_id,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with session.post(creds.token_uri, data=data, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise InvalidCredentialsError(f"Twitter token refresh failed: HTTP {resp.status} {text[:200]}")
            token_json = await resp.json()
            new_access = token_json.get("access_token")
            expires_in = int(token_json.get("expires_in", 7200))
            if not new_access:
                raise InvalidCredentialsError("Twitter token refresh did not return access_token")
            creds.access_token = new_access
            creds.expires_in = expires_in
            creds.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            if token_json.get("refresh_token"):
                creds.refresh_token = token_json["refresh_token"]
            return creds
