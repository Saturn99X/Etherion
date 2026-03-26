"""Async tool request queue — human-in-the-loop confirmation via Redis."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)

_PREFIX = "etherion:toolreq"
_APPROVAL_PREFIX = "etherion:toolapproval"


class ToolRequestQueue:
    def _client(self):
        from src.core.redis import get_redis_client
        return get_redis_client()

    def enqueue(self, job_id: str, tool_name: str, args: Dict[str, Any]) -> str:
        request_id = f"tr_{uuid.uuid4().hex[:12]}"
        payload = json.dumps({"request_id": request_id, "job_id": job_id, "tool_name": tool_name, "args": args})
        self._client().lpush(f"{_PREFIX}:{job_id}", payload)
        logger.info("Enqueued tool request %s for job %s: %s", request_id, job_id, tool_name)
        return request_id

    def wait_for_approval(self, request_id: str, timeout: int = 300) -> bool:
        result = self._client().brpop(f"{_APPROVAL_PREFIX}:{request_id}", timeout=timeout)
        if result is None:
            return False
        _, value = result
        return json.loads(value).get("approved", False)

    def approve(self, request_id: str) -> None:
        self._client().lpush(
            f"{_APPROVAL_PREFIX}:{request_id}",
            json.dumps({"approved": True}),
        )

    def reject(self, request_id: str) -> None:
        self._client().lpush(
            f"{_APPROVAL_PREFIX}:{request_id}",
            json.dumps({"approved": False}),
        )
