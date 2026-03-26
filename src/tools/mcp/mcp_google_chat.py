"""
Google Chat MCP Tool (MVP)
- list_spaces
- get_messages
- send_message
"""
from __future__ import annotations

from typing import Any, Dict

from .base_mcp_tool import RateLimitConfig, RetryConfig, CircuitBreakerConfig, AuthType, ValidationError
from .google_workspace_base import GoogleWorkspaceBase


class MCPGoogleChatTool(GoogleWorkspaceBase):
    CHAT_BASE = "https://chat.googleapis.com/v1"

    SCOPES_READ = [
        "https://www.googleapis.com/auth/chat.spaces.readonly",
        "https://www.googleapis.com/auth/chat.messages.readonly",
    ]
    SCOPES_WRITE = [
        "https://www.googleapis.com/auth/chat.bot",
    ]

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(requests_per_second=10.0, burst_size=20)
    DEFAULT_RETRY_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=30.0)
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)

    def __init__(self):
        super().__init__(
            name="mcp_google_chat",
            description="Google Chat operations (spaces, messages)",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.CHAT_BASE,
            rate_limit_config=self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )

    def _get_operation_schema(self, operation: str):
        STR = str
        schemas = {
            "list_spaces": {},
            "get_messages": {
                "space": {"required": True, "type": STR},  # e.g., spaces/AAA... 
                "page_size": {"required": False, "type": int},
            },
            "send_message": {
                "space": {"required": True, "type": STR},
                "text": {"required": True, "type": STR},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        return (operation == "send_message") or super()._is_write_operation(operation, params)

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]):
        op = (operation or "").lower()
        if op == "list_spaces":
            headers = await self._auth_headers(tenant_id, self.SCOPES_READ)
            url = f"{self.CHAT_BASE}/spaces"
            return await self._request_json("GET", url, headers=headers)

        if op == "get_messages":
            headers = await self._auth_headers(tenant_id, self.SCOPES_READ)
            space = params["space"]
            q = {}
            if params.get("page_size"): q["pageSize"] = int(params["page_size"])  # type: ignore
            url = f"{self.CHAT_BASE}/{space}/messages"
            return await self._request_json("GET", url, headers=headers, params=q)

        if op == "send_message":
            headers = await self._auth_headers(tenant_id, self.SCOPES_WRITE)
            space = params["space"]
            url = f"{self.CHAT_BASE}/{space}/messages"
            body = {"text": params["text"]}
            return await self._request_json("POST", url, headers=headers, json_body=body)

        raise ValidationError(f"Unsupported operation: {operation}")
