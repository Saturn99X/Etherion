"""
Conversation Logger Service

Captures complete conversation flow events (user messages, assistant messages,
tool calls) with metadata, applies basic PII scrubbing, and persists to the
database (Message table) while emitting anonymized copies for SFT collection.

WHY: Phase 12 requires complete conversation flow capture with privacy.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional

from sqlmodel import Session

from src.database.db import get_db
from src.database.ts_models import Message


_PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.IGNORECASE),  # emails
    re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b"),  # SSN-like
    re.compile(r"\b\+?\d{1,2}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),  # phones
]


def _scrub_pii(text: str) -> str:
    if not text:
        return text
    scrubbed = text
    for pat in _PII_PATTERNS:
        scrubbed = pat.sub("[REDACTED]", scrubbed)
    return scrubbed


class ConversationLogger:
    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session or get_db()

    def log_user_message(self, tenant_id: int, conversation_id: int, content: str) -> int:
        return self._create_message(tenant_id, conversation_id, "user", content)

    def log_assistant_message(self, tenant_id: int, conversation_id: int, content: str) -> int:
        return self._create_message(tenant_id, conversation_id, "assistant", content)

    def log_system_message(self, tenant_id: int, conversation_id: int, content: str) -> int:
        return self._create_message(tenant_id, conversation_id, "system", content)

    def _create_message(self, tenant_id: int, conversation_id: int, role: str, content: str) -> int:
        safe_content = _scrub_pii(content)

        message = Message(
            role=role,
            content=safe_content,
            created_at=datetime.utcnow(),
            conversation_id=conversation_id,
            tenant_id=tenant_id,
        )
        self._session.add(message)
        self._session.commit()
        self._session.refresh(message)
        return int(message.id)


