from __future__ import annotations

from typing import Any, Dict, List, Optional
import os

from src.services.bigquery_service import BigQueryService
from src.services.embedding_service import EmbeddingService
from src.services.bq_schema_manager import ensure_tenant_kb


class BQVectorSearchService:
    """BigQuery VECTOR_SEARCH service for tenant KB.

    - Uses multimodal pipeline by default (multimodalembedding@001, 1408-D)
    - Falls back to legacy docs table if multimodal disabled
    - Executes VECTOR_SEARCH against `project.tnt_{tenant}.multimodal_docs` or `docs`
    - Returns rows with distance for ranking
    """

    def __init__(self, project_id: Optional[str] = None, bq: Optional[BigQueryService] = None, embedder: Optional[Any] = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")
        self.bq = bq or BigQueryService(project_id=self.project_id)
        
        self.use_multimodal = os.getenv("KB_MULTIMODAL_ENABLED", "true").lower() == "true"
        
        if embedder:
            self.embedder = embedder
        else:
            if self.use_multimodal:
                from src.services.multimodal_embedding_service import MultimodalEmbeddingService
                self.embedder = MultimodalEmbeddingService(project_id=self.project_id)
            else:
                self.embedder = EmbeddingService(project_id=self.project_id)

    def search(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 10,
        project_id_filter: Optional[str] = None,
        kb_type: Optional[str] = None,
        job_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        search_job_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Ensure tenant dataset and docs table exist before VECTOR_SEARCH.
        # This avoids 404 errors for newly created tenants that haven't ingested any KB docs yet.
        try:
            if self.use_multimodal:
                from src.services.bq_schema_manager import ensure_tenant_multimodal_kb
                ensure_tenant_multimodal_kb(self.bq.client, str(tenant_id))
            else:
                ensure_tenant_kb(self.bq.client, str(tenant_id))
        except Exception:
            pass

        # 1) Embed query
        vecs = self.embedder.embed_texts([query])
        query_vec: List[float] = vecs[0] if vecs else []
        if not query_vec:
            return []

        # 2) Build SQL; wrap table in a subselect to allow metadata filters
        if self.use_multimodal:
            table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
            base_select_cols = "doc_id, gcs_uri, filename, part_name, part_number, total_parts, chapter_count, metadata, vector_embedding"
        else:
            table_ref = f"{self.project_id}.tnt_{tenant_id}.docs"
            base_select_cols = "doc_id, text_chunk, file_uri, metadata, vector_embedding"

        filters = []
        params: Dict[str, Any] = {
            "query_vec": [float(x) for x in query_vec],
            "top_k": int(top_k),
        }
        if project_id_filter:
            filters.append("JSON_VALUE(metadata, '$.project_id') = @project_id")
            params["project_id"] = str(project_id_filter)
        if kb_type:
            filters.append("JSON_VALUE(metadata, '$.kb_type') = @kb_type")
            params["kb_type"] = str(kb_type)
        if thread_id:
            filters.append("JSON_VALUE(metadata, '$.thread_id') = @thread_id")
            params["thread_id"] = str(thread_id)
        if search_job_id:
            filters.append("JSON_VALUE(metadata, '$.job_id') = @search_job_id")
            params["search_job_id"] = str(search_job_id)
            
        where_clause = (" WHERE " + " AND ".join(filters)) if filters else ""

        sql = f"""
        SELECT base, distance
        FROM VECTOR_SEARCH(
          (SELECT {base_select_cols} FROM `{table_ref}`{where_clause}),
          'vector_embedding',
          (SELECT @query_vec AS query_embedding),
          'query_embedding',
          top_k => @top_k
        )
        """

        rows = self.bq.query(sql, params=params, labels={"tenant_id": str(tenant_id), "component": "bq_vector_search"}, job_id=job_id)
        out: List[Dict[str, Any]] = []
        for r in rows:
            base = r.get("base") or {}
            try:
                if hasattr(base, "items"):
                    base_obj: Any = base
                else:
                    base_obj = dict(base)
            except Exception:
                base_obj = {}
            if self.use_multimodal:
                out.append(
                    {
                        "doc_id": base_obj.get("doc_id"),
                        "metadata": base_obj.get("metadata"),
                        "gcs_uri": base_obj.get("gcs_uri"),
                        "filename": base_obj.get("filename"),
                        "part_name": base_obj.get("part_name"),
                        "part_number": base_obj.get("part_number"),
                        "total_parts": base_obj.get("total_parts"),
                        "chapter_count": base_obj.get("chapter_count"),
                        "metadata": base_obj.get("metadata") or {},
                        "distance": float(r.get("distance", 0.0)),
                    }
                )
            else:
                out.append(
                    {
                        "doc_id": base_obj.get("doc_id"),
                        "text_chunk": base_obj.get("text_chunk"),
                        "file_uri": base_obj.get("file_uri"),
                        "metadata": base_obj.get("metadata") or {},
                    "distance": r.get("distance"),
                }
            )
        return out
