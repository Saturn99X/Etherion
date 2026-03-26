from __future__ import annotations

from typing import Any, Dict, List, Optional
import os

from src.services.bigquery_service import BigQueryService
from src.services.bq_schema_manager import ensure_tenant_media_object_kb
from src.services.embedding_service import EmbeddingService


class BQMediaObjectSearchService:
    
    def __init__(
        self,
        project_id: Optional[str] = None,
        bq: Optional[BigQueryService] = None,
        embedder: Optional[EmbeddingService] = None,
    ) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")
        self.bq = bq or BigQueryService(project_id=self.project_id)
        self._embedder = embedder

    def search(
        self,
        *,
        tenant_id: str,
        query: str,
        top_k: int = 10,
        content_type_prefix: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        try:
            ensure_tenant_media_object_kb(self.bq.client, str(tenant_id))
        except Exception:
            pass

        dataset_id = f"tnt_{tenant_id}"
        embeddings_ref = f"{self.project_id}.{dataset_id}.media_object_embeddings"

        filters: List[str] = []
        params: Dict[str, Any] = {
            "query": str(query),
            "top_k": int(top_k),
        }
        if content_type_prefix:
            filters.append("STARTS_WITH(content_type, @content_type_prefix)")
            params["content_type_prefix"] = str(content_type_prefix)
        where_clause = (" WHERE " + " AND ".join(filters)) if filters else ""

        embedder = self._embedder or EmbeddingService(project_id=self.project_id)
        query_vec = embedder.embed_texts([str(query)], task="RETRIEVAL_QUERY")
        vec = query_vec[0] if query_vec else []
        params["query_vec"] = vec
        sql = f"""
        SELECT base, distance
        FROM VECTOR_SEARCH(
          (SELECT tenant_id, gcs_uri, content_type, size_bytes, updated_at, metadata, vector_embedding FROM `{embeddings_ref}`{where_clause}),
          'vector_embedding',
          (SELECT @query_vec AS query_embedding),
          'query_embedding',
          top_k => @top_k
        )
        """

        rows = self.bq.query(
            sql,
            params=params,
            labels={"tenant_id": str(tenant_id), "component": "bq_media_object_search"},
            job_id=job_id,
        )

        out: List[Dict[str, Any]] = []
        for r in rows:
            base = r.get("base") or {}
            try:
                base_obj = base if hasattr(base, "items") else dict(base)
            except Exception:
                base_obj = {}
            out.append(
                {
                    "gcs_uri": base_obj.get("gcs_uri"),
                    "content_type": base_obj.get("content_type"),
                    "metadata": base_obj.get("metadata") or {},
                    "distance": r.get("distance"),
                }
            )
        return out
