"""Abstract KB backend + factory."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class KBBackend(ABC):
    @abstractmethod
    async def search(
        self,
        tenant_id: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        project_id: Optional[str] = None,
        kb_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return top_k documents with keys: doc_id, text_chunk, score, metadata, storage_uri."""

    @abstractmethod
    async def upsert(
        self,
        tenant_id: str,
        doc_id: str,
        text: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        """Insert or update a document."""

    @abstractmethod
    async def delete(self, tenant_id: str, doc_id: str) -> None:
        """Delete a document."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if backend is reachable."""


def get_kb_backend() -> KBBackend:
    backend = os.getenv("KB_VECTOR_BACKEND", "pgvector").lower()
    if backend == "bigquery":
        from .kb_backend_bq import BigQueryKBBackend
        return BigQueryKBBackend()
    else:
        from .kb_backend_pgvector import PgvectorKBBackend
        return PgvectorKBBackend()
