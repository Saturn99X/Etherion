import os
import logging
import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
import redis  # Use sync client
import json
from contextlib import asynccontextmanager
import contextlib
import ssl

logger = logging.getLogger(__name__)

# In-process pub/sub mirror to avoid race conditions in tests/dev (e.g., DummyRedis drops
# messages published before a subscription queue exists). We always mirror publishes to
# this local bus and have subscriptions read from it while a background forwarder pipes
# Redis messages into the same queue.
_local_bus: Dict[str, asyncio.Queue] = {}

def _get_local_queue(channel: str) -> asyncio.Queue:
    q = _local_bus.get(channel)
    if q is None:
        q = asyncio.Queue()
        _local_bus[channel] = q
    return q


def _clear_local_bus(prefixes: Optional[list[str]] = None) -> int:
    if not prefixes:
        n = len(_local_bus)
        _local_bus.clear()
        return n
    removed = 0
    for k in list(_local_bus.keys()):
        try:
            if any(str(k).startswith(p) for p in prefixes):
                _local_bus.pop(k, None)
                removed += 1
        except Exception:
            continue
    return removed

class RedisClient:
    """Redis client utility for Pub/Sub operations and caching.
    
    Uses synchronous redis client wrapped in asyncio.to_thread to avoid
    SSL handshake issues with redis.asyncio and Memorystore.
    """

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis client."""
        self.redis_url = None
        if redis_url:
            self.redis_url = redis_url
        if not self.redis_url:
            self.redis_url = os.getenv("ETHERION_REDIS_URL") or os.getenv("REDIS_URL")
            if not self.redis_url:
                if os.getenv("ENVIRONMENT") == "production":
                    raise ValueError("REDIS_URL environment variable is required for production deployment")
                self.redis_url = "redis://localhost:6379/0"
        # TLS detection and certificate requirements (for Memorystore SERVER_AUTHENTICATION)
        self._is_tls = self.redis_url.lower().startswith("rediss://")
        # Allow override via env; default to 'none' to accommodate Memorystore server-auth without client CA chain
        self._ssl_cert_reqs_env = os.getenv("REDIS_SSL_CERT_REQS", "none").lower()
        if self._ssl_cert_reqs_env == "required":
            self._ssl_cert_reqs = ssl.CERT_REQUIRED
        elif self._ssl_cert_reqs_env == "optional":
            self._ssl_cert_reqs = ssl.CERT_OPTIONAL
        else:
            self._ssl_cert_reqs = ssl.CERT_NONE
        self._client: Optional[redis.Redis] = None
        self._pubsub_client: Optional[redis.Redis] = None
        # Test-friendly mirror store so E2E can introspect keys (e.g., cache assertions)
        # This does NOT replace Redis; it's only a shadow of keys set via helper methods.
        self._mirror_store: Dict[str, Any] = {}
        # Expose as `store` to match DummyRedis interface used in tests
        self.store = self._mirror_store

    async def get_client(self) -> redis.Redis:
        """Get or create Redis client (sync client, used via asyncio.to_thread)."""
        if self._client is None:
            ssl_kwargs = {}
            if self._is_tls:
                ssl_kwargs["ssl_cert_reqs"] = self._ssl_cert_reqs
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                max_connections=20,
                **ssl_kwargs,
            )
        return self._client

    async def get_pubsub_client(self) -> redis.Redis:
        """Get or create separate Redis client for Pub/Sub operations."""
        if self._pubsub_client is None:
            ssl_kwargs = {}
            if self._is_tls:
                ssl_kwargs["ssl_cert_reqs"] = self._ssl_cert_reqs
            self._pubsub_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                max_connections=20,
                **ssl_kwargs,
            )
        return self._pubsub_client

    async def publish(self, channel: str, message: Dict[str, Any]) -> int:
        """Publish a message to a Redis channel."""
        try:
            client = await self.get_client()
            json_message = json.dumps(message)
            result = await asyncio.to_thread(client.publish, channel, json_message)
            logger.debug(f"Published message to channel {channel}: {json_message}")
            # Mirroring removed to ensure consistency across multiple Cloud Run instances.
            # Production relies exclusively on Redis for Pub/Sub.
            return result
        except Exception as e:
            logger.error(f"Error publishing to channel {channel}: {e}")
            raise

    async def delete(self, key: str) -> int:
        client = await self.get_client()
        try:
            return int(await asyncio.to_thread(client.delete, key))
        finally:
            try:
                self._mirror_store.pop(str(key), None)
            except Exception:
                pass

    async def delete_by_pattern(self, pattern: str, *, max_keys: int = 5000, count: int = 500) -> Dict[str, Any]:
        client = await self.get_client()

        def _scan_and_delete() -> Dict[str, Any]:
            deleted = 0
            seen = 0
            try:
                for key in client.scan_iter(match=pattern, count=count):
                    seen += 1
                    try:
                        deleted += int(client.delete(key))
                        try:
                            self._mirror_store.pop(str(key), None)
                        except Exception:
                            pass
                    except Exception:
                        continue
                    if deleted >= int(max_keys):
                        break
            except Exception:
                pass
            return {"pattern": pattern, "seen": seen, "deleted": deleted, "max_keys": int(max_keys)}

        return await asyncio.to_thread(_scan_and_delete)

    async def purge_local_bus(self) -> int:
        return _clear_local_bus()

    async def subscribe(self, channel: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to a Redis channel and yield messages.

        Implementation details:
        - Start a background forwarder that reads from real Redis Pub/Sub and
          mirrors messages into an in-process asyncio.Queue for the channel.
        - Yield from the local queue so early publications (mirrored on publish)
          are not lost even if the external subscription isn't ready yet.
        """
        client = await self.get_pubsub_client()
        pubsub = client.pubsub()

        local_q = _get_local_queue(channel)

        async def _forward_from_redis():
            try:
                await asyncio.to_thread(pubsub.subscribe, channel)
                logger.info(f"Subscribed to channel: {channel}")
                while True:
                    try:
                        message = await asyncio.to_thread(pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0)
                        if message is not None and message['type'] == 'message':
                            try:
                                data = json.loads(message['data'])
                                await local_q.put(data)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to decode message from {channel}: {e}")
                        else:
                            await asyncio.sleep(0.01)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Error receiving message from {channel}: {e}")
                        break
            finally:
                try:
                    await asyncio.to_thread(pubsub.unsubscribe, channel)
                    await asyncio.to_thread(pubsub.close)
                except Exception as e:
                    logger.error(f"Error closing subscription to {channel}: {e}")

        forwarder = asyncio.create_task(_forward_from_redis())
        try:
            while True:
                payload = await local_q.get()
                yield payload
        finally:
            forwarder.cancel()
            with contextlib.suppress(Exception):
                await forwarder

    @asynccontextmanager
    async def subscribe_context(self, channel: str):
        """Context manager for subscribing to a channel."""
        client = await self.get_pubsub_client()
        pubsub = client.pubsub()

        try:
            await asyncio.to_thread(pubsub.subscribe, channel)
            logger.info(f"Subscribed to channel: {channel}\"")
            yield pubsub
        except Exception as e:
            logger.error(f"Error in subscription context for {channel}: {e}")
            raise
        finally:
            try:
                await asyncio.to_thread(pubsub.unsubscribe, channel)
                await asyncio.to_thread(pubsub.close)
            except Exception as e:
                logger.error(f"Error closing subscription context for {channel}: {e}")

    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set a key-value pair in Redis."""
        try:
            client = await self.get_client()
            json_value = json.dumps(value) if not isinstance(value, str) else value
            result = await asyncio.to_thread(client.set, key, json_value, ex=expire)
            # Mirror into in-memory store for tests that introspect keys
            try:
                self._mirror_store[key] = json_value
            except Exception:
                pass
            return result
        except Exception as e:
            logger.error(f"Error setting key {key}: {e}")
            raise

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value from Redis."""
        try:
            client = await self.get_client()
            value = await asyncio.to_thread(client.get, key)
            if value is None:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.error(f"Error getting key {key}: {e}")
            return default

    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment an integer value stored at key by amount (default 1)."""
        try:
            client = await self.get_client()
            new_value = await asyncio.to_thread(client.incrby, key, amount)
            return int(new_value)
        except Exception as e:
            logger.error(f"Error incrementing key {key} by {amount}: {e}")
            raise

    async def decr(self, key: str, amount: int = 1) -> int:
        """Decrement an integer value stored at key by amount (default 1)."""
        try:
            client = await self.get_client()
            new_value = await asyncio.to_thread(client.decrby, key, amount)
            return int(new_value)
        except Exception as e:
            logger.error(f"Error decrementing key {key} by {amount}: {e}")
            raise

    async def lpush(self, key: str, value: Any) -> int:
        """Push a value onto the head of a list and return the new length."""
        try:
            client = await self.get_client()
            serialized = json.dumps(value) if not isinstance(value, str) else value
            length = await asyncio.to_thread(client.lpush, key, serialized)
            return int(length)
        except Exception as e:
            logger.error(f"Error LPUSH to list {key}: {e}")
            raise

    async def delete(self, key: str) -> int:
        """Delete a key from Redis."""
        try:
            client = await self.get_client()
            result = await asyncio.to_thread(client.delete, key)
            try:
                self._mirror_store.pop(key, None)
            except Exception:
                pass
            return result
        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            raise

    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        try:
            client = await self.get_client()
            result = await asyncio.to_thread(client.exists, key)
            return bool(result)
        except Exception as e:
            logger.error(f"Error checking existence of key {key}: {e}")
            return False

    async def ping(self) -> bool:
        """Test Redis connection."""
        try:
            client = await self.get_client()
            await asyncio.to_thread(client.ping)
            return True
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on a key."""
        client = await self.get_client()
        return await asyncio.to_thread(client.expire, key, seconds)

    async def execute_command(self, *args, **kwargs):
        """Execute arbitrary Redis command (needed by RedisSearch/caching)."""
        client = await self.get_client()
        return await asyncio.to_thread(client.execute_command, *args, **kwargs)

    async def scan_iter(self, match=None, count=None):
        """Scan Redis keys matching pattern."""
        client = await self.get_client()
        # client.scan_iter is a synchronous generator, so we need to iterate it in a thread
        # and yield results back to the async context.
        # This is a common pattern for wrapping sync generators in async.
        queue = asyncio.Queue()
        stop_event = asyncio.Event()

        def _sync_scan():
            try:
                for key in client.scan_iter(match=match, count=count):
                    if stop_event.is_set():
                        break
                    queue.put_nowait(key)
            except Exception as e:
                logger.error(f"Error during Redis scan_iter: {e}")
            finally:
                queue.put_nowait(None) # Sentinel value to signal end

        task = asyncio.to_thread(_sync_scan)

        try:
            while True:
                key = await queue.get()
                if key is None:
                    break
                yield key
        finally:
            stop_event.set()
            await task # Ensure the thread finishes
            # The queue might still have items if the consumer stopped early,
            # but the sentinel will eventually be consumed or the queue will be GC'd.

    async def close(self):
        """Close Redis connections."""
        if self._client:
            await asyncio.to_thread(self._client.close)
            self._client = None
        if self._pubsub_client:
            await asyncio.to_thread(self._pubsub_client.close)
            self._pubsub_client = None

