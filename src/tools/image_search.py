from typing import Any, Dict, List, Optional

from langchain_core.tools import tool


@tool
async def image_search(
    query: str,
    tenant_id: Optional[str] = None,
    num_results: int = 10,
    safe_search: str = "moderate",
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Search for images by query and return a list of results."""
    if not query:
        raise ValueError("image_search requires 'query'.")
    if num_results <= 0:
        num_results = 10

    results: List[Dict[str, Any]] = []
    return {"query": query, "results": results, "provider": "image_search"}
