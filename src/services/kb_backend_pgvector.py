"""pgvector KB backend using SQLModel async session."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .kb_backend import KBBackend

logger = logging.getLogger(__name__)


class PgvectorKBBackend(KBBackend):
    async def search(
        self,
        tenant_id: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        project_id: Optional[str] = None,
        kb_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        from src.database.db import get_session

        async for session in get_session():
            params: Dict[str, Any] = {
                "tid": tenant_id,
                "vec": str(query_embedding),
                "k": top_k,
            }
            sql = """
                SELECT d.doc_id, d.text_chunk, d.metadata_json, d.storage_uri,
                       1 - (d.embedding <=> CAST(:vec AS vector)) AS score
                FROM document d
                JOIN knowledgebase kb ON kb.id = d.kb_id
                WHERE d.tenant_id = :tid
            """
            if project_id:
                sql += " AND kb.project_id = :project_id"
                params["project_id"] = project_id
            if kb_type:
                sql += " AND kb.kb_type = :kb_type"
                params["kb_type"] = kb_type
            sql += " ORDER BY score DESC LIMIT :k"

            result = await session.execute(text(sql), params)
            rows = result.fetchall()
            return [
                {
                    "doc_id": r.doc_id,
                    "text_chunk": r.text_chunk,
                    "score": float(r.score),
                    "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
                    "storage_uri": r.storage_uri,
                }
                for r in rows
            ]
        return []

    async def upsert(
        self,
        tenant_id: str,
        doc_id: str,
        text: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        from sqlalchemy import text
        from src.database.db import get_session
        import json

        async for session in get_session():
            sql = """
                INSERT INTO document (doc_id, tenant_id, text_chunk, embedding, metadata_json, updated_at)
                VALUES (:doc_id, :tid, :text, CAST(:vec AS vector), :meta, NOW())
                ON CONFLICT (doc_id) DO UPDATE
                SET text_chunk = EXCLUDED.text_chunk,
                    embedding = EXCLUDED.embedding,
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = NOW()
            """
            await session.execute(text(sql), {
                "doc_id": doc_id,
                "tid": tenant_id,
                "text": text,
                "vec": str(embedding),
                "meta": json.dumps(metadata),
            })
            await session.commit()
            return

    async def delete(self, tenant_id: str, doc_id: str) -> None:
        from sqlalchemy import text
        from src.database.db import get_session

        async for session in get_session():
            await session.execute(
                text("DELETE FROM document WHERE doc_id = :doc_id AND tenant_id = :tid"),
                {"doc_id": doc_id, "tid": tenant_id},
            )
            await session.commit()
            return

    async def health_check(self) -> bool:
        from sqlalchemy import text
        from src.database.db import get_session
        try:
            async for session in get_session():
                await session.execute(text("SELECT 1"))
                return True
        except Exception:
            return False
        return False
