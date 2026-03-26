from __future__ import annotations

from typing import List, Any
import os
import re


def _client_for_project(client: Any, project: str) -> Any:
    """Return a BigQuery client aligned to the given project using the same credentials.

    WHY: Some environments have ADC default project/quotas that can bleed into API paths
    even when dataset references specify a different project. By ensuring both the client
    and resource references use the same explicit project, we avoid calls to the wrong
    project (e.g., 'natural-content-agent').
    """
    from google.cloud import bigquery
    try:
        if not isinstance(client, bigquery.Client):
            return client
        if getattr(client, "project", None) == project:
            return client
        creds = getattr(client, "_credentials", None)
        return bigquery.Client(project=project, credentials=creds)
    except Exception:
        # Fallback to creating a client with just the project; ADC will supply creds
        return bigquery.Client(project=project)


def _grant_dataset_iam(client: Any, dataset: Any, project: str) -> None:
    """Grant dataEditor role on dataset to API and Worker service accounts.
    
    WHY: Dynamically created tenant datasets must grant IAM at creation time.
    Terraform only handles pre-existing datasets. Without this, worker gets 403
    when trying to create tables.
    """
    from google.cloud import bigquery
    
    # Service accounts that need dataEditor on tenant datasets
    service_accounts = [
        os.getenv("WORKER_SERVICE_ACCOUNT", "prod-worker-agents-svc@fabled-decker-476913-v9.iam.gserviceaccount.com"),
        os.getenv("API_SERVICE_ACCOUNT", "fabled-decker-476913-v9-api-service@fabled-decker-476913-v9.iam.gserviceaccount.com"),
    ]
    
    try:
        # Get current IAM policy
        policy = client.get_iam_policy(dataset)
        
        # Add dataEditor binding for each service account
        role = "roles/bigquery.dataEditor"
        existing_members = set()
        for binding in policy.bindings:
            if binding.get("role") == role:
                existing_members = set(binding.get("members", []))
                break
        
        new_members = set()
        for sa in service_accounts:
            if sa:
                member = f"serviceAccount:{sa}"
                if member not in existing_members:
                    new_members.add(member)
        
        if new_members:
            # Add new binding or update existing
            found = False
            for binding in policy.bindings:
                if binding.get("role") == role:
                    binding["members"] = list(existing_members | new_members)
                    found = True
                    break
            if not found:
                policy.bindings.append({
                    "role": role,
                    "members": list(new_members)
                })
            
            client.set_iam_policy(dataset, policy)
    except Exception as e:
        # Log but don't fail - dataset is created, IAM is best-effort
        import logging
        logging.warning(f"Failed to set dataset IAM for {dataset.dataset_id}: {e}")


def ensure_tenant_dataset(client: Any, tenant_id: str, location: str = "US") -> Any:
    from google.cloud import bigquery
    # Prefer explicit project from env to avoid unintended defaults from ADC
    project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GCLOUD_PROJECT")
        or client.project
    )
    dataset_id = f"tnt_{tenant_id}"
    # Build an explicit DatasetReference to ensure project id is embedded in the API request
    ds_ref = bigquery.DatasetReference(project=project, dataset_id=dataset_id)
    aligned = _client_for_project(client, project)
    try:
        return aligned.get_dataset(ds_ref)
    except Exception:
        dataset = bigquery.Dataset(ds_ref)
        dataset.location = location
        created = aligned.create_dataset(dataset)
        # Grant IAM permissions to service accounts
        _grant_dataset_iam(aligned, created, project)
        return created


