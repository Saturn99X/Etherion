"""PostgreSQL storage backend — stores file content as bytea in kb_asset_content."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import BytesIO
from typing import BinaryIO, Optional
from uuid import uuid4

from .storage_backend import StorageBackend


class PGStorageBackend(StorageBackend):
    """Stores file bytes in PostgreSQL kb_asset_content table.

    The table has: asset_id UUID PK, bucket VARCHAR, key VARCHAR,
    content BYTEA, content_type VARCHAR, created_at TIMESTAMPTZ.
    """

    def __init__(self) -> None:
        from src.database.db import get_db
        self._get_db = get_db

    def _store(self, bucket: str, key: str, content: bytes, content_type: str) -> str:
        asset_id = str(uuid4())
        from sqlalchemy import text
        db = self._get_db()
        try:
            db.execute(
                text("""
                    INSERT INTO kb_asset_content
                        (asset_id, bucket, key, content, content_type, created_at)
                    VALUES (:aid, :b, :k, :c, :ct, :ca)
                """),
                {
                    "aid": asset_id, "b": bucket, "k": key,
                    "c": content, "ct": content_type,
                    "ca": datetime.utcnow(),
                },
            )
            db.commit()
        finally:
            db.close()
        return asset_id

    def upload(self, bucket: str, key: str, data: BinaryIO,
               content_type: str = "application/octet-stream") -> str:
        content = data.read() if hasattr(data, "read") else data
        aid = self._store(bucket, key, content, content_type)
        return f"pg://{bucket}/{key}?asset_id={aid}"

    def download(self, bucket: str, key: str) -> bytes:
        from sqlalchemy import text
        db = self._get_db()
        try:
            row = db.execute(
                text("SELECT content FROM kb_asset_content WHERE bucket=:b AND key=:k ORDER BY created_at DESC LIMIT 1"),
                {"b": bucket, "k": key},
            ).fetchone()
            if row:
                return row[0]
            raise FileNotFoundError(f"{bucket}/{key} not found")
        finally:
            db.close()

    def delete(self, bucket: str, key: str) -> None:
        from sqlalchemy import text
        db = self._get_db()
        try:
            db.execute(text("DELETE FROM kb_asset_content WHERE bucket=:b AND key=:k"), {"b": bucket, "k": key})
            db.commit()
        finally:
            db.close()

    def exists(self, bucket: str, key: str) -> bool:
        from sqlalchemy import text
        db = self._get_db()
        try:
            row = db.execute(
                text("SELECT 1 FROM kb_asset_content WHERE bucket=:b AND key=:k LIMIT 1"),
                {"b": bucket, "k": key},
            ).fetchone()
            return row is not None
        finally:
            db.close()

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        from sqlalchemy import text
        db = self._get_db()
        try:
            rows = db.execute(
                text("SELECT key FROM kb_asset_content WHERE bucket=:b AND key LIKE :p"),
                {"b": bucket, "p": f"{prefix}%"},
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            db.close()

    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        return f"pg://{bucket}/{key}?expires={datetime.utcnow() + timedelta(seconds=expiry_seconds)}"

    def health_check(self) -> bool:
        try:
            from src.database.db import get_db
            db = get_db()
            db.close()
            return True
        except Exception:
            return False
