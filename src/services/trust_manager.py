"""
Whitelist & Trust Manager for security decisions.

Maintains per-user trust scores and explicit allowlists to adjust thresholds
for prompt security actions. Uses Redis for persistence when available.
"""

import os
from dataclasses import dataclass
from typing import Optional

try:
    import redis.asyncio as redis
except Exception:  # pragma: no cover
    redis = None


@dataclass
class TrustConfig:
    min_score: int = 0
    max_score: int = 100
    default_score: int = 50
    high_trust_threshold: int = 80
    low_trust_threshold: int = 20


class TrustManager:
    def __init__(self, config: Optional[TrustConfig] = None) -> None:
        self.config = config or TrustConfig()
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> Optional[redis.Redis]:
        if redis is None:
            return None
        if self._redis is not None:
            return self._redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            self._redis = redis.from_url(url, decode_responses=True)
            await self._redis.ping()
            return self._redis
        except Exception:
            self._redis = None
            return None

    async def get_score(self, user_key: str) -> int:
        r = await self._get_redis()
        if r:
            key = f"trust:{user_key}:score"
            val = await r.get(key)
            if val is None:
                await r.set(key, str(self.config.default_score))
                return self.config.default_score
            try:
                return int(val)
            except Exception:
                return self.config.default_score
        return self.config.default_score

    async def adjust_score(self, user_key: str, delta: int) -> int:
        score = await self.get_score(user_key)
        score = max(self.config.min_score, min(self.config.max_score, score + delta))
        r = await self._get_redis()
        if r:
            await r.set(f"trust:{user_key}:score", str(score))
        return score

    async def get_threshold_adjustment(self, user_key: str) -> int:
        """Return a risk threshold offset based on trust score (positive lowers risk)."""
        score = await self.get_score(user_key)
        if score >= self.config.high_trust_threshold:
            return -10  # more tolerant
        if score <= self.config.low_trust_threshold:
            return +10  # more strict
        return 0


_trust_manager_singleton: Optional[TrustManager] = None


def get_trust_manager() -> TrustManager:
    global _trust_manager_singleton
    if _trust_manager_singleton is None:
        _trust_manager_singleton = TrustManager()
    return _trust_manager_singleton


