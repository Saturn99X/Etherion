"""
Behavior monitoring and graduated lockout for suspicious activity.

Tracks per-user prompt-injection detections and applies temporary lockouts
if thresholds are exceeded. Uses Redis (via redis.asyncio) when available,
falls back to in-memory map for single-process dev.
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from src.core.redis import get_redis_client


@dataclass
class BehaviorPolicy:
    window_seconds: int = 600
    max_incidents: int = 3
    lockout_seconds: int = 900


class BehaviorMonitor:
    def __init__(self, policy: Optional[BehaviorPolicy] = None) -> None:
        self.policy = policy or BehaviorPolicy()
        self._mem_incidents: Dict[str, int] = {}
        self._mem_lockouts: Dict[str, datetime] = {}

    async def close(self) -> None:
        """Close resources (no-op for shared redis client)."""
        pass

    async def record_incident(self, user_key: str) -> None:
        now = datetime.now(timezone.utc)
        client = get_redis_client()
        
        # Try Redis first
        try:
            key = f"behavior:{user_key}:incidents"
            await client.incr(key)
            await client.expire(key, self.policy.window_seconds)
            count = int(await client.get(key) or 0)
        except Exception:
            # Fallback to memory
            self._mem_incidents[user_key] = self._mem_incidents.get(user_key, 0) + 1
            count = self._mem_incidents[user_key]

        if count >= self.policy.max_incidents:
            await self._apply_lockout(user_key, now)

    async def _apply_lockout(self, user_key: str, now: datetime) -> None:
        until = now + timedelta(seconds=self.policy.lockout_seconds)
        client = get_redis_client()
        
        try:
            key = f"behavior:{user_key}:lockout"
            await client.set(key, until.isoformat(), expire=self.policy.lockout_seconds)
        except Exception:
            self._mem_lockouts[user_key] = until

    async def is_locked_out(self, user_key: str) -> bool:
        now = datetime.now(timezone.utc)
        client = get_redis_client()
        
        try:
            key = f"behavior:{user_key}:lockout"
            val = await client.get(key)
            if not val:
                return False
            try:
                until = datetime.fromisoformat(val)
                return until > now
            except Exception:
                return False
        except Exception:
            until = self._mem_lockouts.get(user_key)
            return bool(until and until > now)


_behavior_monitor_singleton: Optional[BehaviorMonitor] = None


def get_behavior_monitor() -> BehaviorMonitor:
    global _behavior_monitor_singleton
    if _behavior_monitor_singleton is None:
        _behavior_monitor_singleton = BehaviorMonitor()
    return _behavior_monitor_singleton


