"""
Base class for all file generation tools.

Provides common functionality for:
- GCS storage integration
- BigQuery metadata indexing
- Vertex AI Search integration
- Signed URL generation
- Base64 encoding for small files
"""

import os
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from io import BytesIO
import base64

import logging

logger = logging.getLogger(__name__)


class BaseFileGenerator:
    """
    Base class for all file generation tools.

    Handles the complete lifecycle:
    1. File generation (implemented by subclasses)
    2. Storage in private GCS bucket
    3. Metadata indexing in BigQuery
    4. Vertex AI Search indexing trigger
    5. Access URL generation (signed or base64)
    """

    def __init__(
        self,
        tenant_id: str,
        agent_id: str,
        job_id: str,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        """
        Initialize the base file generator.

        Args:
            tenant_id: The tenant ID for multi-tenancy isolation
            agent_id: The ID of the agent creating the file
            job_id: The job ID associated with this generation
            user_id: Optional user ID for audit trails
            project_id: GCP project ID (defaults to env var)
        """
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.job_id = job_id
        self.user_id = user_id
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")

        # Initialize GCP clients lazily
        self._storage_client = None
        self._bigquery_client = None

        # Bucket naming convention: tnt-{tenant_id}-assets
        self.bucket_name = f"tnt-{tenant_id}-assets"

        # BigQuery dataset naming: tnt_{tenant_id}
        self.dataset_id = f"tnt_{tenant_id}"
        self.table_id = "assets"

        logger.info(
            f"Initialized BaseFileGenerator for tenant={tenant_id}, "
            f"agent={agent_id}, job={job_id}"
        )

    @property
    def storage_client(self):
        if self._storage_client is None:
            from google.cloud import storage
            self._storage_client = storage.Client(project=self.project_id)
        return self._storage_client

    @property
    def bigquery_client(self):
        if self._bigquery_client is None:
            from google.cloud import bigquery
            self._bigquery_client = bigquery.Client(project=self.project_id)
        return self._bigquery_client

    def _ensure_bucket_exists(self) -> Any:
        """
        Ensure the private GCS bucket exists with proper configuration.

        Returns:
            The GCS bucket object
        """
        from google.cloud.exceptions import NotFound
        try:
            bucket = self.storage_client.get_bucket(self.bucket_name)
            logger.info(f"Bucket {self.bucket_name} already exists")
        except NotFound:
            # Create bucket with uniform bucket-level access (no public access)
            bucket_location = os.getenv("GCS_BUCKET_LOCATION", "us-central1")
            bucket = self.storage_client.create_bucket(
                self.bucket_name, location=bucket_location
            )
            bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            bucket.patch()
            logger.info(f"Created private bucket {self.bucket_name}")

        return bucket

    def _ensure_bigquery_table_exists(self):
        """
        Ensure the BigQuery assets table exists with proper schema.
        """
        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound
        # First ensure dataset exists
        dataset_ref = bigquery.Dataset(f"{self.project_id}.{self.dataset_id}")
        try:
            self.bigquery_client.get_dataset(dataset_ref)
            logger.info(f"Dataset {self.dataset_id} already exists")
        except NotFound:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = os.getenv("BIGQUERY_LOCATION", "us-central1")
            dataset = self.bigquery_client.create_dataset(dataset, timeout=30)
            logger.info(f"Created dataset {self.dataset_id}")

        # Now ensure table exists
        table_ref = dataset_ref.table(self.table_id)

        try:
            self.bigquery_client.get_table(table_ref)
            logger.info(f"Table {self.dataset_id}.{self.table_id} already exists")
        except NotFound:
            # Define schema for assets table
            schema = [
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

            table = bigquery.Table(table_ref, schema=schema)

            # Enable partitioning and clustering for performance
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY, field="created_at"
            )
            table.clustering_fields = ["tenant_id", "agent_id"]

            table = self.bigquery_client.create_table(table)
            logger.info(f"Created table {self.dataset_id}.{self.table_id}")

    async def save_to_gcs(
        self, file_bytes: bytes, filename: str, mime_type: str
    ) -> str:
        """
        Save file bytes to private GCS bucket.

        Args:
            file_bytes: The file content as bytes
            filename: The filename to use
            mime_type: The MIME type of the file

        Returns:
            The gs:// URI of the saved file
        """
        bucket = self._ensure_bucket_exists()

        # Create blob path: {agent_id}/{job_id}/{filename}
        blob_path = f"{self.agent_id}/{self.job_id}/{filename}"
        blob = bucket.blob(blob_path)

        # Upload with proper content type
        blob.upload_from_string(file_bytes, content_type=mime_type)

        gcs_uri = f"gs://{self.bucket_name}/{blob_path}"
        logger.info(f"Saved file to {gcs_uri}")

        return gcs_uri

    async def index_in_bigquery(
        self,
        asset_id: str,
        gcs_uri: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        text_extract: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Index the asset in BigQuery for searchability.

        Args:
            asset_id: Unique identifier for the asset
            gcs_uri: The GCS URI where the file is stored
            filename: The filename
            mime_type: The MIME type
            size_bytes: File size in bytes
            text_extract: Optional extracted text for search
            description: Optional description
            tags: Optional list of tags
            metadata: Optional additional metadata as JSON
        """
        self._ensure_bigquery_table_exists()

        table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"

        # Ensure origin attribution is enforced (AI-only assets)
        merged_metadata: Dict[str, Any] = {**(metadata or {})}
        merged_metadata["origin"] = "ai"

        row = {
            "asset_id": asset_id,
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "agent_name": f"agent_{self.agent_id}",
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "mime_type": mime_type,
            "gcs_uri": gcs_uri,
            "filename": filename,
            "size_bytes": size_bytes,
            "text_extract": text_extract or "",
            "description": description or "",
            "created_at": datetime.utcnow().isoformat(),
            "created_by": self.user_id or self.agent_id,
            "tags": tags or [],
            "metadata": merged_metadata,
        }

        errors = self.bigquery_client.insert_rows_json(table_ref, [row])

        if errors:
            logger.error(f"BigQuery insert errors: {errors}")
            raise Exception(f"Failed to index in BigQuery: {errors}")

        logger.info(f"Indexed asset {asset_id} in BigQuery")

    def generate_signed_url(self, gcs_uri: str, expiration_minutes: int = 5) -> str:
        """
        Generate a signed URL for temporary access to the file.

        Args:
            gcs_uri: The gs:// URI of the file
            expiration_minutes: URL expiration time in minutes (default: 5)

        Returns:
            A signed URL that expires after the specified time
        """
        # Parse gs:// URI
        if not gcs_uri.startswith("gs://"):
            raise ValueError("Invalid GCS URI")

        path_parts = gcs_uri[5:].split("/", 1)
        bucket_name = path_parts[0]
        blob_name = path_parts[1]

        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        url = blob.generate_signed_url(
            version="v4", expiration=timedelta(minutes=expiration_minutes), method="GET"
        )

        logger.info(
            f"Generated signed URL for {gcs_uri} (expires in {expiration_minutes} min)"
        )

        return url

    def to_base64(self, file_bytes: bytes, mime_type: str) -> str:
        """
        Convert file bytes to base64 data URI for inline embedding.

        Args:
            file_bytes: The file content as bytes
            mime_type: The MIME type

        Returns:
            A data URI string
        """
        b64_data = base64.b64encode(file_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{b64_data}"

    async def save_asset(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Complete flow: Save to GCS → Index in BigQuery → Return access info.

        Args:
            file_bytes: The file content as bytes
            filename: The filename
            mime_type: The MIME type
            description: Optional description
            tags: Optional tags for categorization
            metadata: Optional additional metadata

        Returns:
            Dictionary with asset_id, gcs_uri, download_url, and optional preview_base64
        """
        # Generate unique asset ID
        asset_id = str(uuid.uuid4())

        # 1. Save to GCS
        gcs_uri = await self.save_to_gcs(file_bytes, filename, mime_type)

        # 2. Index in BigQuery
        await self.index_in_bigquery(
            asset_id=asset_id,
            gcs_uri=gcs_uri,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
            description=description,
            tags=tags,
            metadata=metadata,
        )

        # 3. Generate access methods
        download_url = self.generate_signed_url(gcs_uri, expiration_minutes=5)

        # For small files (<5MB), also provide base64
        preview_base64 = None
        if len(file_bytes) < 5 * 1024 * 1024:  # 5MB threshold
            preview_base64 = self.to_base64(file_bytes, mime_type)

        result = {
            "asset_id": asset_id,
            "gcs_uri": gcs_uri,
            "filename": filename,
            "download_url": download_url,
            "preview_base64": preview_base64,
            "size_bytes": len(file_bytes),
            "mime_type": mime_type,
        }

        logger.info(f"Successfully saved asset {asset_id}: {filename}")

        return result
