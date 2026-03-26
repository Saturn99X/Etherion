# WebSocket Lifecycle in Etherion

## The Full Journey

When a user opens a job details page in the Etherion UI, their browser opens a WebSocket connection to the GraphQL server and sends a subscription request. Here's the complete lifecycle from connection to close.

## HTTP Upgrade → WebSocket

```
Client (Browser)                         Server (Etherion)
        |                                        |
        | HTTP GET /graphql                     |
        | (with Upgrade: websocket header)      |
        |--------------------------------------->|
        |                                        |
        |                        HTTP 101 Switching Protocols
        |<---------------------------------------|
        |                                        |
        | WebSocket connection established      |
        | (upgrade complete, now bidirectional) |
```

The browser initiates with an HTTP GET request that includes the `Upgrade: websocket` header. The server responds with HTTP 101, and the connection is upgraded from HTTP to WebSocket. From this point forward, both sides can send messages at any time without waiting for a request/response cycle.

## GraphQL-WS Handshake

Once the WebSocket is established, the client sends a GraphQL connection init message and optional authentication headers:

```
Client                                   Server
   |                                        |
   | GQL_CONNECTION_INIT                   |
   | { type: "connection_init",            |
   |   payload: {                           |
   |     headers: {                         |
   |       Authorization: "Bearer <token>" |
   |     }                                  |
   |   }                                    |
   | }                                      |
   |--------------------------------------->|
   |                                        |
   |            Server extracts auth header,
   |            validates JWT token,
   |            extracts user & tenant ID
   |
   |                          GQL_CONNECTION_ACK
   |                          { type: "connection_ack" }
   |<---------------------------------------|
   |                                        |
```

The server receives the `connection_init` message and extracts the authorization header. It validates the JWT token, resolves the user and tenant from the token, and stores this context on the connection. The server responds with `connection_ack` to confirm the handshake succeeded.

If the token is invalid or missing, the server can send `connection_error` and close the WebSocket.

## Subscription Start

After the handshake, the client sends a subscription message:

```
Client                                   Server
   |                                        |
   | GQL_START                              |
   | { type: "start",                       |
   |   id: "1",                             |
   |   payload: {                           |
   |     query: "subscription {             |
   |       subscribeToJobStatus(            |
   |         job_id: \"xyz\"                |
   |       ) { job_id status ... }          |
   |     }"                                 |
   |   }                                    |
   | }                                      |
   |--------------------------------------->|
   |                                        |
   |            Server:
   |            1. Parse and validate query
   |            2. Invoke subscription resolver
   |            3. Resolver checks auth
   |            4. Resolver checks job ownership
   |            5. Resolver subscribes to Redis
   |            6. Background task starts
   |               listening for messages
   |
```

The client sends a GraphQL subscription query with an ID (e.g., "1"). The server:

1. Parses the query
2. Validates the GraphQL schema
3. Invokes the subscription resolver (e.g., `subscribeToJobStatus`)
4. The resolver performs authorization checks
5. If auth succeeds, the resolver subscribes to Redis
6. A background async task starts listening for messages on that channel

## Steady State: Updates Flow

```
Worker (Celery)      Redis       Server       Client (Browser)
      |               |             |             |
      | PUBLISH       |             |             |
      | (status:      |             |             |
      |  RUNNING...)  |             |             |
      |---->|         |             |             |
      |     | Forward to all subs  |             |
      |     |----------->|         |             |
      |     |            |         |             |
      |     |            | Convert to GraphQL   |
      |     |            | and yield            |
      |     |            |--GQL_DATA with msg-->|
      |     |            |             |         |
      |     |            |             | Browser receives
      |     |            |             | React re-renders
      |     |            |             | Progress bar updates
      |     |            |             |
      | (client subscribes to same job)         |
      |                                 | Another client joins
      |                   Each client  |
      |                   gets same msg from
      |                   Redis broadcast
      |
      | PUBLISH        |             |
      | (progress:     |             |
      |  50%)          |             |
      |---->|          |             |
      |     |--------->|             |
      |     |          |--GQL_DATA-->|
      |     |          |--GQL_DATA-->|  (both clients receive)
      |     |          |--GQL_DATA-->|
```

When the worker publishes to `job_status_xyz`, Redis broadcasts the message to all subscribers. The server's background task receives it, converts it to a GraphQL type, and yields it to the client via `GQL_DATA`.

