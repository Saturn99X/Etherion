"""
Base class for all file generation tools.

Provides common functionality for:
- MinIO/local storage integration via StorageBackend
- PostgreSQL + pgvector metadata indexing
- Signed URL generation via backend
- Base64 encoding for small files
"""

import os
import uuid
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from io import BytesIO
import base64

from src.core.storage_backend import get_storage_backend

import logging

logger = logging.getLogger(__name__)


class BaseFileGenerator:
    """
    Base class for all file generation tools.

    Handles the complete lifecycle:
    1. File generation (implemented by subclasses)
    2. Storage in MinIO/local via StorageBackend
    3. Metadata indexing in PostgreSQL
    4. Access URL generation (signed or base64)
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
            project_id: Unused, kept for backward compatibility
        """
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.job_id = job_id
        self.user_id = user_id

        self.storage = get_storage_backend()
        self.bucket_name = f"tnt-{tenant_id}-assets"

        logger.info(
            f"Initialized BaseFileGenerator for tenant={tenant_id}, "
            f"agent={agent_id}, job={job_id}"
        )

    def _ensure_bucket_exists(self) -> None:
        """Ensure the storage bucket exists."""
        if not self.storage.exists(self.bucket_name, ".keep"):
            from io import BytesIO
            self.storage.upload(self.bucket_name, ".keep", BytesIO(b""))
            logger.info(f"Created bucket {self.bucket_name}")

    async def save_to_storage(
        self, file_bytes: bytes, filename: str, mime_type: str
    ) -> str:
        """
        Save file bytes to storage.

        Args:
            file_bytes: The file content as bytes
            filename: The filename to use
            mime_type: The MIME type of the file

        Returns:
            The storage URI of the saved file
        """
        self._ensure_bucket_exists()

        # Create key path: {agent_id}/{job_id}/{filename}
        key = f"{self.agent_id}/{self.job_id}/{filename}"
        self.storage.upload(self.bucket_name, key, BytesIO(file_bytes), content_type=mime_type)

        storage_uri = f"s3://{self.bucket_name}/{key}"
        logger.info(f"Saved file to {storage_uri}")

        return storage_uri

    async def index_in_db(
        self,
        asset_id: str,
        storage_uri: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        text_extract: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Index the asset in PostgreSQL for searchability.

        Args:
            asset_id: Unique identifier for the asset
            storage_uri: The storage URI where the file is stored
            filename: The filename
            mime_type: The MIME type
            size_bytes: File size in bytes
            text_extract: Optional extracted text for search
            description: Optional description
            tags: Optional list of tags
            metadata: Optional additional metadata as JSON
        """
        from src.database.db import get_db
        from sqlalchemy import text

        merged_metadata: Dict[str, Any] = {**(metadata or {})}
        merged_metadata["origin"] = "ai"

        db = get_db()
        try:
            db.execute(
                text("""
                    INSERT INTO kb_assets
                        (asset_id, job_id, tenant_id, agent_name, agent_id, user_id,
                         mime_type, storage_uri, filename, size_bytes,
                         text_extract, description, metadata, created_at)
                    VALUES
                        (:asset_id, :job_id, :tenant_id, :agent_name, :agent_id, :user_id,
                         :mime_type, :storage_uri, :filename, :size_bytes,
                         :text_extract, :description, :metadata, :created_at)
                """),
                {
                    "asset_id": asset_id,
                    "job_id": self.job_id,
                    "tenant_id": self.tenant_id,
                    "agent_name": f"agent_{self.agent_id}",
                    "agent_id": self.agent_id,
                    "user_id": self.user_id or "",
                    "mime_type": mime_type,
                    "storage_uri": storage_uri,
                    "filename": filename,
                    "size_bytes": size_bytes,
                    "text_extract": text_extract or "",
                    "description": description or "",
                    "metadata": json.dumps(merged_metadata) if merged_metadata else "{}",
                    "created_at": datetime.utcnow(),
                },
            )
            db.commit()
            logger.info(f"Indexed asset {asset_id} in database")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to index asset {asset_id}: {e}")
            raise
        finally:
            db.close()

    def get_url(self, storage_uri: str, expiration_minutes: int = 5) -> str:
        """
        Generate a signed URL for temporary access to the file.

        Args:
            storage_uri: The storage URI of the file
            expiration_minutes: URL expiration time in minutes (default: 5)

        Returns:
            A signed URL that expires after the specified time
        """
        if storage_uri.startswith("s3://"):
            path = storage_uri[5:]
        else:
            path = storage_uri

        parts = path.split("/", 1)
        bucket_name = parts[0]
        key = parts[1] if len(parts) > 1 else ""

        url = self.storage.get_url(bucket_name, key, expiry_seconds=expiration_minutes * 60)

        logger.info(
            f"Generated URL for {storage_uri} (expires in {expiration_minutes} min)"
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
        Complete flow: Save to Storage → Index in DB → Return access info.

        Args:
            file_bytes: The file content as bytes
            filename: The filename
            mime_type: The MIME type
            description: Optional description
            tags: Optional tags for categorization
            metadata: Optional additional metadata

        Returns:
            Dictionary with asset_id, storage_uri, download_url, and optional preview_base64
        """
        asset_id = str(uuid.uuid4())

        storage_uri = await self.save_to_storage(file_bytes, filename, mime_type)

        await self.index_in_db(
            asset_id=asset_id,
            storage_uri=storage_uri,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
            description=description,
            tags=tags,
            metadata=metadata,
        )

        download_url = self.get_url(storage_uri, expiration_minutes=5)

        preview_base64 = None
        if len(file_bytes) < 5 * 1024 * 1024:
            preview_base64 = self.to_base64(file_bytes, mime_type)

        result = {
            "asset_id": asset_id,
            "storage_uri": storage_uri,
            "filename": filename,
            "download_url": download_url,
            "preview_base64": preview_base64,
            "size_bytes": len(file_bytes),
            "mime_type": mime_type,
        }

        logger.info(f"Successfully saved asset {asset_id}: {filename}")

        return result
