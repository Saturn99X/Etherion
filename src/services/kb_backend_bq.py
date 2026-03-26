"""BigQuery KB backend — wraps existing kb_query_service."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .kb_backend import KBBackend


class BigQueryKBBackend(KBBackend):
    async def search(
        self,
        tenant_id: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        project_id: Optional[str] = None,
        kb_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from src.services.kb_query_service import KBQueryService
        svc = KBQueryService()
        results = await svc.search(
            tenant_id=tenant_id,
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            project_id=project_id,
            kb_type=kb_type,
        )
        return results

    async def upsert(self, tenant_id: str, doc_id: str, text: str, embedding: List[float], metadata: Dict[str, Any]) -> None:
        raise NotImplementedError("BigQuery backend is read-only from the application layer.")

    async def delete(self, tenant_id: str, doc_id: str) -> None:
        raise NotImplementedError("BigQuery backend is read-only from the application layer.")

    async def health_check(self) -> bool:
        try:
            from src.services.bigquery_service import BigQueryService
            svc = BigQueryService()
            return svc.client is not None
        except Exception:
            return False