Key point: If multiple clients are subscribed to the same job, **they all receive the same update from one Redis message**. Redis's broadcast model is incredibly efficient here.

## Client Receives Update

```
Client (Browser)
   |
   | GQL_DATA
   | { type: "data",
   |   id: "1",
   |   payload: {
   |     data: {
   |       subscribeToJobStatus: {
   |         job_id: "xyz",
   |         status: "RUNNING",
   |         progress_percentage: 45,
   |         current_step_description: "..."
   |       }
   |     }
   |   }
   | }
   |<-----
   |
   | React updates state:
   | setJobStatus({ status: "RUNNING", ... })
   |
   | Component re-renders:
   | <ProgressBar value={45} />
   | <p>{current_step_description}</p>
```

The client receives the update, updates its local state, and re-renders the component. The user sees the progress bar move and the step description change in real-time.

## Terminal State: Subscription Closes

```
Worker (Celery)      Redis       Server       Client (Browser)
      |               |             |             |
      | PUBLISH       |             |             |
      | (status:      |             |             |
      |  COMPLETED)   |             |             |
      |---->|         |             |             |
      |     |--------->|             |             |
      |     |          |--GQL_DATA-->|             |
      |     |          |  (final msg)|             |
      |     |          |             |             |
      |     |          | Resolver checks if terminal
      |     |          | status in [COMPLETED, FAILED, CANCELLED]
      |     |          | Yes! Break the loop
      |     |          | Generator ends
      |     |          |             |             |
      |     |          |--GQL_COMPLETE--|---------->|
      |     |          |   { type: "complete",     |
      |     |          |     id: "1" }             |
      |     |          |             |             |
      |     |          |             |  Client knows subscription is done
      |     |          |             |  Closes the subscription ID "1"
      |     |          |             |  Can still receive on other IDs
```

When the resolver detects a terminal status (COMPLETED, FAILED, CANCELLED), it breaks the loop and the async generator ends. Strawberry sends a `GQL_COMPLETE` message to inform the client the subscription is finished. The client knows not to expect more updates on this subscription ID.

The WebSocket connection itself **stays open**. The client could open another subscription on the same connection (e.g., to watch another job), or close the connection if this was the only subscription.

## Client Disconnect (Mid-Job)

What if the user closes the tab or their network drops while the job is still running?

```
Client (Browser)                     Server
   |                                   |
   | [WebSocket connection open]       |
   |                                   |
   | User closes tab                   |
   | OR network drops                  |
   |                                   |
   | TCP FIN (connection closes)       |
   |---------- X -------->|             |
   |                      | Server detects disconnect
   |                      | Resolver's finally block runs
   |                      | Redis connection closed
   |                      | Connection limit counter decremented
   |                      |
   |                      | Redis continues publishing job updates
   |                      | (just no one listening anymore)
```

When the WebSocket closes (either gracefully via client disconnect or abruptly via network failure), the server detects it and runs the resolver's `finally` block:

```python
finally:
    try:
        await redis.decr(conn_key)  # Decrement connection count
    except Exception:
        pass
    logger.info(f"Subscription ended for job {job_id}")
```

The Redis subscription is cleaned up, connection limits are updated, and any resources are freed. The job continues running on the worker—it doesn't depend on the client being connected.

## Client Reconnects

If the client was watching a long-running job and their network dropped, they can reconnect:

```
Client (Browser)                     Server
   |                                   |
   | [WebSocket disconnected]          |
   |                                   | Job is still RUNNING, publishing updates
   |                                   | (no one listening to this job atm)
   |                                   |
   | User clicks "Reconnect" button    |
   | (or auto-reconnect logic fires)   |
   |                                   |
   | WebSocket handshake               |
   | (same as before)                  |
   |-----Connection init & auth------->|
   |<-----Connection ack-------|        |
   |                                   |
   | Subscription (same job_id)        |
   |-----GQL_START (job_id: "xyz")---->|
   |                                   |
   |                   Resolver subscribes to Redis
   |                   Catches next publish
   |                   (may have missed updates while down,
   |                    but gets current + future updates)
   |
   |<-----GQL_DATA (current status)-----|
```

