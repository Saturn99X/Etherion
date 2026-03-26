"""
Google Forms MCP Tool (vendor-bridged)
- create_form
- get_form
- list_form_responses
- set_publish_settings
- get_form_response
"""
from __future__ import annotations

from typing import Any, Dict
import asyncio

from .base_mcp_tool import RateLimitConfig, RetryConfig, CircuitBreakerConfig, AuthType, ValidationError
from .google_workspace_base import GoogleWorkspaceBase
from .vendor_bridge.google_workspace_adapter import GoogleWorkspaceVendorAdapter


class MCPGoogleFormsTool(GoogleWorkspaceBase):
    FORMS_BASE = "https://forms.googleapis.com/v1"

    SCOPES_READ = [
        "https://www.googleapis.com/auth/forms.body.readonly",
        "https://www.googleapis.com/auth/forms.responses.readonly",
    ]
    SCOPES_WRITE = [
        "https://www.googleapis.com/auth/forms.body",
    ]

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(requests_per_second=10.0, burst_size=20)
    DEFAULT_RETRY_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=30.0)
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)

    def __init__(self):
        super().__init__(
            name="mcp_google_forms",
            description="Google Forms operations (create, get, list responses)",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.FORMS_BASE,
            rate_limit_config=self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )

    def _get_operation_schema(self, operation: str):
        STR = str
        DICT = dict
        schemas = {
            "create_form": {
                "title": {"required": True, "type": STR},
                "description": {"required": False, "type": STR},
                "document_title": {"required": False, "type": STR},
            },
            "get_form": {
                "form_id": {"required": True, "type": STR},
            },
            "list_form_responses": {
                "form_id": {"required": True, "type": STR},
                "page_size": {"required": False, "type": int},
                "page_token": {"required": False, "type": STR},
            },
            "set_publish_settings": {
                "form_id": {"required": True, "type": STR},
                "publish_as_template": {"required": False, "type": bool},
                "require_authentication": {"required": False, "type": bool},
            },
            "get_form_response": {
                "form_id": {"required": True, "type": STR},
                "response_id": {"required": True, "type": STR},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        return (operation in {"create_form", "set_publish_settings"}) or super()._is_write_operation(operation, params)

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]):
        op = (operation or "").lower()
        adapter = GoogleWorkspaceVendorAdapter(str(tenant_id))

        if op == "create_form":
            forms = await adapter.get_forms(["https://www.googleapis.com/auth/forms.body"])
            title = params["title"]
            description = params.get("description")
            document_title = params.get("document_title")
            def _create():
                body: Dict[str, Any] = {"info": {"title": title}}
                if description:
                    body["info"]["description"] = description
                if document_title:
                    body["info"]["document_title"] = document_title
                return forms.forms().create(body=body).execute()
            return await asyncio.to_thread(_create)

        if op == "get_form":
            forms = await adapter.get_forms(["https://www.googleapis.com/auth/forms.body.readonly"])
            fid = params["form_id"]
            def _get():
                return forms.forms().get(formId=fid).execute()
            return await asyncio.to_thread(_get)

        if op == "list_form_responses":
            forms = await adapter.get_forms(["https://www.googleapis.com/auth/forms.responses.readonly"])
            fid = params["form_id"]
            page_size = int(params.get("page_size", 10))
            page_token = params.get("page_token")
            def _list():
                kwargs: Dict[str, Any] = {"formId": fid, "pageSize": page_size}
                if page_token:
                    kwargs["pageToken"] = page_token
                return forms.forms().responses().list(**kwargs).execute()
            return await asyncio.to_thread(_list)

        if op == "set_publish_settings":
            forms = await adapter.get_forms(["https://www.googleapis.com/auth/forms.body"])
            fid = params["form_id"]
            publish_as_template = bool(params.get("publish_as_template", False))
            require_authentication = bool(params.get("require_authentication", False))
            def _set():
                body = {
                    "publishAsTemplate": publish_as_template,
                    "requireAuthentication": require_authentication,
                }
                return forms.forms().setPublishSettings(formId=fid, body=body).execute()
            return await asyncio.to_thread(_set)

        if op == "get_form_response":
            forms = await adapter.get_forms(["https://www.googleapis.com/auth/forms.responses.readonly"])
            fid = params["form_id"]
            rid = params["response_id"]
            def _get_resp():
                return forms.forms().responses().get(formId=fid, responseId=rid).execute()
            return await asyncio.to_thread(_get_resp)

        raise ValidationError(f"Unsupported operation: {operation}")
