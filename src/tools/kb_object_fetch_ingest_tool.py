from __future__ import annotations

import os
from typing import Any, Dict, Optional

from langchain_core.tools import tool

from src.config.environment import EnvironmentConfig
from src.core.gcs_client import fetch_tenant_object_to_tempfile
from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService
from src.services.multimodal_ingestion_service import MultimodalIngestionService


@tool
async def kb_object_fetch_ingest(
    tenant_id: str,
    gcs_uri: str,
    project_id: Optional[str] = None,
    job_id: Optional[str] = None,
    max_size_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch a tenant-scoped gs:// object and ingest it through the KB ingestion pipeline."""

    tenant_id = str(tenant_id or "").strip()
    gcs_uri = str(gcs_uri or "").strip()

    if not tenant_id:
        raise ValueError("kb_object_fetch_ingest requires 'tenant_id'.")
    if not gcs_uri:
        raise ValueError("kb_object_fetch_ingest requires 'gcs_uri'.")

    cfg = EnvironmentConfig()
    if not bool(cfg.get("kb_direct_gcs_fetch_enabled", False)):
        raise RuntimeError("kb_direct_gcs_fetch_enabled is false")

    default_max = int(os.getenv("KB_OBJECT_FETCH_MAX_SIZE_BYTES", str(10 * 1024 * 1024)) or str(10 * 1024 * 1024))
    max_size_bytes = int(max_size_bytes or default_max)
    if max_size_bytes <= 0:
        raise ValueError("max_size_bytes must be > 0")

    obj = fetch_tenant_object_to_tempfile(
        tenant_id=tenant_id,
        gcs_uri=gcs_uri,
        max_size_bytes=max_size_bytes,
        bucket_suffix="media",
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT"),
    )

    try:
        with open(obj.local_path, "rb") as f:
            content = f.read()
    finally:
        try:
            os.unlink(obj.local_path)
        except Exception:
            pass

    svc = MultimodalIngestionService(project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
    result = svc.ingest_gcs_uri(
        tenant_id=str(tenant_id),
        gcs_uri=str(obj.gcs_uri),
        filename=str(obj.filename),
        mime_type=str(obj.content_type),
        project_id=str(project_id) if project_id else None,
        job_id=job_id,
    )

    # Best-effort: ensure the per-object embeddings row exists/updates for this object.
    # This keeps the object-KB semantic layer consistent with new uploads and updates.
    try:
        if bool(cfg.get("kb_object_tables_enabled", False)):
            backfill = BQMediaObjectEmbeddingsBackfillService(project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
            backfill.backfill(tenant_id=str(tenant_id), gcs_uri=str(result.gcs_uri), job_id=job_id)
    except Exception:
        pass

    return {
        "provider": "object_kb_fetch_ingest",
        "tenant_id": result.tenant_id,
        "gcs_uri": result.gcs_uri,
        "filename": result.filename,
        "mime_type": result.mime_type,
        "size_bytes": int(result.size_bytes),
        "doc_ids": result.doc_ids,
        "chapter_count": int(result.chapter_count),
    }
