# Subscriptions: Real-Time Updates

## The Subscription Model

GraphQL subscriptions enable servers to push updates to clients over a persistent connection. Unlike queries (request-response) and mutations (request-response with side effects), subscriptions are bidirectional: after the client sends a subscription request, the server actively sends updates whenever data changes.

In Etherion, subscriptions are the foundation for real-time job tracking. When a user submits a goal via `executeGoal`, the job begins running asynchronously. The user doesn't want to poll for updates; they want to see progress in real-time. Subscriptions deliver that.

## The WebSocket Upgrade Process

Subscriptions use WebSocket, a protocol that maintains a persistent TCP connection. Here's how it works:

**1. Client Initiates Subscription**

The GraphQL client (often Apollo Client on the frontend) opens a WebSocket connection to `/graphql`:

```javascript
// Frontend code
const socket = new WebSocket('wss://api.example.com/graphql');
// Send GraphQL handshake
socket.send(JSON.stringify({
  type: 'connection_init',
  payload: {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  }
}));

// Send subscription
socket.send(JSON.stringify({
  type: 'start',
  id: '1',
  payload: {
    query: `
      subscription {
        subscribeToJobStatus(job_id: "job-123") {
          job_id
          status
          timestamp
          message
        }
      }
    `
  }
}));
```

**2. FastAPI Receives Upgrade**

The request arrives at our FastAPI app. The GraphQL router detects it's a WebSocket upgrade (based on headers) and upgrades the HTTP connection to WebSocket:

```python
# In FastAPI/Starlette, this happens in the GraphQL router automatically
graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/graphql")
```

**3. Context Getter Builds Auth Context**

The `get_context` function runs:

```python
async def get_context(connection: HTTPConnection, connection_params: Optional[dict] = None):
    """Get GraphQL context for both HTTP and WebSocket connections."""
    # Extract auth from connection_params (sent by client in connection_init)
    connection_params = connection_params or {}
    headers = connection_params.get("headers") or {}

    # Resolve user from Authorization header
    auth_value = headers.get("Authorization")
    current_user, tenant_id = await resolve_current_user_from_headers(
        {"Authorization": auth_value}
    )

    connection.state.auth_context = {
        "current_user": current_user,
        "tenant_id": tenant_id,
    }

    return {
        "request": connection,
        "tenant_id": tenant_id,
        "connection_params": connection_params,
    }
```

This extracts the JWT from the WebSocket handshake, validates it, and attaches the authenticated user to the connection. From this point on, the WebSocket connection is authenticated.

## Implementing a Subscription

Here's the `subscribeToJobStatus` subscription from `subscriptions.py`:

```python
@strawberry.subscription
async def subscribeToJobStatus(
    self,
    info: Info,
    job_id: str
) -> AsyncGenerator[JobStatusUpdate, None]:
    """
    Subscribe to real-time status updates for a specific job.

    Yields:
        JobStatusUpdate: Status changes as the job executes
    """
    # Get authenticated user from context
    try:
        current_user = await _get_current_user_from_ws_or_headers(info)
        if not current_user:
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                message="Authentication required",
                error_message="User must be authenticated",
            )
            return
    except Exception as e:
        logger.error(f"Auth error: {e}")
        yield JobStatusUpdate(
            job_id=job_id,
            status="ERROR",
            message="Authentication error",
        )
        return

    # Verify job exists and user has access (security check)
    try:
        with session_scope() as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                yield JobStatusUpdate(
                    job_id=job_id,
                    status="ERROR",
                    message="Job not found",
                )
                return

            # Critical: check user owns this job (user-level isolation)
            if job.user_id != current_user.id or job.tenant_id != current_user.tenant_id:
                yield JobStatusUpdate(
                    job_id=job_id,
                    status="ERROR",
                    message="Access denied",
                )
                return
    except Exception as e:
        logger.error(f"DB error: {e}")
        yield JobStatusUpdate(job_id=job_id, status="ERROR")
        return

    logger.info(f"Starting subscription for job {job_id}")

    try:
        # Subscribe to Redis channel for this job
        redis_client = get_redis_client()

        # subscribe_to_job_status is an async generator from Redis
        async for update_data in subscribe_to_job_status(job_id):
            try:
                # Convert Redis message to GraphQL type
                job_status_update = JobStatusUpdate(
                    job_id=update_data.get("job_id", job_id),
                    status=update_data.get("status"),
                    timestamp=update_data.get("timestamp"),
                    message=update_data.get("message"),
                    progress_percentage=update_data.get("progress_percentage"),
                    error_message=update_data.get("error_message"),
                )

                yield job_status_update

                # Exit when job reaches terminal state
                if update_data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                    logger.info(f"Job {job_id} finished")
                    break

            except Exception as e:
                logger.error(f"Error processing update: {e}")
                yield JobStatusUpdate(
                    job_id=job_id,
                    status="ERROR",
                    message="Processing error",
                )

    except asyncio.CancelledError:
        logger.info(f"Subscription cancelled for job {job_id}")
        raise
    except Exception as e:
        logger.error(f"Subscription error: {e}")
```

**Key points**:

1. **AsyncGenerator Return Type**: Subscriptions return `AsyncGenerator[T, None]`, meaning they yield values over time.

