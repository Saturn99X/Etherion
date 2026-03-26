"""
Google Custom Search (PSE) MCP Tool (MVP)
- search_custom

Uses API key + cx stored under service "google_search" key_type "credentials":
{
  "api_key": "...",
  "cx": "..."
}
"""
from __future__ import annotations

from typing import Any, Dict

from .base_mcp_tool import RateLimitConfig, RetryConfig, CircuitBreakerConfig, AuthType, ValidationError, EnhancedMCPTool, HttpMethod

from src.utils.secrets_manager import TenantSecretsManager


class MCPGoogleSearchTool(EnhancedMCPTool):
    BASE = "https://www.googleapis.com/customsearch/v1"

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(requests_per_second=5.0, burst_size=10)
    DEFAULT_RETRY_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=30.0)
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)

    def __init__(self):
        super().__init__(
            name="mcp_google_search",
            description="Google Custom Search (Programmable Search Engine)",
            auth_type=AuthType.API_KEY,
            base_url=self.BASE,
            rate_limit_config=self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=15.0,
        )
        self._tsm = TenantSecretsManager()

    def _get_operation_schema(self, operation: str):
        STR = str
        INT = int
        schemas = {
            "search_custom": {
                "query": {"required": True, "type": STR},
                "num": {"required": False, "type": INT},
                "start": {"required": False, "type": INT},
            },
        }
        return schemas.get((operation or "").lower())

    async def _get_cse_creds(self, tenant_id: str) -> Dict[str, str]:
        data = await self.secrets_manager.get_secret(
            tenant_id=tenant_id,
            service_name="google_search",
            key_type="credentials",
        )
        if not isinstance(data, dict) or not data.get("api_key") or not data.get("cx"):
            raise ValidationError("Missing google_search credentials (api_key, cx)")
        return {"api_key": data["api_key"], "cx": data["cx"]}

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]):
        op = (operation or "").lower()
        if op == "search_custom":
            creds = await self._get_cse_creds(tenant_id)
            q = {
                "key": creds["api_key"],
                "cx": creds["cx"],
                "q": params["query"],
            }
            if params.get("num"): q["num"] = int(params["num"])  # type: ignore
            if params.get("start"): q["start"] = int(params["start"])  # type: ignore
            return await self._make_request(
                method=HttpMethod.GET,
                url=self.BASE,
                headers={},
                params=q,
            )
        raise ValidationError(f"Unsupported operation: {operation}")
