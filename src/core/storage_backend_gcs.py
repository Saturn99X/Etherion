"""GCS storage backend — wraps existing src.core.gcs_client."""
from __future__ import annotations

import os
from datetime import timedelta
from typing import BinaryIO

from .storage_backend import StorageBackend


class GCSStorageBackend(StorageBackend):
    def __init__(self) -> None:
        from google.cloud import storage as gcs
        self._client = gcs.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))

    def _bucket(self, name: str):
        return self._client.bucket(name)

    def upload(self, bucket: str, key: str, data: BinaryIO, content_type: str = "application/octet-stream") -> str:
        blob = self._bucket(bucket).blob(key)
        content = data.read() if hasattr(data, "read") else data
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{bucket}/{key}"

    def download(self, bucket: str, key: str) -> bytes:
        return self._bucket(bucket).blob(key).download_as_bytes()

    def delete(self, bucket: str, key: str) -> None:
        self._bucket(bucket).blob(key).delete()

    def exists(self, bucket: str, key: str) -> bool:
        return self._bucket(bucket).blob(key).exists()

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        blobs = self._client.list_blobs(bucket, prefix=prefix)
        return [b.name for b in blobs]

    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        blob = self._bucket(bucket).blob(key)
        return blob.generate_signed_url(expiration=timedelta(seconds=expiry_seconds), version="v4")

    def health_check(self) -> bool:
        try:
            list(self._client.list_buckets(max_results=1))
            return True
        except Exception:
            return False