2. **Authentication Check**: Before subscribing, we verify the user is authenticated and owns the job. This prevents users from spying on other users' jobs.

3. **Redis Pub/Sub**: We subscribe to a Redis channel specific to this job (`f"job_status:{job_id}"`). The helper `subscribe_to_job_status` wraps Redis pub/sub.

4. **Yield Updates**: Each time a message arrives on the Redis channel, we convert it to the GraphQL type and yield it.

5. **Terminal State Exit**: When the job reaches a terminal state (COMPLETED, FAILED, CANCELLED), we break out of the loop. The subscription closes, and the WebSocket frame is sent to the client.

## The Redis Pub/Sub Pipeline

How do status updates get published to Redis in the first place? When the background orchestration task runs, it periodically publishes updates:

```python
# In orchestrate_goal_task (orchestrator service)
async def orchestrate_goal_task(job_id, goal_description, user_id, tenant_id):
    # ... execute steps ...

    # After each step completes, publish update
    await publish_job_status(job_id, {
        "status": "RUNNING",
        "message": f"Executing step: {step_name}",
        "progress_percentage": 45,
        "current_step_description": step_name,
        "timestamp": datetime.utcnow().isoformat(),
    })

    # ... more steps ...

    # When complete
    await publish_job_status(job_id, {
        "status": "COMPLETED",
        "message": "Job finished successfully",
        "timestamp": datetime.utcnow().isoformat(),
    })
```

The `publish_job_status` function (in `src/core/redis.py`) publishes a message to the Redis channel:

```python
async def publish_job_status(job_id: str, data: dict):
    """Publish job status update to Redis pub/sub."""
    redis = get_redis_client()
    channel = f"job_status:{job_id}"
    await redis.publish(channel, json.dumps(data))
```

**Flow**:

1. Orchestration task runs (async background process)
2. Task completes a step and calls `publish_job_status`
3. Message is published to Redis channel `job_status:job-123`
4. Subscription resolver (listening on that channel) receives the message
5. Resolver converts message to GraphQL type and yields it
6. Strawberry serializes the update and sends it to the WebSocket client
7. Client receives the update and updates the UI

This entire flow happens in real-time, with latency measured in milliseconds.

## Handling Disconnections

If the WebSocket connection drops, the subscription is automatically cancelled. When `asyncio.CancelledError` is raised, we log it and exit gracefully. The client can reconnect and resume (though there's no built-in resume mechanism; the client would need to subscribe again from the current job status).

If the subscription resolver crashes unexpectedly, we catch the exception, yield an error update, and close the subscription.

## Scaling Subscriptions

Redis pub/sub works across a single Redis instance. If Etherion is deployed on multiple servers, each server has its own Redis client, and they all publish to the same Redis instance. This means subscriptions work seamlessly whether the orchestration task runs on server A and the subscription resolver runs on server B—Redis bridges them.

For very high scale (millions of concurrent subscriptions), Etherion could migrate to Redis Streams or a dedicated pub/sub service. But for now, Redis pub/sub is simple and effective.

## Client-Side Implementation (Frontend)

On the frontend (React, Vue, etc.), clients use Apollo Client to handle subscriptions:

```javascript
import { useSubscription, gql } from '@apollo/client';

const SUBSCRIPTION = gql`
  subscription SubscribeToJobStatus($jobId: String!) {
    subscribeToJobStatus(job_id: $jobId) {
      job_id
      status
      timestamp
      message
      progress_percentage
      error_message
    }
  }
`;

function JobDetail({ jobId }) {
  const { data, loading, error } = useSubscription(SUBSCRIPTION, {
    variables: { jobId },
  });

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  const { subscribeToJobStatus } = data;
  return (
    <div>
      <p>Status: {subscribeToJobStatus.status}</p>
      <p>Progress: {subscribeToJobStatus.progress_percentage}%</p>
      <p>{subscribeToJobStatus.message}</p>
    </div>
  );
}
```

Apollo Client automatically handles WebSocket connection management, subscription lifecycle, and message handling. When the component unmounts, Apollo unsubscribes, and the WebSocket frame is sent to the server to clean up.

## Other Subscriptions

Etherion has additional subscriptions:

**`subscribeToExecutionTrace`**: Yields step-by-step execution trace events (tool invoked, LLM response, etc.) as the job runs. Useful for debugging and showing detailed logs.

**`subscribeToUIEvents`**: Broadcasts events like "team member joined" or "permissions updated". Used to keep UIs in sync when multiple users are collaborating.

These follow the same pattern: authenticate, verify permissions, subscribe to Redis channel, yield updates, handle disconnection.

## Error Recovery

If the Redis channel is temporarily unavailable or the orchestration task crashes, the subscription should gracefully handle errors:

- If orchestration crashes, it should update the job status to FAILED and publish that to Redis
- If Redis is down, the subscription resolver should yield an error and close the connection
- Clients should display an error message and offer to retry

Currently, some of these error paths are best-effort. For critical applications, you'd want to add circuit breakers and retry logic.

## Next Steps

- **Middleware** (`middleware.md`): Understand how requests are authenticated and logged.
- **Mutations** (`mutations.md`): Learn how mutations trigger subscriptions via Redis publish.
- **Schema Structure** (`schema-structure.md`): Review how subscription types are defined.
