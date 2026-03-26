"""
BigQuery schema definitions for Phase 13.

Defines core table schemas and helpers for per-tenant datasets.
"""

from google.cloud import bigquery


def assets_table_schema() -> list:
    return [
        bigquery.SchemaField("asset_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("job_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("tenant_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("agent_name", "STRING"),
        bigquery.SchemaField("agent_id", "STRING"),
        bigquery.SchemaField("user_id", "STRING"),
        bigquery.SchemaField("mime_type", "STRING"),
        bigquery.SchemaField("gcs_uri", "STRING"),
        bigquery.SchemaField("filename", "STRING"),
        bigquery.SchemaField("size_bytes", "INT64"),
        bigquery.SchemaField("text_extract", "STRING"),
        bigquery.SchemaField("description", "STRING"),
        bigquery.SchemaField("vector_embedding", "FLOAT64", mode="REPEATED"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("created_by", "STRING"),
        bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
        bigquery.SchemaField("metadata", "JSON"),
    ]


def ensure_assets_table(bq, project_id: str, tenant_id: str) -> None:
    from src.services.bigquery_service import BigQueryService

    svc = BigQueryService(project_id)
    dataset_id = f"tnt_{tenant_id}"
    table_id = "assets"
    svc.ensure_table(
        dataset_id=dataset_id,
        table_id=table_id,
        schema=assets_table_schema(),
        partition_field="created_at",
        cluster_fields=["tenant_id", "agent_id"],
    )


