# Real-Time Updates in Etherion

## Why Real-Time Matters for an AI Agent Platform

When a user submits a job to Etherion—whether it's analyzing documents, running a workflow, or orchestrating multi-step agent tasks—they don't want to stare at a loading spinner for 30 seconds and then see a final result. They want to see what's happening *right now*. Is the agent processing step 1 of 5? Did it just call the Google Drive API? Is a tool invocation about to timeout?

This is where real-time updates become critical. An AI agent platform lives or dies on transparency. Users need to trust that their jobs are progressing, not stuck. Platform operators need to debug jobs as they run, catching hangs before they cascade into SLA violations. Dashboards need to show live job status across a tenant without refreshing the page every three seconds.

Etherion solves this with a clean architecture built on **Redis Pub/Sub** and **GraphQL subscriptions**. When a job changes state—moving from QUEUED → RUNNING → COMPLETED—that event flows through Redis channels. Clients subscribe via GraphQL over WebSocket, and updates stream to the browser in real-time, at scale, without polling.

## The Architecture at a Glance

Here's the flow:

1. **Worker publishes events** → Job starts running, publishes status updates to a Redis channel (e.g., `job_status_abc123`)
2. **Redis holds the message** → All subscribers to that channel receive it instantly
3. **GraphQL subscription receives it** → The resolver yields the update to the client
4. **Client gets the update** → React component re-renders with the new status, progress bar ticks, or logs appear

No database reads. No API polling. Just a push-based stream with Redis as the backbone.

## Key Concepts

### Redis Channels

Etherion uses a naming convention for channels to scope events:

- `job_status_{job_id}` — Job lifecycle updates (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED)
- `job_trace_{job_id}` — Execution trace events (step-by-step progress, tool invocations, memory usage)
- `ui_events_{tenant_id}` — Tenant-wide UI notifications (agent deployed, tenant settings changed)

This channel naming keeps subscriptions precise. A client watching job `xyz` only gets updates for job `xyz`, not all jobs.

### Subscription Lifecycle

When a user opens a job details page and subscribes to `subscribeToJobStatus(job_id: "abc123")`:

1. **Authorization** — WebSocket connection is verified; user must have permission to access the job
2. **Subscribe to Redis channel** — A background task starts listening to Redis for messages on `job_status_abc123`
3. **Yield to client** — Each message is converted to a GraphQL type and sent to the browser
4. **Terminal state reached** — When the job completes (COMPLETED, FAILED, CANCELLED), the subscription closes gracefully
5. **Client disconnects** — The subscription is cleaned up; Redis unsubscribes

Throughout this lifecycle, the GraphQL subscription is async and non-blocking. Multiple clients can subscribe to the same job simultaneously without interfering.

## Real-World Scenario

A tenant user kicks off a job to analyze 500 marketing emails, extract sentiment, and create Notion database entries. Here's what happens behind the scenes:

1. **t=0s** → Worker receives the job, publishes `{"status": "RUNNING", "step": "Parsing emails"}` to `job_status_job_xyz`
2. **Client subscription yields** → GraphQL resolver receives the message, converts it to `JobStatusUpdate`, yields it
3. **Browser receives** → React component updates the UI: "Parsing emails... 0%"
4. **t=3s** → Worker publishes `{"status": "RUNNING", "progress_percentage": 20, "current_step_description": "Extracting sentiment for batch 1"}`
5. **Browser updates again** → Progress bar moves to 20%, step description changes
6. **t=25s** → Worker hits a quota limit; publishes `{"status": "FAILED", "error_message": "Notion API rate limit exceeded"}`
7. **Client receives FAILED** → Subscription logic sees terminal state, closes the stream gracefully
8. **User sees the error** → React knows the job is done; error banner appears

All of this happens with zero polling, zero heartbeats, zero wasted requests. The user sees real-time feedback.

## Multi-Client Resilience

One powerful property of this architecture: it scales elegantly. If 50 users on the same tenant are all watching the same job (via a shared dashboard), they all subscribe to the same Redis channel. Redis broadcasts one message to all 50 subscribers. No database load. No bandwidth waste. The subscription resolver just yields the message to each client independently.

If one client's WebSocket connection drops mid-stream, the others keep receiving updates. That client reconnects, re-authorizes, and gets added back to the Redis subscriber list—all within 100ms.

## Error Handling and Backpressure

The architecture includes rate limiting to prevent a bursty job (with thousands of trace events per second) from overwhelming the client. Each subscription resolver has a per-IP sliding window. If a client's connection is slow, events are dropped gracefully, not queued indefinitely, keeping memory usage bounded.

When a job publishes too many events in a burst, the system throttles at the client level. The user sees a consistent stream of meaningful updates, not a firehose.

## Next Steps

- **[redis-pubsub.md](redis-pubsub.md)** — Deep dive into how Redis Pub/Sub works and Etherion's channel design
- **[graphql-subscriptions.md](graphql-subscriptions.md)** — How GraphQL subscriptions work in Strawberry and the resolver pattern
- **[websocket-lifecycle.md](websocket-lifecycle.md)** — The full WebSocket connection lifecycle with ASCII diagrams
