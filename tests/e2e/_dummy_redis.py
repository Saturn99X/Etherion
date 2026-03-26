import asyncio
from typing import Any


class DummyRedisClient:
    """In-memory asynchronous stand-in for Redis used in E2E tests."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.lists: dict[str, list[Any]] = {}
        self.published: list[tuple[str, Any]] = []
        self.subscriptions: dict[str, asyncio.Queue] = {}

    async def get_client(self):
        return self

    async def get_pubsub_client(self):
        return self

    async def publish(self, channel: str, message: Any):
        self.published.append((channel, message))
        # Ensure the channel queue exists even if no subscriber yet, so messages are buffered
        queue = self.subscriptions.setdefault(channel, asyncio.Queue())
        await queue.put(message)
        return 1

    async def subscribe(self, channel: str):
        queue = self.subscriptions.setdefault(channel, asyncio.Queue())
        while True:
            payload = await queue.get()
            yield payload

    async def set(self, key: str, value: Any, ex: int | None = None, expire: int | None = None):
        self.store[key] = value
        return True

    async def setex(self, key: str, ttl: int, value: Any):
        # Minimal emulation: ignore TTL but store the value
        self.store[key] = value
        return True

    async def get(self, key: str, default: Any = None):
        return self.store.get(key, default)

    async def incr(self, key: str, amount: int = 1):
        value = int(self.store.get(key, 0)) + amount
        self.store[key] = value
        return value

    async def incrby(self, key: str, amount: int):
        return await self.incr(key, amount)

    async def decrby(self, key: str, amount: int):
        value = int(self.store.get(key, 0)) - amount
        self.store[key] = value
        return value

    async def delete(self, key: str):
        return 1 if self.store.pop(key, None) is not None else 0

    async def exists(self, key: str):
        return key in self.store

    async def lpush(self, key: str, value: Any):
        bucket = self.lists.setdefault(key, [])
        bucket.insert(0, value)
        return len(bucket)

    async def lrange(self, key: str, start: int, end: int):
        bucket = self.lists.get(key, [])
        n = len(bucket)
        # Handle negative indices similar to Redis semantics in a minimal way
        if start < 0:
            start = max(0, n + start)
        if end < 0:
            end = n + end
        end = min(end, n - 1)
        if start > end or n == 0:
            return []
        # Inclusive end
        return bucket[start:end + 1]

    async def ping(self):
        return True

    async def eval(self, script: str, numkeys: int, key: str, amount: int):
        current = int(self.store.get(key, 0))
        if current <= 0:
            self.store[key] = 0
            return 0
        if amount >= current:
            self.store[key] = 0
            return 0
        new_balance = current - amount
        self.store[key] = new_balance
        return new_balance

    async def close(self):
        return True

    async def scan(self, cursor: str = "0", match: str = "*", count: int = 100):
        # Simple implementation: ignore cursor/count and return all keys matching prefix patterns like "prefix:*"
        if match.endswith("*"):
            prefix = match[:-1]
            keys = [k for k in list(self.store.keys()) if k.startswith(prefix)]
        else:
            # Exact match
            keys = [k for k in list(self.store.keys()) if k == match]
        return ("0", keys)


def setup_dummy_redis(monkeypatch) -> DummyRedisClient:
    from src.core import redis as redis_module

    dummy = DummyRedisClient()
    redis_module._redis_client = dummy  # type: ignore[attr-defined]
    monkeypatch.setattr(redis_module, "get_redis_client", lambda: dummy)
    return dummy
