"""MinIO object storage backend."""
from __future__ import annotations

import io
import os
from datetime import timedelta
from typing import BinaryIO

from .storage_backend import StorageBackend


class MinIOStorageBackend(StorageBackend):
    def __init__(self) -> None:
        from minio import Minio

        endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        # Strip http:// or https:// prefix — minio SDK takes host:port
        for scheme in ("https://", "http://"):
            if endpoint.startswith(scheme):
                endpoint = endpoint[len(scheme):]
                break

        secure = os.getenv("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
        self._client = Minio(
            endpoint,
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            region=os.getenv("MINIO_REGION", "us-east-1"),
            secure=secure,
        )

    def _ensure_bucket(self, bucket: str) -> None:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def upload(self, bucket: str, key: str, data: BinaryIO, content_type: str = "application/octet-stream") -> str:
        self._ensure_bucket(bucket)
        content = data.read() if hasattr(data, "read") else data
        self._client.put_object(bucket, key, io.BytesIO(content), len(content), content_type=content_type)
        endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        return f"s3://{bucket}/{key}"

    def download(self, bucket: str, key: str) -> bytes:
        response = self._client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, bucket: str, key: str) -> None:
        self._client.remove_object(bucket, key)

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self._client.stat_object(bucket, key)
            return True
        except Exception:
            return False

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        try:
            objects = self._client.list_objects(bucket, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except Exception:
            return []

    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        return self._client.presigned_get_object(bucket, key, expires=timedelta(seconds=expiry_seconds))

    def health_check(self) -> bool:
        try:
            self._client.list_buckets()
            return True
        except Exception:
            return False
