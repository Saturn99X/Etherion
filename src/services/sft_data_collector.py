"""
SFT Data Collector Service

Aggregates conversation turns and execution metadata into anonymized traces and
uploads them to the fine-tuning bucket via FineTuningGCSService.

WHY: Phase 12 requires comprehensive SFT data capture with privacy.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime

from sqlmodel import Session, select

from src.database.db import get_db
from src.database.ts_models import Message, Conversation
from src.services.fine_tuning_gcs import FineTuningGCSService


def _hash_tenant(tenant_id: int) -> str:
    return hashlib.sha256(str(tenant_id).encode("utf-8")).hexdigest()[:16]


class SFTDataCollector:
    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session or get_db()
        self._gcs = FineTuningGCSService()

    async def collect_conversation_trace(self, tenant_id: int, conversation_id: int, job_id: str) -> str:
        """
        Build an anonymized trace from conversation messages and upload to GCS.
        """
        # Fetch conversation to validate tenant
        convo = self._session.get(Conversation, conversation_id)
        if not convo or int(convo.tenant_id) != int(tenant_id):
            raise ValueError("Conversation not found or cross-tenant access")

        # Fetch messages in order
        stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.tenant_id == tenant_id,
        ).order_by(Message.created_at.asc())
        rows: List[Message] = list(self._session.exec(stmt))

        # Build anonymized trace
        turns: List[Dict[str, Any]] = []
        for m in rows:
            turns.append({
                "role": m.role,
                "content": m.content,  # already scrubbed by ConversationLogger
                "ts": m.created_at.isoformat() if m.created_at else None,
            })

        trace: Dict[str, Any] = {
            "metadata": {
                "job_id": job_id,
                "tenant_hash": _hash_tenant(tenant_id),
                "conversation_id": conversation_id,
                "collected_at": datetime.utcnow().isoformat(),
                "schema_version": "1.0"
            },
            "turns": turns,
        }

        # Upload anonymized trace
        gcs_uri = await self._gcs.upload_trace_to_fine_tuning_bucket(
            anonymized_trace=trace,
            job_id=job_id,
            tenant_hash=_hash_tenant(tenant_id)
        )

        return gcs_uri


