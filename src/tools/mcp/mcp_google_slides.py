"""
Google Slides MCP Tool (vendor-bridged)
- create_presentation
- get_presentation
"""
from __future__ import annotations

from typing import Any, Dict
import asyncio

from .base_mcp_tool import RateLimitConfig, RetryConfig, CircuitBreakerConfig, AuthType, ValidationError
from .google_workspace_base import GoogleWorkspaceBase
from .vendor_bridge.google_workspace_adapter import GoogleWorkspaceVendorAdapter


class MCPGoogleSlidesTool(GoogleWorkspaceBase):
    SLIDES_BASE = "https://slides.googleapis.com/v1"

    SCOPES_READ = [
        "https://www.googleapis.com/auth/presentations.readonly",
    ]
    SCOPES_WRITE = [
        "https://www.googleapis.com/auth/presentations",
    ]

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(requests_per_second=10.0, burst_size=20)
    DEFAULT_RETRY_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=30.0)
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)

    def __init__(self):
        super().__init__(
            name="mcp_google_slides",
            description="Google Slides operations (create, get)",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.SLIDES_BASE,
            rate_limit_config=self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )

    def _get_operation_schema(self, operation: str):
        STR = str
        schemas = {
            "create_presentation": {
                "title": {"required": True, "type": STR},
            },
            "get_presentation": {
                "presentation_id": {"required": True, "type": STR},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        return (operation == "create_presentation") or super()._is_write_operation(operation, params)

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]):
        op = (operation or "").lower()
        adapter = GoogleWorkspaceVendorAdapter(str(tenant_id))

        if op == "create_presentation":
            title = params["title"]
            slides = await adapter.get_slides(["https://www.googleapis.com/auth/presentations"])
            def _create():
                return slides.presentations().create(body={"title": title}).execute()
            return await asyncio.to_thread(_create)

        if op == "get_presentation":
            pid = params["presentation_id"]
            slides = await adapter.get_slides(["https://www.googleapis.com/auth/presentations.readonly"])
            def _get():
                return slides.presentations().get(presentationId=pid).execute()
            return await asyncio.to_thread(_get)

        raise ValidationError(f"Unsupported operation: {operation}")
