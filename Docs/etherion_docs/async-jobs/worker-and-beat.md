# Worker and Beat: Two Daemon Processes

Etherion runs two separate Celery daemon processes:

1. **Worker**: Dequeues and executes on-demand tasks (agent jobs, ingestion, etc.)
2. **Beat**: Schedules periodic tasks at specified times (e.g., pricing reconciliation at midnight)

They are independent processes, though they share the same Celery app configuration.

## The Main Worker Process

The worker is started by the CLI command:

```bash
etherion worker --queues=worker-agents,worker-artifacts --concurrency=8
```

Or via Python directly (in `/etherion/cli/cmd_worker.py`):

```python
def run_worker(
    queues: str = "celery,worker-artifacts",
    concurrency: int = 4,
    loglevel: str = "info",
) -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_WORKER)
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    console.print(f"[bold]Starting Celery worker (queues={queues})[/bold]")
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "src.core.celery.celery_app",
        "worker",
        f"--loglevel={loglevel}",
        f"--concurrency={concurrency}",
        "-Q", queues,
        "--pool=threads",
    ]
    sys.exit(subprocess.call(cmd))
```

**-Q (queues)**: The worker listens to one or more named queues. In this case, both `worker-agents` and `worker-artifacts`. The worker won't listen to a queue unless explicitly specified—this allows horizontal scaling by running multiple workers, each on its own subset of queues.

**--concurrency**: Number of threads in the thread pool. Default 4 for development, typically 8-16 for production depending on machine resources. Each thread can execute one task concurrently.

**--pool=threads**: Use thread pool (GIL-friendly for I/O-bound work) instead of process pool.

### Worker Lifecycle

1. **Startup**: Worker imports all task modules (goal_orchestrator, tasks, pricing.reconciliation, etc.) and registers them with Celery
2. **Signal ready**: Worker fires `worker_ready` signal, which Etherion logs
3. **Poll loop**: Worker polls Redis queues every ~100ms for new messages
4. **Execute**: When a task is found, worker dequeues it, executes it (firing task_prerun/postrun signals), and acknowledges completion in Redis
5. **Graceful shutdown**: On SIGTERM, worker waits for in-flight tasks to complete (up to a timeout), then exits

### Scaling Worker Capacity

To handle more concurrent jobs, you can:

**Increase concurrency on a single machine**: Set `--concurrency=16` to run 16 threads. Thread count is limited by CPU cores and memory.

**Run multiple worker processes**: Start multiple workers on the same or different machines, all listening to the same Redis broker. Celery's broker automatically distributes tasks across workers.

**Segregate queues**: Run one worker set on `worker-agents` (agent execution) and another on `worker-artifacts` (I/O), so heavy I/O doesn't starve agent tasks.

## Beat: The Periodic Task Scheduler

Beat is a lightweight scheduler that enqueues tasks on a cron schedule. Start it with:

```bash
etherion worker beat
```

Or:

```python
def run_beat(loglevel: str = "info") -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_WORKER)
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    console.print("[bold]Starting Celery beat scheduler[/bold]")
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "src.core.celery.celery_app",
        "beat",
        f"--loglevel={loglevel}",
    ]
    sys.exit(subprocess.call(cmd))
```

Beat reads the `celery_app.conf.beat_schedule` dictionary and, at the specified times, calls `apply_async()` on the named tasks.

## Current Periodic Tasks

As of now, Etherion schedules one periodic task:

```python
# In /src/core/celery.py
celery_app.conf.beat_schedule = {
    "pricing-reconciliation-nightly": {
        "task": "src.services.pricing.reconciliation.run_reconciliation",
        "schedule": {
            "type": "crontab",
            "minute": 0,
            "hour": 0,
        },
    }
}
```

This runs the pricing reconciliation task at 00:00 UTC every day. The task queries all tenant usage and recomputes billing totals.

## Adding a New Periodic Task

To add a new periodic task, follow these steps:

**Step 1**: Define the task function with the `@celery_app.task` decorator:

```python
# In src/services/my_service.py
from src.core.celery import celery_app

@celery_app.task(name="my_service.cleanup_old_reports")
def cleanup_old_reports():
    """Delete reports older than 30 days."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=30)

    with get_session() as session:
        old_reports = session.query(Report).filter(
            Report.created_at < cutoff
        ).all()
        for report in old_reports:
            session.delete(report)
        session.commit()

    return {"deleted": len(old_reports)}
```

**Step 2**: Add the task to the beat schedule in `/src/core/celery.py`:

```python
celery_app.conf.beat_schedule = {
    "pricing-reconciliation-nightly": {
        "task": "src.services.pricing.reconciliation.run_reconciliation",
        "schedule": {
            "type": "crontab",
            "minute": 0,
            "hour": 0,
        },
    },
    "cleanup-old-reports-daily": {
        "task": "my_service.cleanup_old_reports",
        "schedule": {
            "type": "crontab",
            "minute": 30,
            "hour": 2,  # 02:30 UTC
        },
    }
}
```

**Step 3**: Import the module so Celery registers the task:

```python
# In /src/core/celery.py, add to the include list:
_celery_kwargs: Dict[str, Any] = {
    "broker": CELERY_BROKER_URL,
    "include": [
        "src.services.goal_orchestrator",
        "src.services.my_service",  # Add this
        # ... other modules
    ],
}
```

**Step 4**: Restart beat and check the logs to confirm the schedule is loaded:

```
beat: Scheduler: Ticking... (current time: 2026-03-26 14:30:00)
beat: Skipping 'cleanup-old-reports-daily' because it hasn't reached its scheduled time.
```

Beat runs in an event loop and wakes up once per minute to check schedules. At the specified time, it will enqueue the task.

## Monitoring Beat

Beat maintains a `celerybeat-schedule` file (by default in the current directory, or set via `--scheduler` flag). This file tracks when each task last executed. If beat crashes and restarts, it reads this file to avoid re-running a task that already executed.

In production, you might want to use a persistent scheduler:

```bash
celery -A src.core.celery.celery_app beat \
    --scheduler=django_celery_beat.schedulers:DatabaseScheduler
```

This stores the schedule in the database, so it survives beat restarts and allows dynamic schedule changes without restarting beat. Etherion currently uses the file-based scheduler for simplicity.

## Beat + Worker on Same Machine

In small deployments, beat and worker can run on the same machine but as separate processes. Beat enqueues tasks to Redis, and the local worker dequeues and executes them. In larger deployments, beat typically runs on a single "control" machine, and many workers run on compute machines.
