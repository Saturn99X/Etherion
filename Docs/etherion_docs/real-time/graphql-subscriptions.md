# GraphQL Subscriptions in Etherion

## What is a GraphQL Subscription?

A GraphQL subscription is a way for a client to **listen** to a server-side event stream. Unlike queries (one-shot read) and mutations (one-shot write), subscriptions are long-lived connections that push updates to the client over time.

In REST terms, a subscription is like opening a `fetch` with `ReadableStream` and never closing it. The server keeps the connection open and writes events to it as they happen. In GraphQL, this is formalized with the `subscription` type in the schema and is typically transported over WebSocket.

## The Strawberry Pattern

Etherion uses **Strawberry**, a Python GraphQL library. In Strawberry, you define subscriptions using the `@strawberry.subscription` decorator and async generators. Here's the pattern:

```python
@strawberry.subscription
async def subscribeToJobStatus(
    self,
    info: Info,
    job_id: str
) -> AsyncGenerator[JobStatusUpdate, None]:
    """
    Subscribe to real-time status updates for a specific job.
    """
    # 1. Authorize the user
    current_user = await _get_current_user_from_ws_or_headers(info)
    if not current_user:
        yield JobStatusUpdate(
            job_id=job_id,
            status="ERROR",
            message="Authentication required"
        )
        return

    # 2. Verify job ownership
    with session_scope() as session:
        job = session.query(Job).filter(Job.job_id == job_id).first()
        if not job or job.user_id != current_user.id:
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                message="Access denied"
            )
            return

    # 3. Subscribe to Redis and yield updates
    redis_client = get_redis_client()
    async for update_data in subscribe_to_job_status(job_id):
        try:
            job_status_update = JobStatusUpdate(
                job_id=update_data.get("job_id", job_id),
                status=update_data.get("status", "UNKNOWN"),
                timestamp=update_data.get("timestamp", ""),
                message=update_data.get("message"),
                progress_percentage=update_data.get("progress_percentage"),
                current_step_description=update_data.get("current_step_description"),
                error_message=update_data.get("error_message"),
                additional_data=update_data.get("additional_data")
            )

            yield job_status_update

            # Break when job reaches terminal state
            if update_data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                break

        except Exception as e:
            logger.error(f"Error processing update: {e}")
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                error_message=f"Error: {str(e)}"
            )

    logger.info(f"Subscription ended for job {job_id}")
```

This resolver is an **async generator**. Each `yield` sends one update to the client. The generator runs in the context of that specific client's WebSocket connection, so different clients get independent generators.

## The Async Generator Pattern

The key insight is that a subscription resolver is a coroutine that yields values over time:

```python
async def subscribeToJobStatus(...) -> AsyncGenerator[JobStatusUpdate, None]:
    # Setup phase (authorization, validation)
    # ...

    # Listen phase
    async for event in some_stream:
        yield convert_to_graphql_type(event)
```

When the client opens a WebSocket and sends a subscription request, Strawberry:

1. Invokes the resolver as an async generator
2. Starts iterating over it
3. Each `yield` sends a message to the client
4. When the generator ends (either naturally or via exception), the subscription closes

The generator itself bridges Redis events to GraphQL types. It's the translator.

## Subscribing to Redis from the Resolver

Inside the resolver, we subscribe to Redis and iterate over messages:

```python
async for update_data in subscribe_to_job_status(job_id):
    # update_data is a dict from Redis
    # Convert it to a Strawberry type and yield
    job_status_update = JobStatusUpdate(...)
    yield job_status_update
```

The `subscribe_to_job_status()` helper is a convenience function:

```python
# src/core/redis.py
async def subscribe_to_job_status(job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    """Convenience function to subscribe to job status updates."""
    client = get_redis_client()
    channel = f"job_status_{job_id}"
    async for message in client.subscribe(channel):
        yield message
```

This is elegant because it's just a layer on top of `client.subscribe()`, which does the heavy lifting of reading from Redis and yielding messages.

## Authorization in Subscriptions

Authorization happens early in the resolver, before we even subscribe to Redis. This is critical for security:

```python
# 1. Get the authenticated user
current_user = await _get_current_user_from_ws_or_headers(info)
if not current_user:
    yield error_response("Authentication required")
    return

# 2. Verify job belongs to the user
with session_scope() as session:
    job = session.query(Job).filter(Job.job_id == job_id).first()
    if not job or job.user_id != current_user.id or job.tenant_id != current_user.tenant_id:
        yield error_response("Access denied")
        return

# 3. Only now do we subscribe to Redis
async for update in subscribe_to_job_status(job_id):
    yield convert_to_graphql_type(update)
```

This pattern ensures:
- An unauthenticated user gets an error response immediately
- A user who doesn't own the job never sees its updates
- Only authorized users can subscribe to a job

The subscription checks permissions at subscription start time. If permissions change (e.g., job is deleted), the resolver might emit an error, but the subscription doesn't proactively check permissions on every message. This is acceptable because jobs are immutable during execution.

## Terminal State and Cleanup

When a job reaches a terminal state (COMPLETED, FAILED, or CANCELLED), the resolver breaks and the generator ends:

```python
if update_data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
    logger.info(f"Job {job_id} reached terminal state: {update_data.get('status')}")
    break
```

Breaking the loop causes the async generator to end, which signals to Strawberry that the subscription is complete. The WebSocket connection can close gracefully, and both client and server know the subscription is done.

This is better than leaving the subscription open indefinitely. The client doesn't have to guess when to unsubscribe; it knows when the job is done.

## Rate Limiting in Subscriptions

