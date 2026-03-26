import asyncio
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from src.core.redis import publish_ui_event

logger = logging.getLogger(__name__)

# Server-side allowlist for component IDs and actions
ALLOWED_ACTIONS = {
    "open_component",
    "update_component",
    "close_component",
    "show_modal",
    "close_modal",
    "toast",
    "append_trace_card",
}

ALLOWED_COMPONENTS = {
    # Triggered UIs
    "triggered-ui/agent-blueprint-ui",
    "triggered-ui/confirmation-modals:basic",
    # File generation
    "file-generation/document-generator-ui",
    "file-generation/pdf-generator-ui",
    "file-generation/excel-generator-ui",
    # Charts & visualization
    "charts-and-visualization/chart-components:bar",
    "charts-and-visualization/chart-components:line",
    "charts-and-visualization/data-table",
    # Agent-specific placeholders (allowed until replaced)
    "agent-specific/marketing-team-ui:campaign-builder",
    "agent-specific/development-team-ui:ci-panel",
    "agent-specific/analytics-team-ui:overview",
    "agent-specific/financial-team-ui:dashboard",
    "agent-specific/sales-team-ui:pipeline",
    "agent-specific/content-team-ui:editor",
}


def _validate_payload(action: str, component: Optional[str], payload: Optional[Dict[str, Any]]) -> Optional[str]:
    """Minimal schema checks per action/component. Return error string if invalid."""
    if action not in ALLOWED_ACTIONS:
        return f"action '{action}' not allowed"
    if action not in {"show_modal", "close_modal"}:
        # For component-based actions, validate component ID
        if not component or component not in ALLOWED_COMPONENTS:
            return f"component '{component}' not allowed"
    # Basic payload shape checks
    if payload is not None and not isinstance(payload, dict):
        return "payload must be a JSON object"

    if action == "show_modal":
        # Expect title/message and optional actions list
        if payload is None:
            return None
        if "title" in payload and not isinstance(payload["title"], (str, type(None))):
            return "modal.title must be a string"
        if "message" in payload and not isinstance(payload["message"], (str, type(None))):
            return "modal.message must be a string"
        if "actions" in payload and not isinstance(payload["actions"], list):
            return "modal.actions must be a list"

    # Charts minimal validation
    if component in {
        "charts-and-visualization/chart-components:bar",
        "charts-and-visualization/chart-components:line",
    }:
        data = (payload or {}).get("data")
        if data is not None and not isinstance(data, list):
            return "chart payload.data must be an array"

    if component == "charts-and-visualization/data-table":
        rows = (payload or {}).get("rows")
        if rows is not None and not isinstance(rows, list):
            return "data-table payload.rows must be an array"
    return None


def ui_action_tool(
    component: str,
    action: str = "open_component",
    payload: Optional[Dict[str, Any]] = None,
    *,
    tenant_id: int,
    job_id: Optional[str] = None,
    message: Optional[str] = None,
) -> str:
    """
    Publish a UI action event to the tenant-scoped UI event stream.

    Parameters:
    - component: canonical component ID, e.g.,
        "triggered-ui/agent-blueprint-ui",
        "triggered-ui/confirmation-modals:basic",
        "agent-specific/marketing-team-ui:campaign-builder",
        "charts-and-visualization/chart-components:bar",
        "file-generation/document-writer".
    - action: one of open_component | update_component | close_component | show_modal | toast | append_trace_card
    - payload: arbitrary JSON-serializable dict of props for the component
    - tenant_id: target tenant for dispatch (required)
    - job_id: optional job context
    - message: optional human-readable message

    Returns: acknowledgement string
    """
    # Validate server-side before publish
    error = _validate_payload(action, component, payload)
    if error:
        logger.warning(f"ui_action_tool validation failed: {error}")
        return f"ui_action_tool rejected: {error}"

    event = {
        "type": action or "UI",
        "component": component,
        "payload": payload or {},
        "job_id": job_id,
        "message": message,
    }

    # Fire-and-forget publish to Redis (safe in sync and async contexts)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(publish_ui_event(tenant_id, event))
        else:
            loop.run_until_complete(publish_ui_event(tenant_id, event))
    except RuntimeError:
        # No event loop: create a temporary one
        asyncio.run(publish_ui_event(tenant_id, event))
    except Exception as e:
        logger.error(f"ui_action_tool failed to publish event: {e}")
        return f"ui_action_tool error: {e}"

    logger.info(f"ui_action_tool published: tenant={tenant_id} component={component} action={action}")
    return "ui_action_tool: event published"


class UIActionInput(BaseModel):
    component: str = Field(
        ...,
        description="Canonical component ID from the server-side allowlist (ALLOWED_COMPONENTS)",
    )
    action: str = Field(
        "open_component",
        description=(
            "One of: open_component | update_component | close_component | "
            "show_modal | close_modal | toast | append_trace_card"
        ),
    )
    payload: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Component-specific props. For charts include 'data'; for data-table include 'rows'; "
            "for modals include 'title', 'message', and optional 'actions'."
        ),
    )
    message: Optional[str] = Field(
        None,
        description="Optional human-readable message to accompany the UI event.",
    )


def _ui_action_tool_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = UIActionInput.model_json_schema()
    except Exception:
        schema = UIActionInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Publish a UI action event to the tenant-scoped UI event stream. Provide component, action, "
            "optional payload, and optional message. Tenant and job identifiers are injected by the platform."
        ),
        "examples": [
            {
                "name": "open_document_generator",
                "input": {
                    "component": "file-generation/document-generator-ui",
                    "action": "open_component",
                    "payload": {"mode": "report", "documentTitle": "Q1 Summary"},
                },
            },
            {
                "name": "show_confirmation_modal",
                "input": {
                    "component": "triggered-ui/confirmation-modals:basic",
                    "action": "show_modal",
                    "payload": {
                        "title": "Delete generated file?",
                        "message": "This action will permanently remove the generated asset.",
                        "actions": ["confirm", "cancel"],
                    },
                },
            },
        ],
    }


ui_action_tool.get_schema_hints = _ui_action_tool_get_schema_hints
