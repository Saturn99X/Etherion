# Celery Configuration: Broker, Backend, and Concurrency

## The Celery App Object

Celery is initialized in `/src/core/celery.py` as a global application instance:

```python
from celery import Celery
from kombu import Queue

celery_app = Celery(
    "etherion_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_BACKEND_FOR_APP,
    include=[
        "src.services.goal_orchestrator",
        "src.services.orchestrator_security",
        "src.core.tasks",
        # ... other task modules
    ],
)
```

The `include` list tells Celery which modules define tasks (using the `@celery_app.task` decorator). When a worker starts, it imports these modules so Celery knows about all available tasks.

The `broker` and `backend` parameters point to Redis. The distinction is important:

- **Broker** (`CELERY_BROKER_URL`): The message queue where tasks are enqueued and dequeued
- **Backend** (`CELERY_BACKEND_FOR_APP`): Where Celery stores task results (status, return value, exceptions)

## Redis URLs and Production Behavior

Etherion reads the Redis URL from environment variables, in order of precedence:

```python
REDIS_URL = os.getenv("ETHERION_REDIS_URL") or os.getenv("REDIS_URL")
if not REDIS_URL:
    if os.getenv("ENVIRONMENT") == "production":
        raise ValueError("REDIS_URL environment variable is required")
    REDIS_URL = "redis://localhost:6379/0"  # Dev default
```

In development, it defaults to `redis://localhost:6379/0`. In production, the URL is required and may point to a managed Redis instance with TLS support (rediss:// scheme).

## Result Backend: Disabled in Production

Here's a critical decision: **Etherion disables Celery's result backend in production** by setting it to `"disabled://"`:

```python
_force_result_backend = (os.getenv("CELERY_FORCE_RESULT_BACKEND") or "").lower() == "true"
_inmemory_transport = CELERY_BROKER_URL.startswith("memory://")
_effective_backend = _env_result_backend

if not _force_result_backend and not _inmemory_transport:
    _effective_backend = "disabled://"
    CELERY_RESULT_BACKEND = None
```

**Why?** Celery's result backend in Redis creates extra traffic: every task completion writes its result to Redis, and the result expires after 1 hour. For a high-throughput agent platform processing hundreds of jobs, this is unnecessary memory churn. Instead, Etherion stores the canonical job status and output in the **database** (the Job model), which is the source of truth anyway. The result backend is only enabled in tests (with `cache+memory://` for in-process execution).

## Task Routing: Multiple Queues

Etherion defines five queues, but most tasks route to two:

```python
task_queues=(
    Queue("worker-agents", routing_key="worker-agents"),
    Queue("worker-artifacts", routing_key="worker-artifacts"),
    Queue("etherion_tasks", routing_key="etherion_tasks"),
    Queue("high_priority", routing_key="high_priority"),
    Queue("low_priority", routing_key="low_priority"),
)

task_default_queue="worker-agents"

task_routes={
    "core.admin_ingest_gcs_uri": {"queue": "worker-artifacts"},
    "core.cleanup_completed_jobs": {"queue": "worker-artifacts"},
    "core.monitor_job_health": {"queue": "worker-artifacts"},
    "goal_orchestrator.execute_goal": {"queue": "worker-agents"},
    # ... other routes
}
```

**worker-agents** (default): Handles agent execution, orchestration, and security tasks. These are CPU-bound and latency-sensitive.

**worker-artifacts**: Handles heavy I/O (GCS downloads, document ingestion, archival) and maintenance tasks (cleanup, health checks). These are I/O-bound and can tolerate delays.

By isolating workload types into separate queues, you can run multiple workers on separate machines, each optimized for its queue. An ingestion task won't block an agent task if they're on different workers.

## Concurrency Model: Thread Pool

Etherion uses a **thread pool** concurrency model:

```python
worker_args = [
    "worker",
    "--pool=threads",
    f"--concurrency={concurrency}",  # Default 8, from env var
    "--prefetch-multiplier=1",
    "--max-tasks-per-child=1000",
]
```

**Why threads, not processes?** Agent tasks involve heavy I/O (API calls, database queries, embedding calls). Threads are ideal because they release the GIL during I/O operations, allowing other threads to run. A process pool would waste memory—each process is ~50MB+ versus threads at ~10MB+.

**Prefetch = 1** is crucial: each worker reserves only one task at a time from the broker. This prevents a worker from grabbing ten tasks and then crashing before completing them all. With `prefetch=1`, if a worker takes a task and dies, that task returns to the queue within seconds.

**Max tasks per child = 1000**: After processing 1000 tasks, a worker thread pool recycles itself. This bounds memory leaks in long-running processes—if a library has a memory leak, the pool resets before it becomes critical.

## Task Execution Settings

```python
task_acks_late=True,
task_reject_on_worker_shutdown=True,
```

**acks_late**: Workers acknowledge task completion *after* execution, not before. If the worker crashes during execution, the broker redelivers the task.

**reject_on_shutdown**: If a worker receives a shutdown signal and is still executing a task, it rejects the task back to the queue instead of losing it.

These settings ensure **at-least-once delivery**: a task is guaranteed to be attempted, but may be executed multiple times if workers fail. This is why idempotency is mandatory.

## Retry Configuration

```python
task_default_retry_delay=60,      # 1 minute first retry
task_max_retry_delay=3600,        # 1 hour max backoff
task_default_max_retries=3,
task_retry_backoff=True,
task_retry_backoff_max=3600,
task_retry_jitter=True,
```

On failure, a task retries with exponential backoff (1 min → 2 min → 4 min, jittered to avoid thundering herd). After 3 retries over ~7 minutes, the task is marked as failed and the error is stored in the Job record.

## Serialization and Monitoring

```python
task_serializer="json",
accept_content=["json"],
task_send_sent_event=True,
task_track_started=True,
timezone="UTC",
enable_utc=True,
```

All task arguments and results are serialized as JSON—safe, language-agnostic, debuggable. Celery sends lifecycle events (sent, started, succeeded, failed) which worker logging handlers consume to track progress. Everything is in UTC to avoid timezone bugs.
