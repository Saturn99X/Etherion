import os
import time
import logging
from typing import Dict, Any, List, Optional

from google.auth import default
from google.auth.transport.requests import Request
from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials
from google.cloud import bigquery

from src.core.celery import celery_app
from src.core.tenant_tasks import tenant_task
from src.services.bq_schema_manager import docs_schema

logger = logging.getLogger(__name__)


def _project_id() -> str:
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    if not project_id:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required")
    return project_id


def _tenant_sa_email(tenant_id: str) -> str:
    project = _project_id()
    return f"sa-tenant-{tenant_id}@{project}.iam.gserviceaccount.com"


def _assert_impersonation_allowed(sa_email: str) -> None:
    allowed_raw = os.getenv("IMPERSONATION_ALLOWED_SAS", "")
    allowed = {s.strip() for s in allowed_raw.split(",") if s.strip()}
    if allowed and sa_email not in allowed:
        raise PermissionError(f"impersonation_not_allowed:{sa_email}")


def _impersonated_bq_client(tenant_id: str) -> bigquery.Client:
    target_sa = _tenant_sa_email(str(tenant_id))
    _assert_impersonation_allowed(target_sa)

    base_creds, _ = default(scopes=[
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/bigquery",
    ])
    if not base_creds.valid:
        try:
            base_creds.refresh(Request())
        except Exception:
            # allow to proceed; ImpersonatedCredentials will refresh when needed
            pass

    imp_creds = ImpersonatedCredentials(
        source_credentials=base_creds,
        target_principal=target_sa,
        target_scopes=[
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/bigquery",
        ],
        lifetime=3600,
    )

    # Force refresh early to catch IAM issues
    try:
        imp_creds.refresh(Request())
    except Exception as e:
        raise PermissionError(f"impersonation_refresh_failed:{target_sa}:{e}")

    return bigquery.Client(project=_project_id(), credentials=imp_creds)


def _ensure_staging_table(bq: bigquery.Client, tenant_id: str) -> str:
    dataset_id = f"tnt_{tenant_id}_staging"
    table_id = "docs"
    full_dataset = bigquery.Dataset(f"{_project_id()}.{dataset_id}")
    # Create dataset if missing (idempotent)
    try:
        bq.get_dataset(full_dataset.reference)
    except Exception:
        try:
            full_dataset.location = os.getenv("BIGQUERY_LOCATION", "US")
            bq.create_dataset(full_dataset)
        except Exception:
            # Might be created by Terraform but ADC project mismatch; re-fetch
            bq.get_dataset(full_dataset.reference)

    # Ensure docs table exists with schema similar to production
    full_table = f"{_project_id()}.{dataset_id}.{table_id}"
    try:
        bq.get_table(full_table)
    except Exception:
        schema = docs_schema()
        tbl = bigquery.Table(full_table, schema=schema)
        # Partition on created_at if present
        if any(f.name == "created_at" for f in schema):
            tbl.time_partitioning = bigquery.TimePartitioning(field="created_at")
        try:
            bq.create_table(tbl)
        except Exception:
            # Race-safe: attempt to get again
            bq.get_table(full_table)

    return full_table


@tenant_task(bind=True, name="worker.drive_stage_file", autoretry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 60})
def drive_stage_file(self, tenant_id: int, file_id: str, title: Optional[str] = None, mime_type: Optional[str] = None,
                     snippet: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Stage a Drive file metadata record into the tenant staging dataset.

    This task impersonates the per-tenant SA `sa-tenant-{id}` to write rows into
    `tnt_{tenant}_staging.docs` using CMEK and respecting TTL configured at the dataset level.

    Args:
        tenant_id: Tenant numeric ID
        file_id: Google Drive file ID
        title: Optional document title
        mime_type: Optional MIME type
        snippet: Optional short text snippet (first N chars)
        metadata: Optional additional metadata
    """
    try:
        bq = _impersonated_bq_client(str(tenant_id))
        table_ref = _ensure_staging_table(bq, str(tenant_id))

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        row = {
            "doc_id": f"drv_{file_id}",
            "tenant_id": str(tenant_id),
            "project_id": None,
            "chunk_hash": file_id,
            "text_chunk": snippet or (title or ""),
            "vector_embedding": [],
            "metadata": {
                "source": "google_drive",
                "file_id": file_id,
                "title": title,
                "mime_type": mime_type,
                **(metadata or {}),
            },
            "file_uri": f"drive://{file_id}",
            "created_at": now,
            "updated_at": now,
        }
        errors = bq.insert_rows_json(table_ref, [row])
        if errors:
            raise RuntimeError(f"bq_insert_errors:{errors}")

        logger.info("Drive staging row inserted", extra={"tenant_id": tenant_id, "file_id": file_id})
        return {"ok": True, "tenant_id": tenant_id, "table": table_ref, "rows": 1}
    except Exception as e:
        logger.error(f"drive_stage_file failed: {e}")
        raise
