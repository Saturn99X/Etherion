"""
Content Repository Service

Job-scoped, AI-only content repository access layer.

Responsibilities:
- List assets for a job (filters applied, origin=ai enforced)
- Get single asset metadata
- Provide access to asset bytes following retrieval policy:
  - If size_bytes ≤ 5 MB → return base64 inline
  - Otherwise → return 5-minute signed URL

Security:
- Tenant isolation via dataset/table naming (tnt_{tenant_id}.assets)
- No public URLs; signed URLs only with short expiry

WHY: Implements Phase 11 foundation without exposing human content. BigQuery is
source of truth; GCS holds private bytes. Vertex AI Search integration happens
via CDC from BigQuery and is out of scope here.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import timedelta
import time
from typing import Any, Dict, List, Optional, Tuple


MAX_INLINE_BYTES: int = 5 * 1024 * 1024  # 5 MB


@dataclass
class AssetRecord:
    asset_id: str
    job_id: str
    tenant_id: str
    agent_name: Optional[str]
    agent_id: Optional[str]
    user_id: Optional[str]
    mime_type: Optional[str]
    gcs_uri: str
    filename: Optional[str]
    size_bytes: int
    created_at: Optional[str]
    metadata: Dict[str, Any]


class ContentRepositoryService:
    def __init__(self, tenant_id: str, project_id: Optional[str] = None) -> None:
        self.tenant_id: str = str(tenant_id)
        self.project_id: str = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT not configured")

        self.dataset_id: str = f"tnt_{self.tenant_id}"
        self.table_id: str = "assets"
        self._bq = None
        self._storage = None

    @property
    def bq(self):
        if self._bq is None:
            from google.cloud import bigquery
            self._bq = bigquery.Client(project=self.project_id)
        return self._bq

    @property
    def storage(self):
        if self._storage is None:
            from google.cloud import storage
            self._storage = storage.Client(project=self.project_id)
        return self._storage

    def _table_ref(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    def _row_to_asset(self, row: Any) -> AssetRecord:
        # BigQuery JSON is represented as dict already
        metadata: Dict[str, Any] = row.get("metadata") or {}
        return AssetRecord(
            asset_id=row.get("asset_id"),
            job_id=row.get("job_id"),
            tenant_id=row.get("tenant_id"),
            agent_name=row.get("agent_name"),
            agent_id=row.get("agent_id"),
            user_id=row.get("user_id"),
            mime_type=row.get("mime_type"),
            gcs_uri=row.get("gcs_uri"),
            filename=row.get("filename"),
            size_bytes=int(row.get("size_bytes") or 0),
            created_at=row.get("created_at"),
            metadata=metadata,
        )

    def list_assets(
        self,
        job_id: str,
        page_size: int = 50,
        page_token: Optional[int] = None,
        mime_type: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Tuple[List[AssetRecord], Optional[int]]:
        """
        List AI-origin assets for a given job, ordered by created_at desc.

        Pagination uses integer offset as page_token for simplicity.
        """
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        offset: int = max(0, page_token or 0)

        # Build filters (origin=ai enforced)
        filters: List[str] = [
            "tenant_id = @tenant_id",
            "job_id = @job_id",
            "JSON_VALUE(metadata, '$.origin') = 'ai'",
        ]
        params: List[bigquery.ScalarQueryParameter] = [
            bigquery.ScalarQueryParameter("tenant_id", "STRING", self.tenant_id),
            bigquery.ScalarQueryParameter("job_id", "STRING", job_id),
        ]

        if mime_type:
            filters.append("mime_type = @mime_type")
            params.append(bigquery.ScalarQueryParameter("mime_type", "STRING", mime_type))
        if tag:
            # tags is REPEATED STRING
            filters.append("@tag IN UNNEST(tags)")
            params.append(bigquery.ScalarQueryParameter("tag", "STRING", tag))

        where_clause = " AND ".join(filters)
        query = f"""
        SELECT asset_id, job_id, tenant_id, agent_name, agent_id, user_id,
               mime_type, gcs_uri, filename, size_bytes, created_at, metadata
        FROM `{self._table_ref()}`
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT @limit OFFSET @offset
        """

        params.extend([
            bigquery.ScalarQueryParameter("limit", "INT64", int(page_size)),
            bigquery.ScalarQueryParameter("offset", "INT64", int(offset)),
        ])

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=params)
            rows = self.bq.query(query, job_config=job_config).result()
        except NotFound:
            # Dataset/table missing → return empty
            return [], None

        assets: List[AssetRecord] = [self._row_to_asset(r) for r in rows]
        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound
        next_token: Optional[int] = None
        if len(assets) == page_size:
            next_token = offset + page_size
        return assets, next_token

    def get_asset(self, asset_id: str) -> Optional[AssetRecord]:
        """
        Fetch single AI-origin asset by id for this tenant.

        Includes short retries to account for BigQuery streaming insert latency.
        Also tolerates metadata stored as JSON or JSON-encoded STRING.
        """
        from google.cloud import bigquery
        base_query = f"""
        SELECT asset_id, job_id, tenant_id, agent_name, agent_id, user_id,
               mime_type, gcs_uri, filename, size_bytes, created_at, metadata
        FROM `{self._table_ref()}`
        WHERE tenant_id = @tenant_id
          AND asset_id = @asset_id
        LIMIT 1
        """
        params = [
            bigquery.ScalarQueryParameter("tenant_id", "STRING", self.tenant_id),
            bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id),
        ]

        delays = [0.2, 0.5, 1.0, 2.0, 3.0, 5.0]
        for i, delay in enumerate([0.0] + delays):
            if delay:
                time.sleep(delay)
            try:
                job_config = bigquery.QueryJobConfig(query_parameters=params)
                rows = list(self.bq.query(base_query, job_config=job_config).result())
            except Exception:
                rows = []
            if rows:
                return self._row_to_asset(rows[0])
        return None

    def get_access(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """
        Apply retrieval policy and return either base64 content or a signed URL.
        """
        record = self.get_asset(asset_id)
        if not record:
            return None

        bucket_name, blob_name = self._parse_gcs_uri(record.gcs_uri)
        bucket = self.storage.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        if int(record.size_bytes) <= MAX_INLINE_BYTES:
            # Inline base64
            data: bytes = blob.download_as_bytes()
            b64 = base64.b64encode(data).decode("utf-8")
            return {
                "asset_id": record.asset_id,
                "filename": record.filename,
                "mime_type": record.mime_type,
                "base64": f"data:{record.mime_type};base64,{b64}",
                "size_bytes": record.size_bytes,
            }

        # Signed URL (5 minutes)
        url = blob.generate_signed_url(version="v4", expiration=timedelta(minutes=5), method="GET")
        return {
            "asset_id": record.asset_id,
            "filename": record.filename,
            "mime_type": record.mime_type,
            "url": url,
            "expires_in_seconds": 300,
            "size_bytes": record.size_bytes,
        }

    @staticmethod
    def _parse_gcs_uri(gcs_uri: str) -> Tuple[str, str]:
        if not gcs_uri.startswith("gs://"):
            raise ValueError("Invalid GCS URI")
        path = gcs_uri[5:]
        parts = path.split("/", 1)
        if len(parts) != 2:
            raise ValueError("Invalid GCS URI path")
        return parts[0], parts[1]
