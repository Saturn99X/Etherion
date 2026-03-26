from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.services.bq_vector_search import BQVectorSearchService


@tool
async def bigquery_vector_search(
    tenant_id: str,
    query: str,
    top_k: int = 10,
    project_id: Optional[str] = None,
    kb_type: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform semantic search using BigQuery VECTOR_SEARCH on tenant KB.

    Input:
      - tenant_id (str, required)
      - query (str, required)
      - top_k (int, optional, default 10)
      - project_id (str, optional) to scope to a project
      - kb_type (str, optional) 'project' | 'personal'
      - job_id (str, optional) for cost tracking labels

    Output:
      {
        "results": [{"doc_id","text_chunk","file_uri","metadata","distance"}],
        "provider": "bigquery"
      }
    """
    tenant_id = str(tenant_id or "").strip()
    query = str(query or "").strip()
    if not tenant_id:
        raise ValueError("bigquery_vector_search requires 'tenant_id'.")
    if not query:
        raise ValueError("bigquery_vector_search requires 'query'.")

    top_k = int(top_k or 10)

    svc = BQVectorSearchService()
    rows = svc.search(
        tenant_id=tenant_id,
        query=query,
        top_k=top_k,
        project_id_filter=str(project_id) if project_id else None,
        kb_type=kb_type,
        job_id=job_id,
    )
    return {"results": rows, "provider": "bigquery"}


class BigQueryVectorSearchInput(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenancy isolation")
    query: str = Field(..., description="Semantic search query text")
    top_k: int = Field(10, description="Maximum number of results to return")
    project_id: Optional[str] = Field(None, description="Optional project scope filter")
    kb_type: Optional[str] = Field(
        None,
        description="Optional KB type filter: 'project' or 'personal'",
    )
    job_id: Optional[str] = Field(
        None,
        description="Optional job identifier for cost tracking and analytics",
    )


def _bigquery_vector_search_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = BigQueryVectorSearchInput.model_json_schema()
    except Exception:
        schema = BigQueryVectorSearchInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Call with an object containing tenant_id, query, optional top_k, "
            "project_id, kb_type, and job_id. The orchestrator will pass this "
            "object as input_data to bigquery_vector_search."
        ),
        "examples": [
            {
                "name": "project_kb_search",
                "input": {
                    "tenant_id": "tnt_123",
                    "query": "autonomous orchestrator design",
                    "project_id": "proj_abc",
                    "top_k": 10,
                },
            },
            {
                "name": "personal_kb_search",
                "input": {
                    "tenant_id": "tnt_123",
                    "query": "recent feedback about marketing campaigns",
                    "kb_type": "personal",
                    "top_k": 5,
                },
            },
        ],
    }

