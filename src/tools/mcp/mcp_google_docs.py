"""
Google Docs MCP Tool (vendor-bridged)
- get_doc_content
- create_doc
- modify_doc_text (batchUpdate)
"""
from __future__ import annotations

from typing import Any, Dict
import asyncio

from .base_mcp_tool import RateLimitConfig, RetryConfig, CircuitBreakerConfig, AuthType, ValidationError
from .google_workspace_base import GoogleWorkspaceBase
from .vendor_bridge.google_workspace_adapter import GoogleWorkspaceVendorAdapter


class MCPGoogleDocsTool(GoogleWorkspaceBase):
    DOCS_BASE = "https://docs.googleapis.com/v1"

    SCOPES_READ = [
        "https://www.googleapis.com/auth/documents.readonly",
    ]
    SCOPES_WRITE = [
        "https://www.googleapis.com/auth/documents",
    ]

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(requests_per_second=10.0, burst_size=20)
    DEFAULT_RETRY_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=30.0)
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)

    def __init__(self):
        super().__init__(
            name="mcp_google_docs",
            description="Google Docs operations (get, create, batchUpdate)",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.DOCS_BASE,
            rate_limit_config=self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )

    def _get_operation_schema(self, operation: str):
        STR = str
        DICT = dict
        schemas = {
            "get_doc_content": {
                "document_id": {"required": True, "type": STR},
            },
            "create_doc": {
                "title": {"required": True, "type": STR},
            },
            "modify_doc_text": {
                "document_id": {"required": True, "type": STR},
                "requests": {"required": True, "type": list},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        return (operation in {"create_doc", "modify_doc_text"}) or super()._is_write_operation(operation, params)

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]):
        op = (operation or "").lower()
        adapter = GoogleWorkspaceVendorAdapter(str(tenant_id))

        if op == "get_doc_content":
            doc_id = params["document_id"]
            docs = await adapter.get_docs(["https://www.googleapis.com/auth/documents.readonly"])
            def _get():
                return docs.documents().get(documentId=doc_id).execute()
            return await asyncio.to_thread(_get)

        if op == "create_doc":
            title = params["title"]
            docs = await adapter.get_docs(["https://www.googleapis.com/auth/documents"])
            def _create():
                return docs.documents().create(body={"title": title}).execute()
            return await asyncio.to_thread(_create)

        if op == "modify_doc_text":
            doc_id = params["document_id"]
            requests = params["requests"]
            docs = await adapter.get_docs(["https://www.googleapis.com/auth/documents"])
            def _batch():
                return docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
            return await asyncio.to_thread(_batch)

        raise ValidationError(f"Unsupported operation: {operation}")
