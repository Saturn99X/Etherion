from __future__ import annotations

import hashlib
import json
import os
import time
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import timedelta

from src.services.bigquery_service import BigQueryService
from src.services.bq_schema_manager import ensure_tenant_kb
from src.services.pricing.cost_tracker import CostTracker


@dataclass
class RepositoryAsset:
    asset_id: str
    job_id: Optional[str]
    filename: str
    mime_type: str
    size_bytes: int
    gcs_uri: str
    created_at: str
    download_url: Optional[str] = None
    preview_base64: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RepositoryService:
    """Repository: lists assets from BigQuery assets table for the tenant.

    Note: Does not filter by metadata.origin so that both user- and AI-origin
    assets are visible to the owning tenant (isolation is enforced by dataset).
    """

    def __init__(self, tenant_id: int, project_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")
        self.bq = BigQueryService(project_id=self.project_id)
        self._storage = None

    @property
    def storage(self):
        if self._storage is None:
            from google.cloud import storage
            self._storage = storage.Client(project=self.project_id)
        return self._storage

    def _table_ref(self) -> str:
        return f"{self.project_id}.tnt_{self.tenant_id}.assets"

    def list_assets(self, limit: int = 50, job_id: Optional[str] = None, origin: Optional[str] = "ai") -> List[RepositoryAsset]:
        # If the tenant dataset/table doesn't exist yet, return empty gracefully
        dataset_id = f"tnt_{self.tenant_id}"
        if not self.bq.dataset_exists(dataset_id) or not self.bq.table_exists(dataset_id, "assets"):
            return []

        filters: List[str] = []
        # Build parameter dict for BigQueryService
        param_dict: Dict[str, Any] = {}
        if job_id:
            filters.append("job_id = @job_id")
            param_dict["job_id"] = job_id
        if origin:
            filters.append("JSON_VALUE(metadata, '$.origin') = @origin")
            param_dict["origin"] = origin

        where_clause = " AND ".join(filters)
        where_sql = f"WHERE {where_clause}" if where_clause else ""
        sql = f"""
        SELECT asset_id, job_id, filename, mime_type, size_bytes, gcs_uri, created_at, metadata
        FROM `{self._table_ref()}`
        {where_sql}
        ORDER BY created_at DESC
        LIMIT @limit
        """
        param_dict["limit"] = int(limit)

        try:
            rows = self.bq.query(
                sql,
                params=param_dict,
                labels={
                    "tenant_id": str(self.tenant_id),
                    "component": "repository_service",
                },
            )
            assets: List[RepositoryAsset] = []
            for r in rows:
                assets.append(
                    RepositoryAsset(
                        asset_id=r.get("asset_id"),
                        job_id=r.get("job_id"),
                        filename=r.get("filename"),
                        mime_type=r.get("mime_type"),
                        size_bytes=int(r.get("size_bytes") or 0),
                        gcs_uri=r.get("gcs_uri"),
                        created_at=str(r.get("created_at")),
                        metadata=r.get("metadata"),
                    )
                )
            return assets
        except Exception:
            # On any query/iteration error (e.g., dataset not found due to race), return empty safely
            return []

    # --- AI artifact creation ---
    def _tenant_bucket(self, suffix: str = "assets") -> Any:
        prefix = os.getenv("GCS_BUCKET_PREFIX", "tnt")
        bucket_name = f"{prefix}-{self.tenant_id}-{suffix}"
        bucket = self.storage.bucket(bucket_name)
        if not bucket.exists():
            location = os.getenv("GCS_BUCKET_LOCATION", "US")
            bucket = self.storage.create_bucket(bucket_name, location=location)
            bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            bucket.patch()
        return bucket

    def create_ai_asset(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        *,
        job_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> RepositoryAsset:
        """Create an AI-generated artifact in the repository.

        - Uploads content to private GCS bucket `{prefix}-{tenant_id}-assets` under `ai/` path.
        - Inserts a row into BigQuery `tnt_{tenant_id}.assets` with `metadata.origin='ai'` and provided title.
        - Returns the created RepositoryAsset.
        """
        bucket = self._tenant_bucket("assets")
        content_hash = hashlib.sha256(content).hexdigest()
        folder = f"ai/{job_id or 'general'}"
        object_name = f"{folder}/{content_hash}/{filename}"
        blob = bucket.blob(object_name)
        blob.upload_from_string(content, content_type=mime_type)
        gcs_uri = f"gs://{bucket.name}/{object_name}"

        if job_id:
            try:
                async def _record() -> None:
                    tracker = CostTracker()
                    await tracker.record_gcs_upload(job_id, bytes_uploaded=len(content), tenant_id=str(self.tenant_id))

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_record())
                except RuntimeError:
                    asyncio.run(_record())
            except Exception:
                pass

        asset_id = hashlib.md5((str(self.tenant_id) + gcs_uri).encode()).hexdigest()
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Compose metadata
        meta: Dict[str, Any] = {
            "origin": "ai",
            "kb_type": "ai_repo",
        }
        if title:
            meta["title"] = title
        if metadata_extra:
            meta.update(metadata_extra)

        # Always serialize metadata to JSON string to be compatible with tables
        # that may still have metadata typed as STRING. BigQuery JSON fields also
        # accept valid JSON strings.
        metadata_value: Any = json.dumps(meta)

        row = {
            "asset_id": asset_id,
            "job_id": job_id,
            "tenant_id": str(self.tenant_id),
            "agent_name": None,
            "agent_id": None,
            "user_id": None,
            "mime_type": mime_type,
            "gcs_uri": gcs_uri,
            "filename": filename,
            "size_bytes": int(len(content)),
            "text_extract": None,
            "description": title or "",
            "created_at": created_at,
            "metadata": None,  # patched below after schema inspection
        }

        # Ensure dataset/table exists and insert row
        dataset_id = f"tnt_{self.tenant_id}"
        # Ensure proper schema using schema manager on the underlying BigQuery client
        ensure_tenant_kb(self.bq.client, str(self.tenant_id))
        row["metadata"] = metadata_value
        # insert
        self.bq.insert_rows_json(
            dataset_id=dataset_id,
            table_id="assets",
            rows=[row],
            job_id=job_id,
            tenant_id=str(self.tenant_id),
        )

        return RepositoryAsset(
            asset_id=asset_id,
            job_id=job_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=int(len(content)),
            gcs_uri=gcs_uri,
            created_at=created_at,
            metadata=meta,
        )

    def generate_signed_url(self, gcs_uri: str, minutes: int = 5) -> str:
        if not gcs_uri.startswith("gs://"):
            raise ValueError("Invalid GCS URI")
        bucket_name, blob_name = gcs_uri[5:].split("/", 1)
        bucket = self.storage.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=minutes), method="GET")