def docs_schema() -> List[Any]:
    from google.cloud import bigquery
    return [
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("tenant_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("project_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("chunk_hash", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("text_chunk", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("vector_embedding", "FLOAT64", mode="REPEATED"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
        bigquery.SchemaField("file_uri", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    ]


def assets_schema() -> List[Any]:
    from google.cloud import bigquery
    return [
        bigquery.SchemaField("asset_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("job_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("tenant_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("agent_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("agent_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("user_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("mime_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("gcs_uri", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("filename", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("size_bytes", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("text_extract", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("vector_embedding", "FLOAT64", mode="REPEATED"),
        bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
    ]


def feedback_schema() -> List[Any]:
    from google.cloud import bigquery
    return [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("tenant_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("user_id", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("job_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("score", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("goal_text", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("final_output_text", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("comment_text", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
    ]


def multimodal_docs_schema() -> List[Any]:
    """Schema for human KB - ALL human-uploaded content (any file type).
    
    Design principles:
    - One row = one GCS file (documents, images, videos, etc.)
    - NO TEXT in BigQuery (only metadata, refs, embeddings)
    - Images extracted from docs = separate GCS files = separate rows
    - 1408-D embeddings from multimodalembedding@001
    """
    from google.cloud import bigquery
    return [
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("tenant_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("project_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("gcs_uri", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("filename", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("part_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("part_number", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("total_parts", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("mime_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("size_bytes", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("source_doc_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("chapter_count", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("vector_embedding", "FLOAT64", mode="REPEATED"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    ]


def ensure_table(client: Any, dataset_id: str, table_id: str, schema: List[Any]) -> Any:
    from google.cloud import bigquery
    # Prefer explicit project from env to avoid unintended defaults from ADC
    project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GCLOUD_PROJECT")
        or client.project
    )
    table_ref = f"{project}.{dataset_id}.{table_id}"
    aligned = _client_for_project(client, project)
    try:
        table = aligned.get_table(table_ref)
        try:
            existing_names = {getattr(f, "name", None) for f in (table.schema or [])}
            desired_fields = [f for f in schema if getattr(f, "name", None) not in existing_names]
            if desired_fields:
                table.schema = list(table.schema or []) + desired_fields
                table = aligned.update_table(table, ["schema"])
        except Exception:
            pass

        return table
    except Exception:
        table = bigquery.Table(table_ref, schema=schema)
        # Partition docs by created_at if present
        if any(f.name == "created_at" for f in schema):
            table.time_partitioning = bigquery.TimePartitioning(field="created_at")
        # Cluster by tenant + project for pruning
        cluster_fields = [f for f in ["tenant_id", "project_id"] if any(sf.name == f for sf in schema)]
        if cluster_fields:
            table.clustering_fields = cluster_fields
        return aligned.create_table(table)


def media_object_embeddings_schema() -> List[Any]:
    from google.cloud import bigquery
    return [
        bigquery.SchemaField("tenant_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("gcs_uri", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("content_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("size_bytes", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
        bigquery.SchemaField("vector_embedding", "FLOAT64", mode="REPEATED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ]


def _format_object_table_connection() -> str:
    raw = (os.getenv("BIGQUERY_OBJECT_TABLE_CONNECTION") or "").strip()
    if not raw or raw.upper() == "DEFAULT":
        return "DEFAULT"
    if not re.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$", raw):
        raise ValueError("BIGQUERY_OBJECT_TABLE_CONNECTION must be 'DEFAULT' or 'project.location.connection_id'")
    return f"`{raw}`"


def _tenant_media_object_table_uri_pattern(*, tenant_id: str) -> str:
    from src.core.gcs_client import _expected_tenant_bucket_name

    bucket = _expected_tenant_bucket_name(tenant_id=str(tenant_id), bucket_suffix="media")
    return f"gs://{bucket}/uploads/*"


def _ensure_tenant_media_object_vector_index(*, client: Any, project: str, dataset_id: str) -> None:
    table_ref = f"{project}.{dataset_id}.media_object_embeddings"
    ddl_timeout_s = float(os.getenv("BIGQUERY_DDL_TIMEOUT_SECONDS", "30") or "30")
    ddl = f"""
    CREATE VECTOR INDEX IF NOT EXISTS idx_media_object_embeddings_vec
    ON `{table_ref}` (vector_embedding)
    OPTIONS(distance_type='COSINE')
    """
    try:
        client.query(ddl).result(timeout=ddl_timeout_s)
    except Exception:
        pass


def ensure_tenant_media_object_kb(client: Any, tenant_id: str) -> None:
    dataset = ensure_tenant_dataset(client, str(tenant_id))
    dataset_id = dataset.dataset_id

    # Prefer explicit project from env to avoid unintended defaults from ADC
    project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GCLOUD_PROJECT")
        or client.project
    )
    aligned = _client_for_project(client, project)
    ddl_timeout_s = float(os.getenv("BIGQUERY_DDL_TIMEOUT_SECONDS", "30") or "30")

    object_table_ref = f"{project}.{dataset_id}.media_object_table"
    try:
        aligned.get_table(object_table_ref)
    except Exception:
        uri_pattern = _tenant_media_object_table_uri_pattern(tenant_id=str(tenant_id))
        conn = _format_object_table_connection()
        ddl = f"""
        CREATE EXTERNAL TABLE `{object_table_ref}`
        WITH CONNECTION {conn}
        OPTIONS(
          object_metadata = 'SIMPLE',
          uris = ['{uri_pattern}']
        )
        """
        aligned.query(ddl).result(timeout=ddl_timeout_s)

    ensure_table(aligned, dataset_id, "media_object_embeddings", media_object_embeddings_schema())

    create_index = os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX", "true").lower() == "true"
    if create_index:
        _ensure_tenant_media_object_vector_index(client=aligned, project=project, dataset_id=dataset_id)


def ai_assets_object_embeddings_schema() -> List[Any]:
    from google.cloud import bigquery
    return [
        bigquery.SchemaField("tenant_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("job_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("gcs_uri", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("content_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("size_bytes", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
        bigquery.SchemaField("vector_embedding", "FLOAT64", mode="REPEATED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ]


def _tenant_ai_assets_object_table_uri_pattern(*, tenant_id: str) -> str:
    from src.core.gcs_client import _expected_tenant_bucket_name

    bucket = _expected_tenant_bucket_name(tenant_id=str(tenant_id), bucket_suffix="assets")
    return f"gs://{bucket}/ai/*"


def ensure_tenant_ai_assets_object_kb(client: Any, tenant_id: str) -> None:
    dataset = ensure_tenant_dataset(client, str(tenant_id))
    dataset_id = dataset.dataset_id

    project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GCLOUD_PROJECT")
        or client.project
    )
    aligned = _client_for_project(client, project)
    ddl_timeout_s = float(os.getenv("BIGQUERY_DDL_TIMEOUT_SECONDS", "30") or "30")

    object_table_ref = f"{project}.{dataset_id}.ai_assets_object_table"
    try:
        aligned.get_table(object_table_ref)
    except Exception:
        uri_pattern = _tenant_ai_assets_object_table_uri_pattern(tenant_id=str(tenant_id))
        conn = _format_object_table_connection()
        ddl = f"""
        CREATE EXTERNAL TABLE `{object_table_ref}`
        WITH CONNECTION {conn}
        OPTIONS(
          object_metadata = 'SIMPLE',
          uris = ['{uri_pattern}']
        )
        """
        aligned.query(ddl).result(timeout=ddl_timeout_s)

    ensure_table(aligned, dataset_id, "ai_assets_object_embeddings", ai_assets_object_embeddings_schema())

    create_model_and_index = os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX", "true").lower() == "true"
    if create_model_and_index:
        table_ref = f"{project}.{dataset_id}.ai_assets_object_embeddings"
        ddl_timeout_s = float(os.getenv("BIGQUERY_DDL_TIMEOUT_SECONDS", "30") or "30")
        ddl = f"""
        CREATE VECTOR INDEX IF NOT EXISTS idx_ai_assets_object_embeddings_vec
        ON `{table_ref}` (vector_embedding)
        OPTIONS(distance_type='COSINE')
        """
        try:
            aligned.query(ddl).result(timeout=ddl_timeout_s)
        except Exception:
            pass


def ensure_tenant_kb(client: Any, tenant_id: str) -> None:
    dataset = ensure_tenant_dataset(client, str(tenant_id))
    ensure_table(client, dataset.dataset_id, "docs", docs_schema())
    ensure_table(client, dataset.dataset_id, "assets", assets_schema())
    # Automatically bootstrap object tables if enabled
    if os.getenv("KB_OBJECT_TABLES_ENABLED", "false").lower() == "true":
        try:
            prev = os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX")
            os.environ["KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX"] = "false"
            try:
                ensure_tenant_media_object_kb(client, str(tenant_id))
                ensure_tenant_ai_assets_object_kb(client, str(tenant_id))
            finally:
                if prev is None:
                    os.environ.pop("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX", None)
                else:
                    os.environ["KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX"] = prev
        except Exception:
            pass
    # Bootstrap multimodal KB tables if enabled (defaulting to true for multimodal-first)
    if os.getenv("KB_MULTIMODAL_ENABLED", "true").lower() == "true":
        try:
            ensure_tenant_multimodal_kb(client, str(tenant_id))
        except Exception:
            pass


def ensure_tenant_multimodal_kb(client: Any, tenant_id: str) -> None:
    """Ensure multimodal KB table exists for tenant (1408-D embeddings).
    
    Creates:
    - multimodal_docs: ONE table for ALL human-uploaded files (docs, images, videos, etc.)
    - Each row = one GCS file
    - Images extracted from PDFs = separate GCS files = separate rows linked via source_doc_id
    - Optional: vector index for VECTOR_SEARCH
    """
    dataset = ensure_tenant_dataset(client, str(tenant_id))
    dataset_id = dataset.dataset_id

    project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GCLOUD_PROJECT")
        or client.project
    )
    aligned = _client_for_project(client, project)

    # Create multimodal_docs table (single table for ALL content)
    ensure_table(aligned, dataset_id, "multimodal_docs", multimodal_docs_schema())

    # Create vector index if enabled
    create_index = os.getenv("KB_MULTIMODAL_CREATE_INDEX", "true").lower() == "true"
    if create_index:
        ddl_timeout_s = float(os.getenv("BIGQUERY_DDL_TIMEOUT_SECONDS", "30") or "30")
        docs_table_ref = f"{project}.{dataset_id}.multimodal_docs"
        ddl_docs = f"""
        CREATE VECTOR INDEX IF NOT EXISTS idx_multimodal_docs_vec
        ON `{docs_table_ref}` (vector_embedding)
        OPTIONS(distance_type='COSINE')
        """
        try:
            aligned.query(ddl_docs).result(timeout=ddl_timeout_s)
        except Exception:
            pass


def ensure_tenant_feedback(client: Any, tenant_id: str) -> None:
    dataset = ensure_tenant_dataset(client, str(tenant_id))
    ensure_table(client, dataset.dataset_id, "feedback", feedback_schema())