# Global Redis client instance
_redis_client: Optional[RedisClient] = None

def get_redis_client() -> RedisClient:
    """Get global Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client

async def publish_job_status(job_id: str, status_data: Dict[str, Any]) -> int:
    """Convenience function to publish job status updates."""
    client = get_redis_client()
    channel = f"job_status_{job_id}"
    # Reliance on local bus removed for Cloud Run multi-instance consistency.
    return await client.publish(channel, status_data)

async def subscribe_to_job_status(job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    """Convenience function to subscribe to job status updates."""
    client = get_redis_client()
    channel = f"job_status_{job_id}"
    async for message in client.subscribe(channel):
        yield message


async def publish_execution_trace(job_id: str, event_data: Dict[str, Any]) -> int:
    """Publish an execution trace UI event for a given job.

    The event is delivered over Redis Pub/Sub channel `job_trace_{job_id}` and
    consumed by GraphQL subscription `subscribeToExecutionTrace`.

    Required keys in event_data should include at least `type` and `step_description`
    for UI triggers; additional context (tenant_id, agent_name, tool_name, etc.)
    may be included in `event_data` and will be forwarded as-is.
    """
    client = get_redis_client()
    channel = f"job_trace_{job_id}"
    payload = dict(event_data)
    if "job_id" not in payload:
        payload["job_id"] = job_id
    if "timestamp" not in payload:
        import datetime as _dt
        payload["timestamp"] = _dt.datetime.utcnow().isoformat()
    # Reliance on local bus removed for Cloud Run multi-instance consistency.
    return await client.publish(channel, payload)


async def publish_ui_event(tenant_id: int, event_data: Dict[str, Any]) -> int:
    """Publish a tenant-scoped UI event (non-job-scoped)."""
    client = get_redis_client()
    channel = f"ui_events_{tenant_id}"
    payload = dict(event_data)
    if "timestamp" not in payload:
        import datetime as _dt
        payload["timestamp"] = _dt.datetime.utcnow().isoformat()
    if "tenant_id" not in payload:
        payload["tenant_id"] = tenant_id
    return await client.publish(channel, payload)


async def subscribe_to_ui_events(tenant_id: int) -> AsyncGenerator[Dict[str, Any], None]:
    """Subscribe to tenant-scoped UI events via local bus with Redis forwarder."""
    client = get_redis_client()
    channel = f"ui_events_{tenant_id}"
    async for message in client.subscribe(channel):
        yield message


async def subscribe_to_execution_trace(job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    """Subscribe to job-scoped execution trace events via local bus with Redis forwarder."""
    client = get_redis_client()
    channel = f"job_trace_{job_id}"
    async for message in client.subscribe(channel):
        yield message

# ============================
# Job cancellation primitives
# ============================

_JOB_CANCEL_PREFIX = "job_cancel_"

async def set_job_cancel(job_id: str, ttl_seconds: int = 3600) -> bool:
    """Mark a job as cancelled via a Redis key with TTL.

    This is a soft-cancel signal. Runtime loops should periodically check this flag
    and abort gracefully, publishing STOP_ACK and setting terminal status.
    """
    key = f"{_JOB_CANCEL_PREFIX}{job_id}"
    client = get_redis_client()
    # store a simple boolean true; mirror as string for interoperability
    return await client.set(key, True, expire=ttl_seconds)

async def is_job_cancelled(job_id: str) -> bool:
    """Return True if a cancel signal exists for the given job."""
    key = f"{_JOB_CANCEL_PREFIX}{job_id}"
    client = get_redis_client()
    val = await client.get(key, default=None)
    return bool(val) and str(val).lower() not in ("0", "false", "none", "null")
