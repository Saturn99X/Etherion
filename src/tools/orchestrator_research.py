# src/tools/orchestrator_research.py
import asyncio
import json
import os
from typing import Dict, List, Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field


# Define Custom Exception
class ResearchToolPermanentFailureError(Exception):
    """Custom exception for permanent failure in a research tool."""
    pass
# Initialize constants

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

# Resilient Helper Functions
async def _search_kb_bq(query: str) -> List[Dict[str, Any]]:
    """Helper function to search tenant KB using BigQuery VECTOR_SEARCH."""
    from src.services.bq_vector_search import BQVectorSearchService
    try:
        svc = BQVectorSearchService()
        # No project scope here; caller provides only query
        rows = svc.search(tenant_id=os.getenv("TENANT_ID", "0"), query=query, top_k=5)
        return rows or []
    except Exception as e:
        # Final attempt: return empty result on failure to avoid crashing orchestrator
        print(f"BigQuery VECTOR_SEARCH failed: {e}")
        return []

 

# Main Tool Implementation
@tool
async def orchestrator_research_tool(input_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    A unified, resilient, and concurrent research tool for the Orchestrator Agent.
    Accepts a JSON object with 'query' and 'search_types' (a list of 'text' and/or 'image').
    Returns a JSON object with 'text_results' and 'image_results'.
    """
    query = input_data.get("query")
    search_types = input_data.get("search_types", [])
    job_id = input_data.get("job_id")

    if not query:
        raise ValueError("The 'query' key is mandatory in the input.")

    # Always run KB + Web per directive (KB timeout 90s, Web timeout 210s)
    kb_timeout = int(input_data.get("kb_timeout_seconds", 90))
    web_timeout = int(input_data.get("web_timeout_seconds", 210))

    async def _kb_task():
        res = await asyncio.wait_for(_search_kb_bq(query), timeout=kb_timeout)
        return res

    async def _web_task():
        from src.tools.exa_search import exa_search
        # Map legacy inputs if present
        exa_extract = input_data.get("exa_extract")
        include_text = bool(input_data.get("exa_include_text", True))
        include_highlights = bool(input_data.get("exa_include_highlights", True))
        include_summary = bool(input_data.get("exa_include_summary", True))
        if isinstance(exa_extract, list):
            include_text = "text" in exa_extract if exa_extract else include_text
            include_highlights = "highlights" in exa_extract if exa_extract else include_highlights
            include_summary = "summary" in exa_extract if exa_extract else include_summary

        exa_params = {
            "query": query,
            "search_type": input_data.get("exa_search_type", "neural"),
            "num_results": int(input_data.get("exa_num_results", input_data.get("exa_limit", 20))),
            "include_text": include_text,
            "include_highlights": include_highlights,
            "include_summary": include_summary,
            "timeout_seconds": web_timeout,
        }
        # Include job tracing for EXA metering
        if job_id:
            exa_params["job_id"] = job_id
        res = await exa_search(exa_params)
        return res.get("results", [])

    tasks = [_kb_task(), _web_task()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: Dict[str, List[Any]] = {"kb_results": [], "web_results": []}
    kb_res, web_res = results
    if not isinstance(kb_res, Exception):
        output["kb_results"] = kb_res
    if not isinstance(web_res, Exception):
        output["web_results"] = web_res
    return output


class OrchestratorResearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Natural-language query for the orchestrator research pass.",
    )
    search_types: List[str] = Field(
        default_factory=list,
        description="Optional list of search types such as 'text' or 'image'. Currently informational.",
    )
    kb_timeout_seconds: int = Field(
        90,
        description="Timeout in seconds for KB (BigQuery) search before falling back to empty results.",
    )
    web_timeout_seconds: int = Field(
        210,
        description="Timeout in seconds for web (Exa) search before falling back to empty results.",
    )
    exa_extract: Optional[List[str]] = Field(
        None,
        description="Legacy list controlling which Exa fields to include: 'text', 'highlights', 'summary'.",
    )
    exa_include_text: bool = Field(
        True,
        description="Whether to include full text content from Exa results.",
    )
    exa_include_highlights: bool = Field(
        True,
        description="Whether to include highlighted passages from Exa results.",
    )
    exa_include_summary: bool = Field(
        True,
        description="Whether to include summary fields from Exa results.",
    )
    exa_search_type: str = Field(
        "neural",
        description="Exa search type, e.g. 'neural' or 'keyword'.",
    )
    exa_num_results: Optional[int] = Field(
        None,
        description="Preferred number of Exa results; falls back to exa_limit when omitted.",
    )
    exa_limit: Optional[int] = Field(
        None,
        description="Legacy limit for Exa results; used when exa_num_results is not provided.",
    )
    job_id: Optional[str] = Field(
        None,
        description="Optional job identifier used for tracing and metering Exa usage.",
    )


def _orchestrator_research_tool_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = OrchestratorResearchInput.model_json_schema()
    except Exception:
        schema = OrchestratorResearchInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Unified research for the orchestrator. Provide query and optional parameters to tune KB/web timeouts "
            "and Exa result shape. Tenant and environment configuration are handled by the platform."
        ),
        "examples": [
            {
                "name": "default_dual_search",
                "input": {
                    "query": "Summarize recent changes in the Etherion orchestrator architecture",
                },
            },
            {
                "name": "web_focus_with_summaries",
                "input": {
                    "query": "latest best practices for multi-tenant vector search on BigQuery",
                    "exa_search_type": "neural",
                    "exa_num_results": 10,
                    "exa_include_text": False,
                    "exa_include_highlights": True,
                    "exa_include_summary": True,
                    "web_timeout_seconds": 180,
                },
            },
        ],
    }


orchestrator_research_tool.args_schema = OrchestratorResearchInput
