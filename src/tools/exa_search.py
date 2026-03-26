import os
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field
from src.services.pricing.cost_tracker import CostTracker
from langchain_core.tools import tool


EXA_API_KEY = os.getenv("EXA_API_KEY")
EXA_BASE_URL = os.getenv("EXA_BASE_URL", "https://api.exa.ai")


async def _post_json(
    client: httpx.AsyncClient,
    path: str,
    body: Dict[str, Any],
    timeout_seconds: int,
) -> Dict[str, Any]:
    if not EXA_API_KEY:
        raise ValueError("EXA_API_KEY is not configured.")
    headers = {
        "x-api-key": EXA_API_KEY,
        "Content-Type": "application/json",
    }
    resp = await client.post(
        f"{EXA_BASE_URL}{path}", headers=headers, json=body, timeout=timeout_seconds
    )
    resp.raise_for_status()
    return resp.json()


@tool
async def exa_search(
    query: str,
    tenant_id: Optional[str] = None,
    search_type: str = "neural",
    num_results: int = 20,
    include_text: bool = True,
    include_highlights: bool = True,
    include_summary: bool = True,
    timeout_seconds: int = 120,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exa web search with optional content retrieval.

    Input:
      - query (str, required)
      - search_type (str): "neural" | "keyword" | "auto" | "fast" (default: neural)
      - num_results (int): default 20 (max 100 for neural)
      - include_text (bool): if true, fetch page text via /contents (default: True)
      - include_highlights (bool): if true, fetch highlights via /contents (default: True)
      - include_summary (bool): if true, fetch summary via /contents (default: True)
      - timeout_seconds (int): request timeout (default 120)

    Output:
      {
        "query": str,
        "results": [
          {"id","title","url","score","publishedDate","text","highlights","summary","status"}
        ],
        "provider": "exa"
      }
    """
    if not query:
        raise ValueError("exa_search requires 'query'.")

    num_results = int(num_results or 20)
    timeout_seconds = int(timeout_seconds or 120)

    # 1) Search
    search_body: Dict[str, Any] = {
        "query": query,
        "type": search_type,
        "numResults": num_results,
    }

    async with httpx.AsyncClient() as client:
        try:
            search_json = await _post_json(client, "/search", search_body, timeout_seconds)
        except httpx.HTTPStatusError as e:
            return {"query": query, "results": [], "provider": "exa", "error": str(e)}

        raw_results = search_json.get("results", [])
        urls: List[str] = [r.get("url") for r in raw_results if r.get("url")]

        # Instrument EXA search request by bucket if job_id provided
        if job_id:
            try:
                tracker = CostTracker()
                kind = "keyword" if search_type == "keyword" else ("auto_fast" if search_type in ("auto", "fast", "auto_fast") else "neural")
                results_count = min(len(raw_results), num_results)
                await tracker.record_exa_search(job_id, kind=kind, results=results_count)
            except Exception:
                pass

        # 2) Optional contents fetch (use 'urls' instead of deprecated 'ids')
        contents: Dict[str, Any] = {}
        if urls and (include_text or include_highlights or include_summary):
            contents_body: Dict[str, Any] = {"urls": urls}
            if include_text:
                contents_body["text"] = True
            if include_highlights:
                contents_body["highlights"] = {}  # Empty object for defaults
            if include_summary:
                contents_body["summary"] = {}  # Empty object for defaults
            try:
                contents = await _post_json(client, "/contents", contents_body, timeout_seconds)
            except httpx.HTTPStatusError:
                contents = {}

            # Instrument EXA contents pages per type
            if job_id:
                try:
                    tracker = CostTracker()
                    pages = len(urls)
                    if include_text and pages:
                        await tracker.record_exa_contents(job_id, kind="text", pages=pages)
                    if include_highlights and pages:
                        await tracker.record_exa_contents(job_id, kind="highlights", pages=pages)
                    if include_summary and pages:
                        await tracker.record_exa_contents(job_id, kind="summary", pages=pages)
                except Exception:
                    pass

    # Map contents by URL (since 'urls' input)
    content_map: Dict[str, Dict[str, Any]] = {}
    statuses_map: Dict[str, str] = {}
    if isinstance(contents, dict):
        for entry in contents.get("results", []):
            content_url = entry.get("url")
            if content_url:
                content_map[content_url] = entry
        for status_entry in contents.get("statuses", []):
            sid = status_entry.get("id")  # Could be URL or ID
            statuses_map[sid] = status_entry.get("status", "unknown")

    normalized: List[Dict[str, Any]] = []
    for item in raw_results:
        item_url = item.get("url")
        c = content_map.get(item_url, {})
        status = statuses_map.get(item_url, "success")  # Default to success if no contents
        normalized.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "url": item_url,
                "score": item.get("score"),
                "publishedDate": item.get("publishedDate"),
                "text": c.get("text"),
                "highlights": c.get("highlights"),
                "summary": c.get("summary"),
                "status": status,  # e.g., "success", "failed"
            }
        )

    return {"query": query, "results": normalized, "provider": "exa"}


class ExaSearchInput(BaseModel):
    query: str = Field(..., description="Search query text")
    search_type: str = Field(
        "neural",
        description="Search mode: 'neural' | 'keyword' | 'auto' | 'fast'",
    )
    num_results: int = Field(
        20,
        description="Number of results to return (default 20, max 100 for neural)",
    )
    include_text: bool = Field(
        True,
        description="If true, fetch page text via /contents",
    )
    include_highlights: bool = Field(
        True,
        description="If true, fetch highlights via /contents",
    )
    include_summary: bool = Field(
        True,
        description="If true, fetch summary via /contents",
    )
    timeout_seconds: int = Field(
        120,
        description="Request timeout in seconds",
    )
    job_id: Optional[str] = Field(
        None,
        description="Optional job identifier for cost tracking",
    )


def _exa_search_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = ExaSearchInput.model_json_schema()
    except Exception:
        schema = ExaSearchInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Call with an object containing query and optional search_type, num_results, "
            "include_text, include_highlights, include_summary, timeout_seconds, and job_id."
        ),
        "examples": [
            {
                "name": "default_neural_search",
                "input": {
                    "query": "latest updates on Gemini 2.5",
                    "num_results": 10,
                },
            },
            {
                "name": "fast_keyword_search_with_highlights",
                "input": {
                    "query": "Etherion platform architecture",
                    "search_type": "keyword",
                    "num_results": 5,
                    "include_text": False,
                    "include_highlights": True,
                    "include_summary": False,
                },
            },
        ],
    }