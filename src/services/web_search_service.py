"""
Web Search Service (Grounded Search integration)

Provides a unified abstraction for mandatory web search using Exa Search.

Refs:
- Vertex AI Search/Discovery Engine SearchServiceClient
- Grounding with Google Search (enable in datastore; set request fields)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from src.tools.exa_search import exa_search


class WebSearchService:
    async def search(self, query: str, num_results: int = 20, job_id: str | None = None) -> List[Dict[str, Any]]:
        params = {
            "query": query,
            "search_type": "neural",
            "num_results": num_results,
            "include_text": True,
            "include_highlights": True,
            "include_summary": True,
            "job_id": job_id,
        }
        data = await exa_search(params)
        return data.get("results", [])


