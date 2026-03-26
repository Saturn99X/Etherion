"""Abstract storage backend + factory."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import BinaryIO, Optional


class StorageBackend(ABC):
    @abstractmethod
    def upload(self, bucket: str, key: str, data: BinaryIO, content_type: str = "application/octet-stream") -> str:
        """Upload data and return the object URI."""

    @abstractmethod
    def download(self, bucket: str, key: str) -> bytes:
        """Download and return object bytes."""

    @abstractmethod
    def delete(self, bucket: str, key: str) -> None:
        """Delete an object."""

    @abstractmethod
    def exists(self, bucket: str, key: str) -> bool:
        """Return True if the object exists."""

    @abstractmethod
    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        """List object keys under prefix."""

    @abstractmethod
    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        """Return a (possibly pre-signed) URL for the object."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the backend is reachable."""


def get_storage_backend() -> StorageBackend:
    """Factory — reads STORAGE_BACKEND env var (local | minio | gcs). Default: minio."""
    backend = os.getenv("STORAGE_BACKEND", "minio").lower()
    if backend == "gcs":
        from .storage_backend_gcs import GCSStorageBackend
        return GCSStorageBackend()
    elif backend == "local":
        from .storage_backend_local import LocalStorageBackend
        return LocalStorageBackend()
    else:
        from .storage_backend_minio import MinIOStorageBackend
        return MinIOStorageBackend()
