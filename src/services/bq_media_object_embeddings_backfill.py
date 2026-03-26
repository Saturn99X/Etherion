from __future__ import annotations

from typing import Optional, Dict, Any
import os
import json

from src.services.bigquery_service import BigQueryService
from src.services.bq_schema_manager import ensure_tenant_media_object_kb
from src.services.embedding_service import EmbeddingService
from src.core.gcs_client import fetch_tenant_object_to_tempfile


class BQMediaObjectEmbeddingsBackfillService:
    def __init__(self, project_id: Optional[str] = None, bq: Optional[BigQueryService] = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")
        self.bq = bq or BigQueryService(project_id=self.project_id)

    def backfill(
        self,
        *,
        tenant_id: str,
        gcs_uri: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> None:
        try:
            ensure_tenant_media_object_kb(self.bq.client, str(tenant_id))
        except Exception:
            pass

        dataset_id = f"tnt_{tenant_id}"
        embeddings_ref = f"{self.project_id}.{dataset_id}.media_object_embeddings"

        if not gcs_uri:
            raise ValueError("gcs_uri is required for media object embedding backfill")

        max_size = int(os.getenv("KB_OBJECT_FETCH_MAX_SIZE_BYTES", "10000000") or "10000000")
        obj = fetch_tenant_object_to_tempfile(
            tenant_id=str(tenant_id),
            gcs_uri=str(gcs_uri),
            max_size_bytes=max_size,
            bucket_suffix="media",
            project_id=self.project_id,
        )
        try:
            try:
                from google.cloud import storage
                client = storage.Client(project=self.project_id)
                bucket = client.bucket(obj.bucket_name)
                blob = bucket.blob(obj.object_name)
                blob.reload()
                updated_at = getattr(blob, "updated", None)
                metadata = getattr(blob, "metadata", None)
            except Exception:
                updated_at = None
                metadata = None

            metadata_json = ""
            try:
                if isinstance(metadata, dict):
                    metadata_json = json.dumps(metadata)
            except Exception:
                metadata_json = ""

            text_for_embedding = "\n".join(
                [
                    f"filename: {obj.filename}",
                    f"content_type: {obj.content_type}",
                    f"gcs_uri: {gcs_uri}",
                    f"metadata: {metadata_json}",
                ]
            )

            embedder = EmbeddingService(project_id=self.project_id)
            vectors = embedder.embed_texts([text_for_embedding[:10000]], task="RETRIEVAL_DOCUMENT")
            vec = vectors[0] if vectors else [0.0] * int(getattr(embedder, "dimension", 768) or 768)
        finally:
            try:
                os.unlink(obj.local_path)
            except Exception:
                pass

        row = {
            "tenant_id": str(tenant_id),
            "gcs_uri": str(gcs_uri),
            "content_type": obj.content_type,
            "size_bytes": int(obj.size_bytes),
            "updated_at": updated_at,
            "metadata": metadata,
            "vector_embedding": vec,
            "created_at": None,
        }

        updated_at_str = None
        try:
            if row["updated_at"] is not None:
                updated_at_str = str(row["updated_at"])
        except Exception:
            updated_at_str = None

        metadata_json_str = None
        try:
            if isinstance(row["metadata"], dict):
                metadata_json_str = json.dumps(row["metadata"])
            elif isinstance(row["metadata"], str):
                metadata_json_str = row["metadata"]
        except Exception:
            metadata_json_str = None

        merge_sql = f"""
        MERGE `{embeddings_ref}` T
        USING (
          SELECT
            @tenant_id AS tenant_id,
            @gcs_uri AS gcs_uri,
            @content_type AS content_type,
            @size_bytes AS size_bytes,
            TIMESTAMP(@updated_at) AS updated_at,
            PARSE_JSON(COALESCE(@metadata_json, '{{}}')) AS metadata,
            @vector_embedding AS vector_embedding,
            CURRENT_TIMESTAMP() AS created_at
        ) S
        ON T.gcs_uri = S.gcs_uri
        WHEN MATCHED THEN
          UPDATE SET
            tenant_id = S.tenant_id,
            content_type = S.content_type,
            size_bytes = S.size_bytes,
            updated_at = S.updated_at,
            metadata = S.metadata,
            vector_embedding = S.vector_embedding
        WHEN NOT MATCHED THEN
          INSERT (tenant_id, gcs_uri, content_type, size_bytes, updated_at, metadata, vector_embedding, created_at)
          VALUES (S.tenant_id, S.gcs_uri, S.content_type, S.size_bytes, S.updated_at, S.metadata, S.vector_embedding, S.created_at)
        """

        params2: Dict[str, Any] = {
            "tenant_id": row["tenant_id"],
            "gcs_uri": row["gcs_uri"],
            "content_type": row["content_type"],
            "size_bytes": row["size_bytes"],
            "updated_at": updated_at_str,
            "metadata_json": metadata_json_str,
            "vector_embedding": row["vector_embedding"],
        }
        self.bq.query(
            merge_sql,
            params=params2,
            labels={"tenant_id": str(tenant_id), "component": "bq_media_object_embeddings_backfill"},
            job_id=job_id,
        )
