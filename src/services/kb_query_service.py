"""
KB Query Service (BigQuery)

Searches tenant knowledge base content stored in BigQuery per Phase 13.
Table expectation (per ev.md): tnt_{tenant_id}.docs with columns:
- doc_id STRING, tenant_id STRING, text_chunk STRING, metadata JSON, file_uri STRING (optional)

Filters:
- project_id via JSON_VALUE(metadata, '$.project_id')
- kb_type via JSON_VALUE(metadata, '$.kb_type') = 'project' | 'personal'
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.services.bigquery_service import BigQueryService


class KBQueryService:
    def __init__(self, project_id: Optional[str] = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")
        self.bq = BigQueryService(project_id=self.project_id)
        self.use_multimodal = os.getenv("KB_MULTIMODAL_ENABLED", "true").lower() == "true"

    def search(
        self,
        tenant_id: str,
        query: str,
        project_id: Optional[str] = None,
        kb_type: Optional[str] = None,
        limit: int = 20,
        job_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        search_job_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        dataset_id = f"tnt_{tenant_id}"
        
        if self.use_multimodal:
            table_ref = f"{self.project_id}.{dataset_id}.multimodal_docs"
            text_col = "metadata"
            base_cols = "doc_id, metadata, gcs_uri, filename, part_name, part_number, total_parts, chapter_count, metadata"
        else:
            table_ref = f"{self.project_id}.{dataset_id}.docs"
            text_col = "text_chunk"
            base_cols = "doc_id, text_chunk, file_uri, metadata"

        # Build LIKE pattern (case-insensitive)
        pattern = f"%{query.lower()}%"

        filters = [
            f"LOWER({text_col}) LIKE @pattern",
        ]
        params = {
            "pattern": pattern,
        }

        if project_id:
            filters.append("JSON_VALUE(metadata, '$.project_id') = @project_id")
            params["project_id"] = project_id

        if kb_type:
            filters.append("JSON_VALUE(metadata, '$.kb_type') = @kb_type")
            params["kb_type"] = kb_type

        if thread_id:
            filters.append("JSON_VALUE(metadata, '$.thread_id') = @thread_id")
            params["thread_id"] = thread_id

        if search_job_id:
            filters.append("JSON_VALUE(metadata, '$.job_id') = @search_job_id")
            params["search_job_id"] = search_job_id

        where_clause = " AND ".join(filters)
        sql = f"""
        SELECT {base_cols}
        FROM `{table_ref}`
        WHERE {where_clause}
        LIMIT @limit
        """
        params["limit"] = int(limit)

        try:
            rows = self.bq.query(
                sql,
                params=params,
                labels={"tenant_id": str(tenant_id), "component": "kb_query_service"},
                job_id=job_id,
            )
            out: List[Dict[str, Any]] = []
            for r in rows:
                if self.use_multimodal:
                    out.append({
                        "doc_id": r.get("doc_id"),
                        "metadata": r.get("metadata"),
                        "gcs_uri": r.get("gcs_uri"),
                        "filename": r.get("filename"),
                        "part_name": r.get("part_name"),
                        "metadata": r.get("metadata") or {},
                    })
                else:
                    out.append({
                        "doc_id": r.get("doc_id"),
                        "text_chunk": r.get("text_chunk"),
                        "file_uri": r.get("file_uri"),
                        "metadata": r.get("metadata") or {},
                    })
            return out
        except Exception:
            # Table may not exist yet or other query error; return empty safely
            return []
