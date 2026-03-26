# Redis Pub/Sub in Etherion

## The Pub/Sub Model

Redis Pub/Sub is elegantly simple: publishers send messages to channels, and subscribers receive every message published to channels they're listening to. There's no broker persistence—if a subscriber isn't listening when a message is published, the message is lost. This is intentional. For real-time job status, we want *current* updates, not replayed history.

Here's the mental model:

```
Publisher (Worker)          Redis Channel              Subscriber (Client 1)
       |                                                      |
       | PUBLISH("job_status_abc", {...})  -------->  SUBSCRIBE("job_status_abc")
       |                                                      |
       |                   Redis Channel              Subscriber (Client 2)
       |                                                      |
       +-----> PUBLISH("job_status_abc", {...})  -------->  SUBSCRIBE("job_status_abc")
```

Every message published to `job_status_abc` goes to all current subscribers. Once they receive it, the message is gone from Redis. The channel is just a delivery mechanism.

## Channel Naming Convention

Etherion uses a strict naming convention to keep events organized and subscriptions scoped:

### Job Status Updates

**Channel:** `job_status_{job_id}`

Published by workers when a job transitions states or updates progress:

```python
await publish_job_status("job_abc123", {
    "job_id": "job_abc123",
    "status": "RUNNING",
    "timestamp": "2026-03-26T14:30:45.123Z",
    "progress_percentage": 45,
    "current_step_description": "Processing batch 2 of 5",
})
```

**Why per-job channels?** A tenant might have 1000 jobs running. If all status updates went to a single `tenant_jobs_1` channel, every subscriber would receive *every* update, even for jobs they don't care about. Per-job channels mean a client only gets events for the job they're monitoring. This is network-efficient and reduces GraphQL resolver load.

### Execution Trace Events

**Channel:** `job_trace_{job_id}`

Published by workers during execution to give granular, real-time visibility into what the agent is doing:

```python
await publish_execution_trace("job_abc123", {
    "type": "TOOL_INVOCATION_START",
    "tool_name": "google_drive_search",
    "step_description": "Searching Google Drive for Q1 reports",
    "timestamp": "2026-03-26T14:30:50.456Z",
    "metadata": {
        "query": "Q1 2026 earnings",
        "job_id": "job_abc123",
    }
})
```

Trace events are typically higher-volume than status updates. They're used for debugging and detailed dashboards. The GraphQL subscription resolver includes rate limiting to prevent trace events from overwhelming the client.

### Tenant-Wide UI Events

**Channel:** `ui_events_{tenant_id}`

Published for events that affect the entire tenant, not a single job:

```python
await publish_ui_event(tenant_id=456, {
    "type": "AGENT_DEPLOYED",
    "message": "Custom agent 'market_analyzer' was deployed",
    "timestamp": "2026-03-26T14:35:00.789Z",
    "agent_id": "agent_market_analyzer",
})
```

Clients subscribe to this channel to show a live feed of tenant-wide changes. Multiple users on the same tenant see the same notifications without polling a database.

## What Events Are Published and When

### Job Status Lifecycle

When a job transitions through its lifecycle, a status update is published:

1. **QUEUED** → Job is waiting in the queue
2. **RUNNING** → Worker has picked up the job
3. **COMPLETED** → Job succeeded
4. **FAILED** → Job failed with an error
5. **CANCELLED** → User or system cancelled the job

Each transition triggers a publish. Additionally, while running, periodic updates with progress percentage are sent.

### Trace Events During Execution

While a job is RUNNING, the agent publishes detailed trace events:

- `STEP_START` / `STEP_END` — Each orchestration step begins or completes
- `TOOL_INVOCATION_START` / `TOOL_INVOCATION_END` — Agent is calling an external tool
- `AGENT_THOUGHT` — Agent is reasoning about the next action
- `ERROR_OCCURRED` — A non-fatal error happened; the agent is retrying
- `MEMORY_UPDATED` — Long-term memory for the agent was modified

The worker code publishes these events by calling `publish_execution_trace()`. The frequency and verbosity depend on how much logging the worker does.

## The Redis Client Implementation

Etherion wraps Redis with an async client (`src/core/redis.py`) that handles Pub/Sub lifecycle gracefully:

```python
class RedisClient:
    async def subscribe(self, channel: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to a Redis channel and yield messages."""
        client = await self.get_pubsub_client()
        pubsub = client.pubsub()
        local_q = _get_local_queue(channel)

        async def _forward_from_redis():
            await asyncio.to_thread(pubsub.subscribe, channel)
            while True:
                try:
                    message = await asyncio.to_thread(
                        pubsub.get_message,
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )
                    if message and message['type'] == 'message':
                        data = json.loads(message['data'])
                        await local_q.put(data)
                except asyncio.CancelledError:
                    break

        forwarder = asyncio.create_task(_forward_from_redis())
        try:
            while True:
                payload = await local_q.get()
                yield payload
        finally:
            forwarder.cancel()
```

