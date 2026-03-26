"""Local filesystem storage backend (development only)."""
from __future__ import annotations

import os
import shutil
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional

from .storage_backend import StorageBackend


class LocalStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self.root = Path(os.getenv("STORAGE_LOCAL_ROOT", "/tmp/etherion-storage"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, bucket: str, key: str) -> Path:
        p = self.root / bucket / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def upload(self, bucket: str, key: str, data: BinaryIO, content_type: str = "application/octet-stream") -> str:
        dest = self._path(bucket, key)
        content = data.read() if hasattr(data, "read") else data
        dest.write_bytes(content)
        return f"file://{dest}"

    def download(self, bucket: str, key: str) -> bytes:
        return self._path(bucket, key).read_bytes()

    def delete(self, bucket: str, key: str) -> None:
        p = self._path(bucket, key)
        if p.exists():
            p.unlink()

    def exists(self, bucket: str, key: str) -> bool:
        return self._path(bucket, key).exists()

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        bucket_dir = self.root / bucket
        if not bucket_dir.exists():
            return []
        keys = []
        for p in bucket_dir.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(bucket_dir))
                if rel.startswith(prefix):
                    keys.append(rel)
        return keys

    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        return f"file://{self._path(bucket, key)}"

    def health_check(self) -> bool:
        return self.root.is_dir()
