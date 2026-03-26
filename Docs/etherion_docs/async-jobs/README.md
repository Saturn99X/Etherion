# Async Jobs: Why Etherion Runs Agent Tasks Asynchronously

## The Synchronous Problem

Imagine a user triggers an agent to research competitive pricing across ten vendors, synthesize findings, and draft a recommendation document. The execution involves:

- Making 10 API calls to external services (2-5 seconds each)
- Parsing structured data from each response
- Running embeddings for semantic analysis
- Generating a final report via LLM

If this all happened synchronously inside a GraphQL mutation, the HTTP request would block for 30-60 seconds. The client waits. The API server holds a connection and database transaction open. If two users trigger this simultaneously, you're burning through connection pools, memory, and CPU. And if the network hiccups after 50 seconds, the entire job is lost—no retry, no recovery.

Etherion solves this with **asynchronous job processing**: the mutation returns immediately with a job ID, work happens in background worker processes, and clients subscribe to job status updates via GraphQL subscriptions.

## Why Celery + Redis

Etherion uses **Celery** (a distributed task queue) with **Redis** as the broker. Here's the architecture decision:

**Celery** decouples task enqueuing from execution. When a GraphQL mutation fires, it pushes a message onto a Redis queue and returns instantly. Worker processes (running in separate containers or processes) pull tasks from that queue and execute them independently. If a worker crashes mid-task, Redis retains the message, and another worker picks it up on retry.

**Redis as broker** provides:
- **Durability**: Messages persist if workers are temporarily unavailable (configurable expiration)
- **Low latency**: In-memory queue operations complete in microseconds
- **Atomicity**: Task acknowledgment is strict—Celery won't remove a task from Redis until the worker signals success
- **Multiple queues**: Different queues (e.g., `worker-agents` for agent tasks, `worker-artifacts` for heavy I/O) allow prioritization and workload isolation

Alternative brokers like RabbitMQ or Kafka would work, but Redis is simpler to operate (single-process, minimal config) and sufficient for Etherion's scale.

## The Job Lifecycle

1. **Enqueue** (API → Redis): Mutation calls `execute_goal_task.apply_async()`, which sends a serialized task message to Redis queue `worker-agents`
2. **Dequeue** (Worker reads): A worker listening on that queue pops the message, deserializes it, and marks it as processing in Redis
3. **Execute**: The task runs—agent loops, tool calls, embedding operations—logging each step
4. **Publish result**: On completion or error, the task saves result data to the Job record in the database and publishes a Redis event that subscriptions listen to
5. **Client learns**: GraphQL subscriptions receive the status change and notify the client in real-time

## Retry and Failure

Celery is configured with **exponential backoff**: if a task fails (throws an exception), it retries automatically with a delay (1 minute → 2 minutes → 4 minutes, up to 3 times). If all retries fail, the task goes to a dead-letter queue conceptually, but Etherion stores the error in the Job record itself.

Critical: **Idempotency**. Tasks must be safe to retry. If an agent task creates a document, the retry should check if that document already exists before creating a duplicate. This is why output_data and trace_data_uri exist—they let tasks detect partial completion.

## Monitoring and Observability

Celery publishes events for task lifecycle stages (prerun, postrun, failure). Etherion logs these with structured formatting so they appear in Cloud Logging. Workers report ready/shutdown state, and task signal handlers catch failures and log them with full tracebacks. Job records in the database become the source of truth for clients, allowing them to query historical job status without needing Celery's result backend (which is disabled in production to reduce Redis memory pressure).

## Why Not Publish-Subscribe Only?

You might ask: "Why not just stream updates from client to server and compute inline?" The answer is resilience. A subscription-only model loses work if the connection drops. Async job architecture keeps work **durable** in the queue even if clients disconnect, and allows work to be **queued up** before workers are ready. It also enables **backpressure**—if workers are busy, tasks sit safely in Redis waiting their turn, rather than overloading the API.
