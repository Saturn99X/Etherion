# src/tools/vertex_ai_search.py
import asyncio
import json
import os
from typing import Dict, List, Any, Optional
from src.services.pricing.cost_tracker import CostTracker
from google.api_core.client_options import ClientOptions
from langchain_core.tools import tool
from google.api_core import retry as gretry
from pydantic import BaseModel, Field
try:
    from google.cloud import discoveryengine_v1 as discoveryengine
except Exception:  # pragma: no cover
    discoveryengine = None  # type: ignore

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "global")

# Hard gate per Phase 13: default backend is BigQuery. Only enable Vertex when explicitly set.
def _vertex_enabled() -> bool:
    kb_backend = os.getenv("KB_BACKEND", "bq").lower()
    if kb_backend != "vertex":
        return False
    flag = os.getenv("ENABLE_VERTEX_AI_SEARCH", "false").lower() in ("1", "true", "yes", "on")
    return flag

def _tenant_datastore_id(tenant_id: Optional[str]) -> str:
    # Per Phase 13, one datastore per tenant
    if not tenant_id:
        return os.getenv("DEFAULT_DATA_STORE_ID", "etherion-data-connector_gcs_store")
    return f"tenant-kb-{tenant_id}"

@tool
async def vertex_ai_search(query: str, tenant_id: Optional[str] = None, timeout_seconds: int = 60, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Performs a search using Vertex AI Search.

    NOTE: Disabled by default (KB_BACKEND=bq). To enable, set env KB_BACKEND=vertex and ENABLE_VERTEX_AI_SEARCH=true.
    
    Args:
        query: The search query string
        
    Returns:
        List of search results with title, link, and snippet
    """
    # Early exit when Vertex is disabled (default state) or client not available
    if not _vertex_enabled() or discoveryengine is None:
        return []
    try:
        client_options = (
            ClientOptions(api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com")
            if LOCATION != "global"
            else None
        )
        client = discoveryengine.SearchServiceClient(client_options=client_options)
        data_store_id = _tenant_datastore_id(tenant_id)
        serving_config = client.serving_config_path(
            project=PROJECT_ID,
            location=LOCATION,
            data_store=data_store_id,
            serving_config="default_config",
        )

        request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=100,
        )
        
        # Execute the search synchronously in a thread pool
        response = await asyncio.to_thread(
            client.search,
            request=request,
            retry=gretry.Retry(deadline=timeout_seconds),
            timeout=timeout_seconds,
        )
        
        # Process the results
        results = []
        for result in response.results:
            # Convert the protobuf Struct to a JSON string then to a dict
            derived_data = json.loads(result.document.derived_struct_data.to_json())
            results.append(derived_data)
        
        # Best-effort: record 1 enterprise query for billing if job_id is provided
        if job_id:
            try:
                tracker = CostTracker()
                await tracker.record_vertex_search(job_id, enterprise_q=1)
            except Exception:
                pass

        return results
        
    except Exception as e:
        return [{"error": f"An error occurred during Vertex AI Search: {e}"}]


class VertexAISearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Search query string to send to Vertex AI Search.",
    )
    tenant_id: Optional[str] = Field(
        None,
        description=(
            "Tenant identifier used to choose the Discovery Engine datastore; when omitted, a default "
            "datastore is used."
        ),
    )
    timeout_seconds: int = Field(
        60,
        description="Deadline in seconds for the Vertex AI Search request.",
    )
    job_id: Optional[str] = Field(
        None,
        description="Optional job identifier used for billing and analytics via CostTracker.",
    )


def _vertex_ai_search_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = VertexAISearchInput.model_json_schema()
    except Exception:
        schema = VertexAISearchInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Perform a knowledge base search using Vertex AI Search. Provide a query string and optional tenant_id, "
            "timeout_seconds, and job_id. Vertex must be enabled via environment flags."
        ),
        "examples": [
            {
                "name": "basic_vertex_search",
                "input": {
                    "query": "multi-tenant orchestrator runtime design",
                },
            },
            {
                "name": "tenant_scoped_vertex_search",
                "input": {
                    "query": "recent product launch announcements",
                    "tenant_id": "123",
                    "timeout_seconds": 45,
                    "job_id": "job_vertex_abc",
                },
            },
        ],
    }