This implementation has a subtle but important design detail: **in-process mirroring**. When a message is published, it goes to an in-process `asyncio.Queue` in addition to Redis. A background forwarder reads from Redis and puts messages into the same queue. This ensures that if a subscription is created milliseconds after a publish, the message isn't lost to Redis's fire-and-forget model.

The `_local_bus` dictionary maps channel names to queues, so multiple subscribers to the same channel share the same queue. Redis broadcasts go to the queue, and each subscriber gets the message independently.

## Publishing from the Worker

When a worker wants to publish a job status update, it uses the convenience functions:

```python
# src/core/redis.py
async def publish_job_status(job_id: str, status_data: Dict[str, Any]) -> int:
    """Convenience function to publish job status updates."""
    client = get_redis_client()
    channel = f"job_status_{job_id}"
    return await client.publish(channel, status_data)
```

The worker calls this from anywhere in its code:

```python
# In a worker task
await publish_job_status(job_id="job_abc123", {
    "status": "RUNNING",
    "progress_percentage": 50,
    "current_step_description": "Running validation",
    "timestamp": datetime.datetime.utcnow().isoformat(),
})
```

The `publish()` method serializes the dict to JSON, sends it to Redis, and returns the number of subscribers who received it. If the return is 0, no one was listening (which is fine; the job runs regardless).

## Scaling Considerations

### Single Redis Instance

Etherion runs with a single Redis instance (or optionally, Redis Sentinel for HA). Pub/Sub doesn't require clustering; all publishers and subscribers connect to the same Redis server. Messages are processed in-memory at wire speed.

As long as the Redis instance can handle the message throughput (typically millions of messages per second on a standard instance), the system scales. For 1000 concurrent jobs with 10 trace events per second each, that's 10k messages per second—well within Redis's capabilities.

### Per-Job Channels Mean Linear Scalability

By using `job_status_{job_id}`, each job gets its own channel. A job with 10 subscribers gets 10 Redis PubSub subscriptions, but they're independent. If job A publishes 100 messages and job B publishes 10, subscribers to job A are never notified about job B's events. This channel separation is what makes Etherion scale.

### In-Process Mirroring Trade-Off

The in-process `_local_bus` queue is not shared across multiple Cloud Run instances. Each instance has its own queue. This means:

- If a subscription starts on instance 1, it receives updates from instance 1's local queue (no cross-instance communication).
- If the same job publishes to instance 2 (which can happen in multi-instance scenarios), subscribers on instance 1 only get the update if they also connect to instance 2's Redis subscription.

In practice, this is resolved because all instances connect to the same Redis instance. The background forwarder ensures every instance receives every published message via Redis Pub/Sub. The local queue is just an optimization to avoid race conditions in tests and development.

## Rate Limiting and Backpressure

To prevent a bursty job from flooding clients, each subscription resolver includes rate limiting:

```python
# Per IP, per job, per minute window: max 60 events
window_key = f"wsrate:exec:{ip}:{job_id}:{int(asyncio.get_event_loop().time()//60)}"
count = await redis.incr(window_key)
if count > msg_limit:
    continue  # drop the message silently
```

If a job publishes 200 trace events in one second, the first 60 are delivered to the client, and the rest are dropped. The client sees a steady stream of updates without being overwhelmed. This keeps the WebSocket connection responsive and prevents client-side memory bloat.

## Error Handling

If Redis becomes unavailable, what happens? In Etherion:

1. A subscription starts but Redis connection fails → The subscription yields an error to the client
2. The client sees `status: "ERROR"` with an error message
3. The user's UI shows a banner: "Connection lost; attempting to reconnect"
4. The client can re-subscribe automatically; the new subscription will work once Redis is back

Etherion doesn't retry publishing if Redis is down; it's a hard failure. Jobs continue to run, but updates don't flow to clients. This is acceptable because Redis uptime is typically > 99.9% in production, and jobs are resilient to transient connectivity issues.

## Key Takeaways

- **Simple model:** Publishers send, subscribers receive, no history
- **Scoped channels:** Per-job channels keep subscriptions precise and efficient
- **In-process mirroring:** Avoids race conditions between publish and subscribe
- **Rate limiting:** Prevents bursty jobs from overwhelming clients
- **Multi-instance ready:** All instances connect to the same Redis, so clients on any instance can subscribe to any job
