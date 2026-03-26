import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.database.models import ToolStatus
from src.tools.tool_manager import get_tool_manager

logger = logging.getLogger(__name__)


class ToolRegistryInput(BaseModel):
    query: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    include_beta: bool = Field(True)
    include_deprecated: bool = Field(False)
    limit: int = Field(200)


@tool
def tool_registry_tool(
    tenant_id: Optional[str] = None,
    job_id: Optional[str] = None,
    query: Optional[str] = None,
    category: Optional[str] = None,
    include_beta: bool = True,
    include_deprecated: bool = False,
    limit: int = 200,
) -> Dict[str, Any]:
    """List/search available tools from the in-code tool registry.

    This intentionally does not query the database. The registry surface is meant to
    reflect what is actually deployed inside the Cloud Run containers.
    """
    include_beta = bool(include_beta)
    include_deprecated = bool(include_deprecated)
    limit = int(limit or 200)

    statuses: List[ToolStatus] = [ToolStatus.STABLE]
    if include_beta:
        statuses.append(ToolStatus.BETA)
    if include_deprecated:
        statuses.append(ToolStatus.DEPRECATED)

    allowed_statuses = {s.value for s in statuses}
    q = (query or "").strip().lower()

    try:
        registry = get_tool_manager().get_tool_registry_info().get("registry", {})

        tools: List[Dict[str, Any]] = []
        for name, cfg in registry.items():
            status = cfg.get("status")
            status_value = status.value if hasattr(status, "value") else (str(status) if status is not None else "BETA")

            if status_value not in allowed_statuses:
                continue
            if category and cfg.get("category") != category:
                continue

            desc = str(cfg.get("description") or "")
            if q and (q not in name.lower()) and (q not in desc.lower()):
                continue

            tools.append(
                {
                    "name": name,
                    "description": desc,
                    "status": status_value,
                    "category": cfg.get("category"),
                    "requires_auth": bool(cfg.get("requires_auth", False)),
                    "documentation_url": cfg.get("documentation_url"),
                    "version": cfg.get("version"),
                }
            )

        tools.sort(key=lambda t: t.get("name", ""))
        if limit > 0:
            tools = tools[:limit]
        return {"count": len(tools), "tools": tools}
    except Exception as e:
        logger.error(f"tool_registry_tool failed: {e}")
        return {"count": 0, "tools": [], "error": str(e)}


# Schema hints registry for tools that provide detailed usage information
TOOL_SCHEMA_HINTS_REGISTRY: Dict[str, Any] = {}


def register_schema_hints(tool_name: str, hints_fn: Any) -> None:
    """Register a schema hints function for a tool."""
    TOOL_SCHEMA_HINTS_REGISTRY[tool_name] = hints_fn


def get_tool_schema_hints(tool_name: str) -> Optional[Dict[str, Any]]:
    """Get schema hints for a specific tool."""
    hints_fn = TOOL_SCHEMA_HINTS_REGISTRY.get(tool_name)
    if hints_fn and callable(hints_fn):
        try:
            return hints_fn()
        except Exception as e:
            logger.warning(f"Failed to get schema hints for {tool_name}: {e}")
    return None


# Auto-register multimodal KB tool schema hints
try:
    from src.tools.multimodal_kb_tool import (
        multimodal_kb_search_get_schema_hints,
        fetch_document_content_get_schema_hints,
        image_search_by_image_get_schema_hints,
    )
    register_schema_hints("multimodal_kb_search", multimodal_kb_search_get_schema_hints)
    register_schema_hints("fetch_document_content", fetch_document_content_get_schema_hints)
    register_schema_hints("image_search_by_image", image_search_by_image_get_schema_hints)
except ImportError:
    pass

# Auto-register bigquery_vector_search schema hints
try:
    from src.tools.bigquery_vector_tool import _bigquery_vector_search_get_schema_hints
    register_schema_hints("bigquery_vector_search", _bigquery_vector_search_get_schema_hints)
except ImportError:
    pass


@tool
def get_tool_usage_schema(
    tool_name: str,
) -> Dict[str, Any]:
    """Get detailed usage schema and examples for a specific tool.

    Use this tool to understand HOW to call another tool correctly.
    Returns input schema, usage instructions, and examples.

    Input:
      - tool_name (str, required): Name of the tool to get schema for

    Output:
      {
        "tool_name": "multimodal_kb_search",
        "input_schema": {...},
        "usage": "How to use this tool...",
        "examples": [...]
      }
    """
    tool_name = str(tool_name or "").strip()
    if not tool_name:
        return {"error": "tool_name is required"}

    hints = get_tool_schema_hints(tool_name)
    if hints:
        return {
            "tool_name": tool_name,
            **hints,
        }

    # Fallback: try to get from registry description
    try:
        registry = get_tool_manager().get_tool_registry_info().get("registry", {})
        if tool_name in registry:
            cfg = registry[tool_name]
            return {
                "tool_name": tool_name,
                "description": cfg.get("description", ""),
                "category": cfg.get("category"),
                "usage": "Call this tool with appropriate parameters. See description for details.",
            }
    except Exception:
        pass

    return {"error": f"No schema hints available for tool '{tool_name}'"}