For high-volume streams like execution traces, rate limiting prevents overwhelming the client:

```python
# In subscribeToExecutionTrace resolver
msg_limit = 60  # events per minute per IP/job
window_key = f"wsrate:exec:{ip}:{job_id}:{int(asyncio.get_event_loop().time()//60)}"

async for evt in subscribe_to_execution_trace(job_id):
    try:
        count = await redis.incr(window_key)
        if count == 1:
            await redis.expire(window_key, 70)
        if count > msg_limit:
            continue  # drop excess events silently
    except Exception:
        pass

    yield JobStatusUpdate(...)
```

We track event count per IP, per job, per minute window. If the count exceeds 60, we skip the event. This keeps the client from being flooded with trace events from a bursty job.

## Connection Limiting

Additionally, the resolver tracks concurrent WebSocket connections:

```python
conn_limit = 10
conn_key = f"wsconn:exec:{ip}"

try:
    active = await redis.incr(conn_key)
    if active == 1:
        await redis.expire(conn_key, 3600)
    if active > conn_limit:
        await redis.decr(conn_key)
        raise Exception("Too many websocket connections from this IP")

    # Subscribe and yield...

finally:
    await redis.decr(conn_key)
```

We limit each IP to 10 concurrent execution trace subscriptions. This prevents a single IP from exhausting server resources by opening thousands of WebSocket connections.

## Error Handling

If an error occurs while yielding, we catch it and emit an error update:

```python
async for update_data in subscribe_to_job_status(job_id):
    try:
        job_status_update = JobStatusUpdate(...)
        yield job_status_update
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        yield JobStatusUpdate(
            job_id=job_id,
            status="ERROR",
            error_message=f"Error processing status update: {str(e)}"
        )
```

This ensures the client doesn't just get a disconnection; it gets an explicit error message. The client can then decide to reconnect or show an error UI.

## Cancellation

When a client closes the WebSocket (e.g., navigates away), the async generator receives a `CancelledError`:

```python
try:
    async for update in subscribe_to_job_status(job_id):
        yield convert_to_graphql_type(update)
except asyncio.CancelledError:
    logger.info(f"Subscription cancelled for job {job_id}")
    raise
finally:
    # Cleanup
    logger.info(f"Subscription ended for job {job_id}")
```

The generator cleans up (close Redis connections, decrement counters) in the `finally` block. This is automatic—Strawberry handles the cancellation when the WebSocket closes.

## Full Resolver Example

Here's a complete, realistic resolver:

```python
@strawberry.subscription
async def subscribeToJobStatus(
    self,
    info: Info,
    job_id: str
) -> AsyncGenerator[JobStatusUpdate, None]:
    """Subscribe to real-time status updates for a specific job."""

    # Authorization phase
    try:
        current_user = await _get_current_user_from_ws_or_headers(info)
        if not current_user:
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                message="Authentication required"
            )
            return
    except Exception as e:
        logger.error(f"Auth error: {e}")
        yield JobStatusUpdate(
            job_id=job_id,
            status="ERROR",
            message="Authentication error"
        )
        return

    # Job verification phase
    try:
        with session_scope() as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                yield JobStatusUpdate(
                    job_id=job_id,
                    status="ERROR",
                    message="Job not found"
                )
                return

            if job.user_id != current_user.id or job.tenant_id != current_user.tenant_id:
                yield JobStatusUpdate(
                    job_id=job_id,
                    status="ERROR",
                    message="Access denied"
                )
                return
    except Exception as e:
        logger.error(f"DB error: {e}")
        yield JobStatusUpdate(
            job_id=job_id,
            status="ERROR",
            message="Database error"
        )
        return

    logger.info(f"Starting subscription for job {job_id} by user {current_user.user_id}")

    # Subscription phase
    try:
        redis_client = get_redis_client()

        async for update_data in subscribe_to_job_status(job_id):
            try:
                job_status_update = JobStatusUpdate(
                    job_id=update_data.get("job_id", job_id),
                    status=update_data.get("status", "UNKNOWN"),
                    timestamp=update_data.get("timestamp", ""),
                    message=update_data.get("message"),
                    progress_percentage=update_data.get("progress_percentage"),
                    current_step_description=update_data.get("current_step_description"),
                    error_message=update_data.get("error_message"),
                    additional_data=update_data.get("additional_data")
                )

                yield job_status_update

                # Exit on terminal state
                if update_data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                    logger.info(f"Job {job_id} terminal: {update_data.get('status')}")
                    break

            except Exception as e:
                logger.error(f"Update processing error: {e}")
                yield JobStatusUpdate(
                    job_id=job_id,
                    status="ERROR",
                    error_message=str(e)
                )

    except asyncio.CancelledError:
        logger.info(f"Subscription cancelled for {job_id}")
        raise
    except Exception as e:
        logger.error(f"Subscription error: {e}")
        yield JobStatusUpdate(
            job_id=job_id,
            status="ERROR",
            error_message=f"Subscription failed: {str(e)}"
        )
    finally:
        logger.info(f"Subscription cleanup for {job_id}")
```

## Key Takeaways

- **Async generators** are the pattern: `yield` sends updates to the client
- **Authorization early**: Check permissions before subscribing to Redis
- **Terminal states close gracefully**: Break the loop when the job is done
- **Rate limiting**: Protect against bursty jobs with sliding windows
- **Connection limits**: Prevent resource exhaustion from many connections
- **Error handling**: Emit error updates instead of silently disconnecting
- **Cancellation clean**: Use `finally` blocks to ensure cleanup