The client reconnects, re-authenticates, and re-subscribes to the job. It gets the current status and continues receiving updates. Some updates that occurred while the client was disconnected are lost (because Redis doesn't persist), but the client is now in sync with the current state.

If the job has already completed by the time the client reconnects, it would receive the terminal status immediately.

## Error Scenario: Network Hiccup

```
Client              Server          Worker
   |                  |                |
   | [Subscription OK] |                |
   | [Receiving updates] |              |
   |                  |                |
   | TCP packet loss  | TCP retransmit |
   | ~500ms latency   |                |
   |                  |                |
   | [Waiting...]     | [Buffering]    |
   | [Client times out after 60s]      |
   |                  |                |
   | Client closes and reconnects      |
   |-----New handshake----->|           |
   |<-----Ack----------|    |           |
   |-----New subscription-->|           |
   |                  |    | Still publishing
   |<-----Updates-----|    |
```

If the network is slow or lossy, the client might experience latency but not necessarily disconnect. Strawberry has configurable timeouts (default 60 seconds). If no messages are received in 60 seconds, the client times out and reconnects.

The resolver's `finally` block cleans up the old subscription, and a new one starts. The job continues running regardless; the worker doesn't know about network issues on the client side.

## Server-Side Cleanup

When the WebSocket connection closes (whether by client action or server action), the server:

1. **Cancels the async generator** → `asyncio.CancelledError` is raised in the resolver
2. **Runs finally blocks** → Redis unsubscribes, counters decrement, logging happens
3. **Frees resources** → Memory from the generator is released

Here's what the resolver cleanup looks like:

```python
try:
    redis_client = get_redis_client()
    conn_key = f"wsconn:exec:{ip}"

    try:
        active = await redis.incr(conn_key)
        if active == 1:
            await redis.expire(conn_key, 3600)
        if active > conn_limit:
            raise Exception("Too many connections")

        async for update in subscribe_to_job_status(job_id):
            yield convert_to_graphql_type(update)

    finally:
        try:
            await redis.decr(conn_key)  # Decrement counter
        except Exception:
            pass

except asyncio.CancelledError:
    logger.info(f"Subscription cancelled for {job_id}")
    raise
except Exception as e:
    logger.error(f"Subscription error: {e}")

finally:
    logger.info(f"Subscription cleanup for {job_id}")
```

The nested `finally` blocks ensure cleanup happens even if an exception occurs.

## Graceful Close by Server

The server can also close a subscription proactively if needed:

```python
if is_job_cancelled(job_id):
    yield JobStatusUpdate(
        job_id=job_id,
        status="CANCELLED",
        message="Job was cancelled by the system"
    )
    return  # Generator ends, sends GQL_COMPLETE
```

Returning from the generator or breaking the loop both cause the subscription to close gracefully. The client receives `GQL_COMPLETE` and knows the subscription is done.

## Key Moments in the Lifecycle

| Stage | Action | Who | What Happens |
|-------|--------|-----|--------------|
| 1. Connect | HTTP Upgrade | Browser + Server | WebSocket connection established |
| 2. Handshake | GQL_CONNECTION_INIT + auth | Browser + Server | User authenticated, context stored |
| 3. Subscribe | GQL_START with query | Browser + Server | Resolver invoked, Redis subscription starts |
| 4. Updates | GQL_DATA with message | Server → Browser | Updates flow in real-time |
| 5. Terminal | GQL_DATA (final) | Server → Browser | Job reaches COMPLETED/FAILED/CANCELLED |
| 6. Close | GQL_COMPLETE | Server → Browser | Resolver returns, subscription ends |
| 7. Cleanup | finally blocks | Server | Resources freed, counters decremented |

## Timeouts and Keepalive

To prevent the WebSocket from being closed by proxies or load balancers, both client and server send periodic "ping" frames:

```
Client              Server
   |                  |
   | PING              |
   |----------------->|
   |                  |
   |            PONG  |
   |<-----------------|
   |                  |
   | (repeat every 30s)|
   |                  |
```

These are WebSocket-level ping/pong frames, not GraphQL messages. They keep the connection alive even if no data is flowing. The interval is typically 30 seconds, so a connection can be idle but still valid.

## Summary

The WebSocket lifecycle in Etherion is:

1. **HTTP Upgrade** → Establish bidirectional channel
2. **GraphQL Handshake** → Authenticate user
3. **Subscribe** → Start listening to Redis
4. **Steady State** → Receive updates as they're published
5. **Terminal State** → Job completes, subscription closes gracefully
6. **Cleanup** → Resources freed, connection can close or reuse

This design ensures real-time updates at scale, with resilience to network issues, and efficient resource management on both client and server.
