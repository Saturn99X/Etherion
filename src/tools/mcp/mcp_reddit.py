"""
Reddit MCP Tool - Production-Ready (Core Operations)

Supports:
- OAuth 2.0 (authorization code/refresh) bearer tokens
- Required custom User-Agent header
- Core operations: get_user_info, get_subreddit_posts, submit_post, get_comments, vote
- Rate limiting, retries, and circuit breaker via EnhancedMCPTool

Official Docs:
- OAuth: https://github.com/reddit-archive/reddit/wiki/OAuth2
- API: https://www.reddit.com/dev/api/

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


@dataclass
class RedditOAuthCredentials:
    access_token: str
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    expires_at: Optional[datetime] = None
    expires_in: int = 3600

    def needs_refresh(self) -> bool:
        if not self.expires_at:
            return bool(self.refresh_token)
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RedditOAuthCredentials":
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
            expires_at=expires_at,
            expires_in=int(data.get("expires_in", 3600)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "expires_in": self.expires_in,
        }


class MCPRedditTool(EnhancedMCPTool):
    """Reddit MCP Tool with required User-Agent and OAuth refresh."""

    API_BASE = "https://oauth.reddit.com"
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

    # Provide a descriptive, compliant User-Agent per Reddit policy
    USER_AGENT = "Etherion-MCP-Reddit/1.0.0 (by u/etherionai)"

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=1.0,
        requests_per_minute=60.0,
        requests_per_hour=3000.0,
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
            name="mcp_reddit",
            description="Reddit API operations (me, posts, submit, comments, vote)",
            auth_type=AuthType.BEARER_TOKEN,
            base_url=self.API_BASE,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )
        self._oauth_cache: Dict[str, RedditOAuthCredentials] = {}

    # ============================= Validation =============================
    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        if operation == "get_user_info":
            return {}
        if operation == "get_subreddit_posts":
            return {
                "subreddit": {"required": True, "type": str, "max_length": 100},
                "sort": {"required": False, "type": str, "max_length": 20},
                "limit": {"required": False, "type": int},
            }
        if operation == "submit_post":
            return {
                "subreddit": {"required": True, "type": str, "max_length": 100},
                "title": {"required": True, "type": str, "max_length": 300},
                "kind": {"required": False, "type": str, "max_length": 10},
                "text": {"required": False, "type": str},
                "url": {"required": False, "type": str, "max_length": 2000},
            }
        if operation == "get_comments":
            return {
                "subreddit": {"required": True, "type": str, "max_length": 100},
                "article_id": {"required": True, "type": str, "max_length": 50},
            }
        if operation == "vote":
            return {
                "thing_id": {"required": True, "type": str, "max_length": 15},
                "direction": {"required": True, "type": int},  # 1, -1, 0
            }
        return None

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        write_ops = {"submit_post", "vote"}
        return op in write_ops or super()._is_write_operation(operation, params)

    # ============================= Execution =============================
    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        try:
            headers = await self._get_reddit_headers(tenant_id)

            if operation == "get_user_info":
                url = f"{self.API_BASE}/api/v1/me"
                data = await self._make_request(HttpMethod.GET, url, headers=headers)
                return MCPToolResult(success=True, data=data)

            if operation == "get_subreddit_posts":
                subreddit = params["subreddit"]
                sort = params.get("sort", "hot")
                limit = min(max(int(params.get("limit", 25)), 1), 100)
                url = f"{self.API_BASE}/r/{subreddit}/{sort}"
                data = await self._make_request(
                    HttpMethod.GET,
                    url,
                    headers=headers,
                    params={"limit": limit},
                )
                return MCPToolResult(success=True, data=data)

            if operation == "submit_post":
                url = f"{self.API_BASE}/api/submit"
                body = {
                    "sr": params["subreddit"],
                    "kind": params.get("kind", "self"),
                    "title": params["title"],
                    "api_type": "json",
                }
                if body["kind"] == "self" and params.get("text") is not None:
                    body["text"] = params["text"]
                if body["kind"] == "link" and params.get("url") is not None:
                    body["url"] = params["url"]
                data = await self._make_request(HttpMethod.POST, url, headers=headers, data=body)
                return MCPToolResult(success=True, data=data)

            if operation == "get_comments":
                url = f"{self.API_BASE}/r/{params['subreddit']}/comments/{params['article_id']}"
                data = await self._make_request(HttpMethod.GET, url, headers=headers)
                return MCPToolResult(success=True, data=data)

            if operation == "vote":
                url = f"{self.API_BASE}/api/vote"
                body = {"id": params["thing_id"], "dir": int(params["direction"])}
                data = await self._make_request(HttpMethod.POST, url, headers=headers, data=body)
                return MCPToolResult(success=True, data=data)

            raise ValidationError(f"Unsupported operation: {operation}")

        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                raise InvalidCredentialsError(f"Reddit authentication failed: {e}")
            elif e.status == 429:
                retry_after = int(e.headers.get("Retry-After", "60"))
                raise RateLimitError("Reddit rate limit exceeded", retry_after=retry_after)
            elif e.status >= 500:
                raise NetworkError(f"Reddit server error: {e}")
            else:
                raise MCPToolError(f"Reddit API error: HTTP {e.status}")
        except Exception as e:
            logger.error(f"Reddit operation {operation} failed: {e}")
            raise

    # ============================= Auth =============================
    async def _get_reddit_headers(self, tenant_id: str) -> Dict[str, str]:
        # Prefer OAuth credentials
        creds_data: Optional[Dict[str, Any]]
        try:
            creds_data = await self.secrets_manager.get_secret(
                tenant_id=tenant_id,
                service_name="reddit",
                key_type="oauth_credentials",
            )
        except Exception:
            creds_data = None

        if creds_data:
            creds = self._oauth_cache.get(tenant_id) or RedditOAuthCredentials.from_dict(creds_data)
            if creds.needs_refresh():
                creds = await self._refresh_token(creds)
                await self.secrets_manager.set_secret(
                    tenant_id=tenant_id,
                    service_name="reddit",
                    key_type="oauth_credentials",
                    secret_value=creds.to_dict(),
                )
            self._oauth_cache[tenant_id] = creds
            return {
                "Authorization": f"bearer {creds.access_token}",
                "User-Agent": self.USER_AGENT,
                "Content-Type": "application/json",
            }

        # Fallback to bearer access token directly (if stored separately)
        token = await self.secrets_manager.get_secret(
            tenant_id=tenant_id, service_name="reddit", key_type="access_token"
        )
        if not token:
            raise InvalidCredentialsError("Reddit credentials not found for tenant")
        return {
            "Authorization": f"bearer {token}",
            "User-Agent": self.USER_AGENT,
            "Content-Type": "application/json",
        }

    async def _refresh_token(self, creds: RedditOAuthCredentials) -> RedditOAuthCredentials:
        if not creds.refresh_token or not creds.client_id or not creds.client_secret:
            raise InvalidCredentialsError("Missing Reddit refresh credentials")

        session = await self._get_session()
        # Reddit requires Basic Auth for client credentials
        auth = aiohttp.BasicAuth(creds.client_id, creds.client_secret)
        data = {"grant_type": "refresh_token", "refresh_token": creds.refresh_token}
        async with session.post(self.TOKEN_URL, auth=auth, data=data, headers={"User-Agent": self.USER_AGENT}) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise InvalidCredentialsError(f"Reddit token refresh failed: HTTP {resp.status} {text[:200]}")
            token_json = await resp.json()
            new_access = token_json.get("access_token")
            expires_in = int(token_json.get("expires_in", 3600))
            if not new_access:
                raise InvalidCredentialsError("Reddit token refresh did not return access_token")
            creds.access_token = new_access
            creds.expires_in = expires_in
            creds.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            if token_json.get("refresh_token"):
                creds.refresh_token = token_json["refresh_token"]
            return creds


