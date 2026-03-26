"""Higher-level Redis helpers built on top of src.core.redis.get_redis_client."""
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _client():
    from src.core.redis import get_redis_client
    return get_redis_client()


def set_with_namespace(ns: str, key: str, value: Any, ttl: Optional[int] = None) -> None:
    r = _client()
    full_key = f"{ns}:{key}"
    serialized = json.dumps(value) if not isinstance(value, (str, bytes)) else value
    if ttl:
        r.set(full_key, serialized, ex=ttl)
    else:
        r.set(full_key, serialized)


def get_with_namespace(ns: str, key: str) -> Optional[Any]:
    r = _client()
    val = r.get(f"{ns}:{key}")
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def invalidate_namespace(ns: str) -> int:
    r = _client()
    pattern = f"{ns}:*"
    keys = r.keys(pattern)
    if keys:
        return r.delete(*keys)
    return 0


def atomic_counter(key: str, amount: int = 1) -> int:
    r = _client()
    return r.incrby(key, amount)


@asynccontextmanager
async def distributed_lock(key: str, ttl: int = 30):
    """Simple distributed lock using SET NX EX. Not reentrant."""
    import asyncio
    import uuid
    r = _client()
    token = str(uuid.uuid4())
    lock_key = f"lock:{key}"
    acquired = r.set(lock_key, token, nx=True, ex=ttl)
    if not acquired:
        raise RuntimeError(f"Could not acquire lock: {key}")
    try:
        yield
    finally:
        # Only release if we still own the lock
        current = r.get(lock_key)
        if current and current.decode() == token:
            r.delete(lock_key)
