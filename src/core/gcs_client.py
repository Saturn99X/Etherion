"""
Google Cloud Storage Client for secure file operations.

This module provides a centralized interface for interacting with Google Cloud Storage,
handling authentication, file uploads, and secure URL generation for the Etherion platform.
"""

import logging
import os
import mimetypes
import tempfile
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from google.cloud import storage
from google.oauth2 import service_account
import google.auth
from urllib.parse import quote
from datetime import timedelta

from src.services.pricing.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


_shared_storage_client: Optional[storage.Client] = None


def _get_shared_storage_client() -> storage.Client:
    global _shared_storage_client
    if _shared_storage_client is None:
        # Keep this fast and deterministic in Cloud Run; ADC is already present.
        _shared_storage_client = storage.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    return _shared_storage_client


@dataclass
class TenantGCSObject:
    tenant_id: str
    gcs_uri: str
    bucket_name: str
    object_name: str
    filename: str
    content_type: str
    size_bytes: int
    local_path: str

class GCSClient:
    """
    Google Cloud Storage client for secure file operations.

    Handles authentication, file uploads, downloads, and signed URL generation
    for tenant-specific GCS operations.
    """

    def __init__(self, tenant_id: str, bucket_type: str = "assets"):
        """
        Initialize GCS client for a specific tenant.

        Args:
            tenant_id: The tenant identifier for bucket isolation
            bucket_type: "assets" for AI-generated assets, "media" for human-source media
        """
        if bucket_type not in ("assets", "media"):
            raise ValueError("bucket_type must be 'assets' or 'media'")
        self.tenant_id = tenant_id
        self.bucket_type = bucket_type
        self.client = self._initialize_client()
        self.bucket_name = self._get_tenant_bucket_name()
        # Ensure bucket exists and hardened
        self._ensure_bucket_exists()

    def _initialize_client(self) -> storage.Client:
        """
        Initialize GCS client with appropriate authentication.

        Returns:
            storage.Client: Authenticated GCS client
        """
        try:
            # Try service account key first (for production)
            service_account_path = os.getenv('GCP_SERVICE_ACCOUNT_KEY_PATH')
            if service_account_path and os.path.exists(service_account_path):
                credentials = service_account.Credentials.from_service_account_file(
                    service_account_path
                )
                return storage.Client(credentials=credentials)

            # Fall back to default credentials (for development)
            credentials, project = google.auth.default()
            return storage.Client(credentials=credentials, project=project)

        except Exception as e:
            logger.error(f"Failed to initialize GCS client: {e}")
            raise

    def _get_tenant_bucket_name(self) -> str:
        """
        Get the tenant-specific GCS bucket name.

        Returns:
            str: Tenant-specific bucket name
        """
        # Phase 13 naming: tnt-{tenant_id}-assets (AI-generated) and tnt-{tenant_id}-media (human-source)
        suffix = "assets" if self.bucket_type == "assets" else "media"
        return f"tnt-{self.tenant_id}-{suffix}"

    def upload_file(
        self,
        local_file_path: str,
        gcs_key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        *,
        job_id: Optional[str] = None,
    ) -> str:
        """
        Upload a local file to GCS.

        Args:
            local_file_path: Path to the local file
            gcs_key: Key/path in GCS (e.g., 'traces/job_123/trace.jsonl')
            metadata: Optional metadata to attach to the file

        Returns:
            str: GCS URI of the uploaded file
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_key)
            if content_type:
                blob.content_type = content_type

            # Set metadata if provided
            if metadata:
                blob.metadata = metadata

            # Upload the file
            blob.upload_from_filename(local_file_path)

            if job_id:
                try:
                    import asyncio as _asyncio

                    size_bytes = 0
                    try:
                        size_bytes = int(os.path.getsize(local_file_path))
                    except Exception:
                        size_bytes = 0

                    async def _record() -> None:
                        tracker = CostTracker()
                        await tracker.record_gcs_upload(job_id, bytes_uploaded=size_bytes, tenant_id=str(self.tenant_id))

                    try:
                        loop = _asyncio.get_running_loop()
                        loop.create_task(_record())
                    except RuntimeError:
                        _asyncio.run(_record())
                except Exception:
                    pass

            gcs_uri = f"gs://{self.bucket_name}/{gcs_key}"
            logger.info(f"Successfully uploaded file to {gcs_uri}")

            return gcs_uri

        except Exception as e:
            logger.error(f"Failed to upload file {local_file_path} to GCS: {e}")
            raise

    def download_file(self, gcs_key: str, local_file_path: str, *, job_id: Optional[str] = None) -> None:
        """
        Download a file from GCS to local storage.

        Args:
            gcs_key: Key/path in GCS
            local_file_path: Local path to save the file
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_key)

            blob.download_to_filename(local_file_path)
            logger.info(f"Successfully downloaded file from gs://{self.bucket_name}/{gcs_key}")

            if job_id:
                try:
                    import asyncio as _asyncio

                    size_bytes = 0
                    try:
                        size_bytes = int(getattr(blob, "size", 0) or 0)
                    except Exception:
                        size_bytes = 0

                    async def _record() -> None:
                        tracker = CostTracker()
                        await tracker.record_gcs_download(job_id, bytes_downloaded=size_bytes, tenant_id=str(self.tenant_id))

                    try:
                        loop = _asyncio.get_running_loop()
                        loop.create_task(_record())
                    except RuntimeError:
                        _asyncio.run(_record())
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to download file from GCS: {e}")
            raise

    def stream_file_content(self, gcs_key: str) -> str:
        """
        Stream file content from GCS as a string.

        Args:
            gcs_key: Key/path in GCS

        Returns:
            str: File content as string
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_key)

            content = blob.download_as_text()
            logger.info(f"Successfully streamed content from gs://{self.bucket_name}/{gcs_key}")

            return content

        except Exception as e:
            logger.error(f"Failed to stream file content from GCS: {e}")
            raise

    def generate_signed_url(self, gcs_key: str, expiration_minutes: int = 60) -> str:
        """
        Generate a signed URL for temporary access to a GCS file.

        Args:
            gcs_key: Key/path in GCS
            expiration_minutes: URL expiration time in minutes

        Returns:
            str: Signed URL for temporary access
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_key)

            # Generate signed URL
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method='GET'
            )

            logger.info(f"Generated signed URL for gs://{self.bucket_name}/{gcs_key}")
            return signed_url

        except Exception as e:
            logger.error(f"Failed to generate signed URL for GCS file: {e}")
            raise

    def delete_file(self, gcs_key: str) -> None:
        """
        Delete a file from GCS.

        Args:
            gcs_key: Key/path in GCS
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_key)

            blob.delete()
            logger.info(f"Successfully deleted file gs://{self.bucket_name}/{gcs_key}")

        except Exception as e:
            logger.error(f"Failed to delete file from GCS: {e}")
            raise

    def file_exists(self, gcs_key: str) -> bool:
        """
        Check if a file exists in GCS.

        Args:
            gcs_key: Key/path in GCS

        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_key)

            return blob.exists()

        except Exception as e:
            logger.error(f"Failed to check file existence in GCS: {e}")
            return False

    def get_file_metadata(self, gcs_key: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a GCS file.

        Args:
            gcs_key: Key/path in GCS

        Returns:
            Optional[Dict[str, Any]]: File metadata or None if not found
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_key)

            if not blob.exists():
                return None

            return {
                'size': blob.size,
                'created': blob.time_created,
                'updated': blob.updated,
                'content_type': blob.content_type,
                'metadata': blob.metadata or {}
            }

        except Exception as e:
            logger.error(f"Failed to get file metadata from GCS: {e}")
            return None

    def _ensure_bucket_exists(self) -> None:
        """
        Ensure tenant bucket exists with hardened configuration:
        - Uniform bucket-level access (no object ACLs)
        - Public Access Prevention enforced
        - Optional lifecycle deletion policy via GCS_RETENTION_DAYS
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            if not bucket.exists():
                bucket = self.client.create_bucket(self.bucket_name, location=os.getenv('GCS_LOCATION', 'us-central1'))
                logger.info(f"Created bucket {self.bucket_name}")

            # Harden bucket
            if not getattr(bucket.iam_configuration, 'uniform_bucket_level_access_enabled', False):
                bucket.iam_configuration.uniform_bucket_level_access_enabled = True
                bucket.patch()

            # Enforce Public Access Prevention (if available in library)
            try:
                bucket.iam_configuration.public_access_prevention = 'enforced'
                bucket.patch()
            except Exception:
                # Older client/library may not expose PAP; ignore
                pass

            # Optional lifecycle
            retention_days = int(os.getenv('GCS_RETENTION_DAYS', '7') or '7')
            if retention_days > 0:
                rule = {
                    'action': {'type': 'Delete'},
                    'condition': {'age': retention_days}
                }
                # Assign lifecycle rules only if different
                if bucket.lifecycle_rules != [rule]:
                    bucket.lifecycle_rules = [rule]
                    bucket.patch()
        except Exception as e:
            logger.warning(f"Bucket ensure/hardening failed for {self.bucket_name}: {e}")


def _parse_gcs_uri(gcs_uri: str) -> Tuple[str, str]:
    if not gcs_uri.startswith("gs://"):
        raise ValueError("Invalid GCS URI")
    rest = gcs_uri[len("gs://") :]
    if "/" not in rest:
        raise ValueError("Invalid GCS URI")
    bucket_name, object_name = rest.split("/", 1)
    if not bucket_name or not object_name:
        raise ValueError("Invalid GCS URI")
    return bucket_name, object_name


def _expected_tenant_bucket_name(*, tenant_id: str, bucket_suffix: str) -> str:
    bucket_prefix = os.getenv("GCS_BUCKET_PREFIX", "tnt")
    return f"{bucket_prefix}-{tenant_id}-{bucket_suffix}"


def fetch_tenant_object_to_tempfile(
    *,
    tenant_id: str,
    gcs_uri: str,
    max_size_bytes: int,
    bucket_suffix: str = "media",
    project_id: Optional[str] = None,
) -> TenantGCSObject:
    if max_size_bytes <= 0:
        raise ValueError("max_size_bytes must be > 0")

    bucket_name, object_name = _parse_gcs_uri(gcs_uri)
    expected_bucket = _expected_tenant_bucket_name(tenant_id=tenant_id, bucket_suffix=bucket_suffix)
    if bucket_name != expected_bucket:
        raise ValueError("GCS URI does not match tenant bucket")

    client_project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not client_project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required")
    client = storage.Client(project=client_project)

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.reload()
    size_bytes = int(getattr(blob, "size", 0) or 0)
    if size_bytes and size_bytes > max_size_bytes:
        raise ValueError("Object exceeds max_size_bytes")

    content_type = (getattr(blob, "content_type", None) or "").strip()
    filename = os.path.basename(object_name)
    if not content_type:
        guessed, _ = mimetypes.guess_type(filename)
        content_type = guessed or "application/octet-stream"

    fd, local_path = tempfile.mkstemp(prefix="etherion-gcs-", dir="/tmp")
    os.close(fd)
    written = 0
    try:
        with open(local_path, "wb") as out_f:
            with blob.open("rb") as in_f:
                while True:
                    chunk = in_f.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_size_bytes:
                        raise ValueError("Object exceeds max_size_bytes")
                    out_f.write(chunk)
        return TenantGCSObject(
            tenant_id=str(tenant_id),
            gcs_uri=gcs_uri,
            bucket_name=bucket_name,
            object_name=object_name,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes or written,
            local_path=local_path,
        )
    except Exception:
        try:
            os.unlink(local_path)
        except Exception:
            pass
        raise


def download_blob_to_bytes(
    gcs_uri: str,
    timeout: int = 30,
    max_retries: int = 3,
    *,
    job_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> bytes:
    """
    Download a GCS blob directly to bytes given a gs:// URI.
    
    Includes robust retry logic with fresh client connections to handle
    transient SSL/network errors in Cloud Run.
    
    Args:
        gcs_uri: Full GCS URI like gs://bucket-name/path/to/file
        timeout: Download timeout in seconds per attempt
        max_retries: Maximum number of retry attempts
        
    Returns:
        bytes: File content as bytes
    """
    import time as _time
    
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    
    uri_parts = gcs_uri.replace("gs://", "").split("/", 1)
    if len(uri_parts) != 2:
        raise ValueError(f"Invalid GCS URI format: {gcs_uri}")
    
    bucket_name, blob_path = uri_parts
    
    last_error = None
    for attempt in range(max_retries):
        try:
            _t0 = _time.time()
            # Use a shared client to avoid repeated ADC + TLS setup costs.
            client = _get_shared_storage_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            # Disable google retry logic so total wall time is bounded by our loop.
            content = blob.download_as_bytes(timeout=timeout, retry=None)
            logger.info(f"Downloaded {len(content)} bytes from {gcs_uri} in {(_time.time() - _t0)*1000:.0f}ms (attempt {attempt+1})")

            if job_id:
                try:
                    import asyncio as _asyncio

                    async def _record() -> None:
                        tracker = CostTracker()
                        await tracker.record_gcs_download(job_id, bytes_downloaded=len(content), tenant_id=tenant_id)

                    try:
                        loop = _asyncio.get_running_loop()
                        loop.create_task(_record())
                    except RuntimeError:
                        _asyncio.run(_record())
                except Exception:
                    pass

            return content
        except Exception as e:
            last_error = e
            logger.warning(f"GCS download attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                # Exponential backoff: 1s, 2s, 4s
                backoff = 2 ** attempt
                logger.info(f"Retrying in {backoff}s...")
                _time.sleep(backoff)
    
    logger.error(f"Failed to download from {gcs_uri} after {max_retries} attempts: {last_error}")
    raise last_error
