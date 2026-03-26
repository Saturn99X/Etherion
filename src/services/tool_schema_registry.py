"""Static tool schema registry for richer ACT prompts.

Provides schema hints and examples for tools that do not expose runtime
`get_schema_hints()`.

Keep schemas minimal but precise to guide LLM output in ACT mode.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# Minimal examples and JSON-schema-like hints per tool name
_REGISTRY: Dict[str, Dict[str, Any]] = {
    "exa_search": {
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text"},
                "search_type": {
                    "type": "string",
                    "description": "Search mode",
                    "enum": ["neural", "keyword", "auto", "fast"],
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "minimum": 1,
                    "maximum": 100,
                },
                "include_text": {
                    "type": "boolean",
                    "description": "If true, fetch page text via /contents",
                },
                "include_highlights": {
                    "type": "boolean",
                    "description": "If true, fetch highlights via /contents",
                },
                "include_summary": {
                    "type": "boolean",
                    "description": "If true, fetch summary via /contents",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Request timeout in seconds",
                    "minimum": 1,
                    "maximum": 600,
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Optional job identifier for cost tracking",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "usage": (
            "Exa web search. Use include_text/highlights/summary to control whether the tool performs an additional "
            "content fetch (/contents). Keep these false for fast/lightweight calls."
        ),
        "examples": [
            {
                "name": "lightweight_search",
                "input": {
                    "query": "Etherion orchestrator performance",
                    "search_type": "neural",
                    "num_results": 8,
                    "include_text": False,
                    "include_highlights": False,
                    "include_summary": False,
                    "timeout_seconds": 15,
                },
            },
            {
                "name": "enriched_search_with_summaries",
                "input": {
                    "query": "EXA search API include_text highlights summary",
                    "search_type": "keyword",
                    "num_results": 5,
                    "include_text": True,
                    "include_highlights": True,
                    "include_summary": True,
                    "timeout_seconds": 60,
                },
            },
        ],
    },
    "unified_research_tool": {
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "User query"},
                "tenant_id": {"type": "string", "description": "Tenant identifier (string)"},
                "project_id": {
                    "type": ["string", "null"],
                    "description": "Optional project scope",
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Optional job identifier for tracing/cost",
                },
                "enable_web": {
                    "description": "Controls whether to run web search via Exa.",
                    "anyOf": [
                        {"type": "boolean"},
                        {
                            "type": "object",
                            "properties": {
                                "search_type": {
                                    "type": "string",
                                    "enum": ["neural", "keyword", "auto", "fast"],
                                    "description": "Exa search mode",
                                },
                                "num_results": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 100,
                                    "description": "Number of Exa results",
                                },
                                "timeout_seconds": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 600,
                                    "description": "Timeout for Exa calls",
                                },
                                "include_text": {
                                    "type": "boolean",
                                    "description": "Fetch page text via /contents",
                                },
                                "include_highlights": {
                                    "type": "boolean",
                                    "description": "Fetch highlights via /contents",
                                },
                                "include_summary": {
                                    "type": "boolean",
                                    "description": "Fetch summaries via /contents",
                                },
                            },
                            "additionalProperties": False,
                        },
                    ],
                },
            },
            "required": ["query", "tenant_id"],
            "additionalProperties": False,
        },
        "usage": (
            "Unified KB (BigQuery) + optional web (Exa) research. Pass enable_web=false for KB-only. "
            "Pass enable_web as an object to precisely control Exa heaviness (include_text/highlights/summary, timeouts, etc.)."
        ),
        "examples": [
            {
                "name": "kb_only",
                "input": {
                    "query": "What did the user complain about regarding cold starts?",
                    "tenant_id": "1",
                    "enable_web": False,
                },
            },
            {
                "name": "kb_plus_light_web",
                "input": {
                    "query": "Latest Cloud Run cold start best practices",
                    "tenant_id": "1",
                    "enable_web": {
                        "search_type": "neural",
                        "num_results": 8,
                        "timeout_seconds": 20,
                        "include_text": False,
                        "include_highlights": False,
                        "include_summary": False,
                    },
                },
            },
        ],
    },
    "tool_registry_tool": {
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": ["string", "null"],
                    "description": "Substring match against tool name/description",
                },
                "category": {
                    "type": ["string", "null"],
                    "description": "Filter by category",
                },
                "include_beta": {
                    "type": "boolean",
                    "description": "Whether to include BETA tools",
                },
                "include_deprecated": {
                    "type": "boolean",
                    "description": "Whether to include DEPRECATED tools",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum tools to return",
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
        "usage": "Lists/searches tools from the in-code ToolManager registry (no DB). Use this to discover tool names and descriptions.",
        "examples": [
            {"name": "search_research_tools", "input": {"query": "research", "limit": 50}},
            {"name": "list_all", "input": {"limit": 200}},
        ],
    },
    "orchestrator_research_tool": {
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "kb_timeout_seconds": {"type": "integer"},
                "web_timeout_seconds": {"type": "integer"},
                "exa_search_type": {"type": "string"},
                "exa_num_results": {"type": ["integer", "null"]},
                "exa_include_text": {"type": "boolean"},
                "exa_include_highlights": {"type": "boolean"},
                "exa_include_summary": {"type": "boolean"},
                "job_id": {"type": ["string", "null"]},
            },
            "required": ["query"],
            "additionalProperties": True,
        },
        "usage": "Legacy orchestrator research tool wrapper (KB + Exa) with explicit timeout knobs.",
    },

    "kb_object_fetch_ingest": {
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
                "gcs_uri": {"type": "string", "description": "Tenant-scoped gs:// URI to fetch (must be in tnt-{tenant}-media)"},
                "project_id": {"type": ["string", "null"], "description": "Optional project scope for KB insertion"},
                "job_id": {"type": ["string", "null"], "description": "Optional job id for labeling/telemetry"},
                "max_size_bytes": {
                    "type": "integer",
                    "description": "Maximum size allowed for fetch+ingest",
                    "minimum": 1,
                },
            },
            "required": ["tenant_id", "gcs_uri"],
            "additionalProperties": False,
        },
        "usage": (
            "Fetch a tenant-scoped object from the tenant media bucket (direct GCS read, streaming + size cap) and ingest it via MultimodalIngestionService. "
            "Use only with gs:// URIs returned by object-KB search. This is an ingestion bridge, not a general file download tool."
        ),
        "examples": [
            {
                "name": "fetch_and_ingest",
                "input": {
                    "tenant_id": "110",
                    "gcs_uri": "gs://tnt-110-media/uploads/<sha>/entropy.pdf",
                    "project_id": "physics_entropy_eval",
                    "max_size_bytes": 10485760,
                },
            }
        ],
    },
}

_GENERIC_TOOL_DEFAULT: Dict[str, Any] = {
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": True,
    },
    "usage": "Provide an object with named fields appropriate for the tool. tenant_id/job_id may be injected automatically by the runtime.",
}

# Generic MCP default hints (used when name starts with mcp_ and tool does not expose hints)
_MCP_DEFAULT: Dict[str, Any] = {
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "description": "Operation verb, e.g., list_channels, create_message"},
            "confirm_action": {"type": "boolean", "description": "Required true for write operations"},
            # Additional operation-specific fields are allowed
        },
        "required": ["operation"],
        "additionalProperties": True,
    },
    "usage": "For MCP tools, include 'operation' and any operation-specific fields. Set confirm_action=true for writes.",
    "examples": [
        {"name": "read", "input": {"operation": "list_items"}},
        {"name": "write", "input": {"operation": "create_item", "name": "Example", "confirm_action": True}},
    ],
}


def get_tool_schema_hints(tool_name: str) -> Optional[Dict[str, Any]]:
    """Return schema hints for a tool name, or a generic default for MCP tools."""
    if not tool_name:
        return None
    if tool_name in _REGISTRY:
        return _REGISTRY[tool_name]
    if tool_name.startswith("mcp_"):
        return _MCP_DEFAULT
    if tool_name.startswith("MCP") and tool_name.endswith("Tool"):
        return _MCP_DEFAULT
    return _GENERIC_TOOL_DEFAULT


def merge_runtime_hints(existing: Optional[Dict[str, Any]], fallback: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Merge instance-provided hints with registry fallback (instance wins)."""
    if existing and fallback:
        merged = dict(fallback)
        merged.update(existing)
        return merged
    return existing or fallback
