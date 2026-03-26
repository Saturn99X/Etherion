import asyncio
import base64
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import aiohttp

from .base_mcp_tool import (
    EnhancedMCPTool,
    MCPToolResult,
    InvalidCredentialsError,
    RateLimitError,
    ValidationError,
    RateLimitConfig,
    RetryConfig,
    CircuitBreakerConfig,
    HttpMethod,
    MCPToolError,
    AuthType,
)
from src.utils.secrets_manager import TenantSecretsManager
from src.utils.input_sanitization import InputSanitizer


class MCPJiraTool(EnhancedMCPTool):
    """Production-ready Jira MCP Tool with async HTTP, validation, and idempotency."""

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=5.0,
        requests_per_minute=300.0,
        requests_per_hour=15000.0,
        burst_size=10,
    )

    DEFAULT_RETRY_CONFIG = RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
        retry_on_status_codes=[429, 500, 502, 503, 504],  # Include 500 for internal_server_error
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
    ):
        super().__init__(
            name="mcp_jira",
            description="Jira Cloud integration: get_issue, search_jql, create_issue, update_issue, get_projects",
            auth_type=AuthType.CUSTOM,
            base_url=None,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )
        self.secrets_manager = TenantSecretsManager()
        self._idempotency_cache: Dict[str, Dict[str, Any]] = {}
        self._idempotency_ttl_seconds: int = 600

    # ========================= OAuth Credentials (Optional) =========================

    @dataclass
    class JiraCredentials:
        access_token: str
        refresh_token: Optional[str] = None
        expires_at: Optional[datetime] = None
        client_id: Optional[str] = None
        client_secret: Optional[str] = None

        def needs_refresh(self, buffer_minutes: int = 5) -> bool:
            if not self.expires_at:
                return False
            return datetime.utcnow() >= (self.expires_at - timedelta(minutes=buffer_minutes))

        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> "MCPJiraTool.JiraCredentials":
            exp = data.get("expires_at")
            expires_at = None
            if isinstance(exp, str) and exp:
                try:
                    expires_at = datetime.fromisoformat(exp)
                except Exception:
                    expires_at = None
            return cls(
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token"),
                expires_at=expires_at,
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
            )

        def to_dict(self) -> Dict[str, Any]:
            return {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }

    async def _get_oauth_credentials_with_refresh(self, tenant_id: str) -> Optional["MCPJiraTool.JiraCredentials"]:
        """Load Jira OAuth credentials and refresh if needed; return None if not configured.
        Prefer unified 'oauth_tokens' key; fallback to legacy 'oauth_credentials'.
        """
        try:
            raw = await self.secrets_manager.get_secret(tenant_id=tenant_id, service_name="jira", key_type="oauth_tokens")
            if not raw or not raw.get("access_token"):
                raw = await self.secrets_manager.get_secret(tenant_id=tenant_id, service_name="jira", key_type="oauth_credentials")
            if not raw or not raw.get("access_token"):
                return None
            creds = MCPJiraTool.JiraCredentials.from_dict(raw)
            # Refresh if needed and refresh token available
            if creds.needs_refresh() and creds.refresh_token and creds.client_id and creds.client_secret:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://auth.atlassian.com/oauth/token",
                        data={
                            "grant_type": "refresh_token",
                            "client_id": creds.client_id,
                            "client_secret": creds.client_secret,
                            "refresh_token": creds.refresh_token,
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ) as resp:
                        data = await resp.json()
                        if resp.status != 200 or not data.get("access_token"):
                            # If refresh fails, fall back to requiring re-auth
                            return creds
                        creds.access_token = data.get("access_token")
                        # Atlassian returns expires_in
                        expires_in = int(data.get("expires_in", 3600))
                        creds.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                        new_refresh = data.get("refresh_token")
                        if new_refresh:
                            creds.refresh_token = new_refresh
                        # Persist
                        await self.secrets_manager.set_secret(
                            tenant_id=tenant_id,
                            service_name="jira",
                            key_type="oauth_tokens",
                            value=creds.to_dict(),
                        )
            return creds
        except Exception:
            return None

    # ========================= Helpers =========================

    async def _get_jira_base(self, tenant_id: str) -> Dict[str, str]:
        """Build base URL and auth header using tenant secrets.

        Prefer OAuth Bearer token if configured; otherwise fallback to email+api_token Basic auth.
        """
        # Common base resolution
        cloud_id = await self.secrets_manager.get_secret(
            tenant_id=tenant_id, service_name="jira", key_type="cloud_id"
        )
        domain = await self.secrets_manager.get_secret(
            tenant_id=tenant_id, service_name="jira", key_type="domain"
        )

        # Try OAuth first
        oauth_creds = await self._get_oauth_credentials_with_refresh(tenant_id)
        if oauth_creds and oauth_creds.access_token:
            headers = {
                "Authorization": f"Bearer {oauth_creds.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if cloud_id:
                base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
            elif domain:
                base_url = f"https://{domain}.atlassian.net/rest/api/3"
            else:
                raise InvalidCredentialsError("Missing Jira cloud_id or domain for tenant")
            return {"base_url": base_url, "headers": headers}

        # Fallback: Basic auth using email + API token
        email = await self.secrets_manager.get_secret(
            tenant_id=tenant_id, service_name="jira", key_type="email"
        )
        api_token = await self.secrets_manager.get_secret(
            tenant_id=tenant_id, service_name="jira", key_type="api_token"
        )
        if not email or not api_token:
            raise InvalidCredentialsError("Jira credentials not found for tenant")
        credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if cloud_id:
            base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
        elif domain:
            base_url = f"https://{domain}.atlassian.net/rest/api/3"
        else:
            raise InvalidCredentialsError("Missing Jira cloud_id or domain for tenant")
        return {"base_url": base_url, "headers": headers}

    async def _get_idempotency_key(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> str:
        """Deterministic idempotency key from tenant, operation and params."""
        # Only include stable, order-independent representation
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(f"{tenant_id}:{operation}:{canonical}".encode()).hexdigest()
        return digest

    async def _get_cached_idempotency(self, tenant_id: str, key: str) -> Optional[Dict[str, Any]]:
        cache_key = f"{tenant_id}:{key}"
        entry = self._idempotency_cache.get(cache_key)
        if not entry:
            return None
        if time.time() - entry["timestamp"] > self._idempotency_ttl_seconds:
            # Expired
            del self._idempotency_cache[cache_key]
            return None
        return entry["result"]

    async def _store_idempotency(self, tenant_id: str, key: str, result: Dict[str, Any]) -> None:
        cache_key = f"{tenant_id}:{key}"
        self._idempotency_cache[cache_key] = {"result": result, "timestamp": time.time()}

    # ========================= Validation =========================

    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        if operation == "get_issue":
            return {
                "issue_key": {"required": True, "type": str, "max_length": 100},
            }
        if operation == "search_jql":
            return {
                "jql": {"required": True, "type": str, "max_length": 1000},
                "max_results": {"required": False, "type": int},
                "start_at": {"required": False, "type": int},
            }
        if operation == "create_issue":
            return {
                "project_key": {"required": True, "type": str, "max_length": 50},
                "summary": {"required": True, "type": str, "max_length": 500},
                "issue_type": {"required": True, "type": str, "max_length": 50},
                "description": {"required": False, "type": str, "max_length": 5000},
            }
        if operation == "update_issue":
            return {
                "issue_key": {"required": True, "type": str, "max_length": 100},
                "fields": {"required": True, "type": dict},
            }
        if operation == "get_projects":
            return {}
        if operation == "get_sprint_tickets":
            return {
                "sprint_id": {"required": True, "type": int},
                "max_results": {"required": False, "type": int},
                "start_at": {"required": False, "type": int},
            }
        return None

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        write_ops = {"create_issue", "update_issue"}
        return op in write_ops or super()._is_write_operation(operation, params)

    # ========================= Handlers =========================

    async def _handle_get_issue(self, tenant_id: str, base: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{base['base_url']}/issue/{params['issue_key']}"
        return await self._make_request(HttpMethod.GET, url, headers=base["headers"])

    async def _handle_search_jql(self, tenant_id: str, base: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{base['base_url']}/search"
        body = {
            "jql": params["jql"],
            "maxResults": min(max(int(params.get("max_results", 50)), 1), 100),
            "startAt": int(params.get("start_at", 0)),
        }
        return await self._make_request(HttpMethod.POST, url, headers=base["headers"], json_data=body)

    async def _handle_create_issue(self, tenant_id: str, base: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{base['base_url']}/issue"
        fields = {
            "project": {"key": params["project_key"]},
            "summary": params["summary"],
            "issuetype": {"name": params["issue_type"]},
        }
        if "description" in params and params["description"] is not None:
            fields["description"] = params["description"]
        body = {"fields": fields}
        return await self._make_request(HttpMethod.POST, url, headers=base["headers"], json_data=body)

    async def _handle_update_issue(self, tenant_id: str, base: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{base['base_url']}/issue/{params['issue_key']}"
        body = {"fields": params["fields"]}
        return await self._make_request(HttpMethod.PUT, url, headers=base["headers"], json_data=body)

    async def _handle_get_projects(self, tenant_id: str, base: Dict[str, str]) -> Dict[str, Any]:
        url = f"{base['base_url']}/project/search"
        return await self._make_request(HttpMethod.GET, url, headers=base["headers"])

    async def _handle_get_sprint_tickets(self, tenant_id: str, base: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        # Use JQL to fetch sprint issues; avoids requiring Agile API permissions
        jql = f"sprint = {int(params['sprint_id'])} ORDER BY updated DESC"
        body = {
            "jql": jql,
            "maxResults": min(max(int(params.get("max_results", 50)), 1), 100),
            "startAt": int(params.get("start_at", 0)),
        }
        url = f"{base['base_url']}/search"
        return await self._make_request(HttpMethod.POST, url, headers=base["headers"], json_data=body)

    # ========================= Execution =========================

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        try:
            base = await self._get_jira_base(tenant_id)

            write_ops = {"create_issue", "update_issue"}

            # Idempotency for writes
            idempotency_key = None
            if operation in write_ops:
                idempotency_key = await self._get_idempotency_key(tenant_id, operation, params)
                cached = await self._get_cached_idempotency(tenant_id, idempotency_key)
                if cached is not None:
                    return MCPToolResult(
                        success=True,
                        data=cached,
                        metadata={"cached": True, "idempotency_key": idempotency_key},
                    )

            handler_map = {
                "get_issue": self._handle_get_issue,
                "search_jql": self._handle_search_jql,
                "create_issue": self._handle_create_issue,
                "update_issue": self._handle_update_issue,
                "get_projects": self._handle_get_projects,
                "get_sprint_tickets": self._handle_get_sprint_tickets,
            }

            handler = handler_map.get(operation)
            if not handler:
                return MCPToolResult(
                    success=False,
                    error_message=f"Unsupported operation: {operation}",
                    error_code="UNSUPPORTED_OPERATION",
                )

            # Dispatch to handler
            if operation in {"get_projects"}:
                result = await handler(tenant_id, base)  # type: ignore[arg-type]
            else:
                result = await handler(tenant_id, base, params)  # type: ignore[arg-type]

            if operation in write_ops and idempotency_key:
                await self._store_idempotency(tenant_id, idempotency_key, result)

            return MCPToolResult(success=True, data=result, metadata={"idempotency_key": idempotency_key})

        except InvalidCredentialsError:
            raise
        except RateLimitError:
            raise
        except ValidationError:
            raise
        except MCPToolError as e:
            # Check for Jira-specific internal server errors
            if "internal_server_error" in str(e).lower() or "500" in str(e):
                # This will be caught by the retry logic in EnhancedMCPTool
                raise MCPToolError(f"Jira internal server error (retryable): {e}", retryable=True)
            raise
        except Exception as e:
            raise MCPToolError(f"Jira API error: {e}")

    # ========================= Webhook Verification =========================

    async def handle_webhook(
        self, tenant_id: str, payload: bytes, signature: str, topic: Optional[str] = None
    ) -> MCPToolResult:
        """Verify and process Jira webhook events.
        
        Args:
            tenant_id: Tenant identifier
            payload: Raw webhook payload
            signature: HMAC signature from X-Atlassian-Webhook-Signature header
            topic: Optional webhook topic filter
            
        Returns:
            MCPToolResult with webhook data if valid
        """
        try:
            # Get webhook secret from secrets manager
            webhook_secret = await self.secrets_manager.get_secret(
                tenant_id=tenant_id, service_name="jira", key_type="webhook_secret"
            )
            
            if not webhook_secret:
                return MCPToolResult(
                    success=False,
                    error_message="Jira webhook secret not found",
                    error_code="MISSING_WEBHOOK_SECRET",
                )
            
            # Verify HMAC signature
            if not self.verify_webhook_signature(payload, signature, webhook_secret):
                return MCPToolResult(
                    success=False,
                    error_message="Invalid webhook signature",
                    error_code="INVALID_SIGNATURE",
                )
            
            # Parse webhook payload
            webhook_data = json.loads(payload.decode('utf-8'))
            
            # Filter by topic if provided
            if topic and webhook_data.get("webhookEvent") != topic:
                return MCPToolResult(
                    success=False,
                    error_message=f"Webhook topic mismatch: expected {topic}, got {webhook_data.get('webhookEvent')}",
                    error_code="TOPIC_MISMATCH",
                )
            
            return MCPToolResult(
                success=True,
                data=webhook_data,
                metadata={"webhook_verified": True, "topic": webhook_data.get("webhookEvent")},
            )
            
        except json.JSONDecodeError as e:
            return MCPToolResult(
                success=False,
                error_message=f"Invalid JSON payload: {e}",
                error_code="INVALID_JSON",
            )
        except Exception as e:
            return MCPToolResult(
                success=False,
                error_message=f"Webhook processing error: {e}",
                error_code="WEBHOOK_ERROR",
            )

    async def close(self) -> None:
        # Clear idempotency cache proactively
        self._idempotency_cache.clear()
        await super().close()
