"""pgvector search tool — drop-in replacement for bigquery_vector_tool."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def pgvector_search(
    tenant_id: str,
    query: str,
    top_k: int = 10,
    project_id: Optional[str] = None,
    kb_type: Optional[str] = None,
    job_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search the pgvector knowledge base. Returns list of {doc_id, text_chunk, score, metadata, storage_uri}."""
    from src.services.kb_backend import get_kb_backend
    from src.services.embedding_service import EmbeddingService

    embedding_svc = EmbeddingService()
    query_embedding = await embedding_svc.embed_text(query)

    backend = get_kb_backend()
    results = await backend.search(
        tenant_id=tenant_id,
        query=query,
        query_embedding=query_embedding,
        top_k=top_k,
        project_id=project_id,
        kb_type=kb_type,
    )
    logger.debug("pgvector_search: tenant=%s query=%r top_k=%d → %d results", tenant_id, query, top_k, len(results))
    return results
