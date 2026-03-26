# Error Handling: Retries, Dead Letters, and Client Notification

When a task fails, Etherion has multiple layers of error recovery and notification to ensure jobs don't silently disappear.

## Task Failure and Retry

When a task raises an unhandled exception, Celery catches it. If the task is configured to retry, Celery automatically requeues the task after a delay:

```python
# Example task with retry configuration
from src.core.celery import celery_app

@celery_app.task(
    bind=True,
    name="core.update_job_status",
    autoretry_for=(Exception,),  # Retry on any Exception
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def update_job_status_task(self, job_id: str, status: str, error_message=None):
    try:
        with tenant_scoped_session(tenant_id) as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            job.update_status(JobStatus(status))
            if error_message:
                job.error_message = error_message
            session.commit()

    except Exception as exc:
        # This raises self.retry(), which requeues the task
        logger.error(f"Failed to update job status: {exc}")
        raise self.retry(exc=exc, countdown=60, max_retries=3)
```

When `self.retry()` is called (or `autoretry_for` triggers), Celery:

1. Increments the retry counter
2. Computes a delay using exponential backoff with jitter
3. Requeues the task message back to Redis with a `countdown` (ETA)
4. The message sits in Redis until the ETA, then becomes available for dequeue

## Exponential Backoff

Celery's default backoff configuration in Etherion:

```python
# In /src/core/celery.py
task_default_retry_delay=60,      # 1 minute first retry
task_max_retry_delay=3600,        # 1 hour max backoff
task_default_max_retries=3,
task_retry_backoff=True,
task_retry_backoff_max=3600,
task_retry_jitter=True,
```

**How it works**: After the first failure, retry in 60 seconds. After the second failure, retry in 2x to 4x that time (depending on backoff multiplier, typically 2). Jitter adds randomness to the delay to prevent thundering herd (many tasks retrying at exactly the same time).

**Timeline example**:
- Task fails at T=0s → Retry at T=60s (60s delay)
- Task fails again at T=70s → Retry at T=190s (120s delay, jittered ±10%)
- Task fails again at T=200s → Retry at T=500s (300s delay, jittered ±10%)
- Task fails at T=510s → Mark as FAILED (3 retries exhausted)

## Dead Letter: Failed Tasks

When all retries are exhausted, Celery does not dequeue the task again. The task is essentially dead, but the exception and traceback are available. Etherion captures this in the Job record:

```python
# In task_failure signal handler (src/core/celery.py)
@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Log task failure."""
    logger.error(f"Task {sender.name} ({task_id}) failed: {exception}")
    logger.error(f"Traceback: {traceback}")
```

And in the task itself, before the final exception is raised:

```python
@tenant_task(bind=True, name="core.archive_execution_trace")
def archive_execution_trace_task(self, job_id: str, tenant_id=None):
    try:
        # ... archive logic ...
    except Exception as exc:
        logger.error(f"Failed to archive execution trace: {exc}")
        raise self.retry(exc=exc)  # Will retry up to max_retries
```

After all retries fail, the task's exception and traceback are available in Celery's logs, but the task message is removed from Redis. The **Job record** in the database becomes the source of truth for clients:

```python
# Job record with error information
job = Job(
    job_id="...",
    status=JobStatus.FAILED,
    error_message="Connection to GCS failed: timeout after 30s",
    # ... other fields
)
```

## Persisting Errors to the Job Record

As a task executes and encounters an error, it updates the Job record with the error message:

```python
@tenant_task(bind=True, name="core.update_job_status")
def update_job_status_task(self, job_id: str, status: str, error_message=None, tenant_id=None):
    try:
        # ... update logic ...
    except Exception as exc:
        logger.error(f"Failed to update job status for {job_id}: {exc}")
        raise self.retry(exc=exc, countdown=60, max_retries=3)
```

The error is stored as a string in `job.error_message`, which is indexed in the database for quick retrieval.

For task types that generate execution traces (like agent goals), errors are also stored in ExecutionTraceStep records:

```python
# In agent execution loop
try:
    observation = tool(input_data)
except Exception as e:
    # Log the error in the trace
    trace_step = ExecutionTraceStep(
        job_id=self.request.id,
        step_number=step,
        observation_result=None,
        error_message=str(e),
        timestamp=datetime.utcnow(),
    )
    session.add(trace_step)
    session.commit()

    # Decide: retry tool call or stop execution
    if retry_count < max_retries:
        retry_count += 1
        continue
    else:
        job.error_message = f"Tool error after {max_retries} retries: {e}"
        job.update_status(JobStatus.FAILED)
        session.commit()
        raise
```

## Publishing Errors to Clients

When a job status changes to FAILED, the `update_job_status_task` publishes a status update to Redis, which GraphQL subscriptions receive:

```python
# In /src/core/tasks.py
status_data = {
    "job_id": job_id,
    "status": "FAILED",
    "timestamp": datetime.utcnow().isoformat(),
    "error_message": error_message,
    "tenant_id": tenant_id
}

# Publish to subscriptions
import asyncio
try:
    loop = asyncio.get_running_loop()
    asyncio.create_task(publish_job_status(job_id, status_data))
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(publish_job_status(job_id, status_data))
    finally:
        loop.close()
```

Clients subscribed to `jobStatusUpdated(jobId: "abc-123")` receive:

```json
{
  "jobStatusUpdated": {
    "jobId": "abc-123",
    "status": "FAILED",
    "errorMessage": "Connection to embedding service timed out after 3 retries",
    "timestamp": "2026-03-26T14:30:00Z"
  }
}
```

This allows the client UI to display the error immediately.

## Idempotent Task Design

Because tasks may be executed multiple times (due to retries or worker crashes), tasks must be **idempotent**: executing the same task twice should be safe.

**Pattern 1: Check-before-create**

```python
@celery_app.task(name="core.create_document")
def create_document(self, doc_id, content):
    """Create a document if it doesn't already exist."""
    doc = session.query(Document).filter(Document.id == doc_id).first()
    if doc:
        logger.info(f"Document {doc_id} already exists, skipping creation")
        return {"status": "already_exists", "doc_id": doc_id}

    doc = Document(id=doc_id, content=content)
    session.add(doc)
    session.commit()
    return {"status": "created", "doc_id": doc_id}
```

**Pattern 2: Versioned operations**

```python
@celery_app.task(name="core.update_embeddings")
def update_embeddings(self, doc_id, version):
    """Update embeddings for a document if version matches."""
    doc = session.query(Document).filter(Document.id == doc_id).first()
    if doc.embedding_version >= version:
        logger.info(f"Embeddings already at version {version}")
        return {"status": "already_done", "doc_id": doc_id}

    embeddings = compute_embeddings(doc.content)
    doc.embeddings = embeddings
    doc.embedding_version = version
    session.commit()
    return {"status": "updated", "doc_id": doc_id}
```

**Pattern 3: External idempotency keys**

Some external systems (payment processors, APIs) expect an idempotency key header. When retrying, send the same key so the external system recognizes the retry and returns the same result:

```python
@celery_app.task(name="core.process_payment")
def process_payment(self, payment_id):
    """Process a payment with idempotency."""
    payment = session.query(Payment).filter(Payment.id == payment_id).first()

    # Use payment_id as idempotency key
    response = payment_api.charge(
        amount=payment.amount,
        idempotency_key=f"pay_{payment_id}_{version}",
    )

    if response.success:
        payment.status = "completed"
    else:
        raise Exception(f"Payment failed: {response.error}")

    session.commit()
    return response
```

## Monitoring Failures

Etherion logs all task failures with structured logging. In Cloud Logging, you can query:

```
resource.type="cloud_run"
resource.service_name="etherion-worker"
jsonPayload.level="ERROR"
jsonPayload.task_name != null
```

This shows all tasks that have failed, allowing operators to identify patterns (e.g., "all GCS tasks are failing", "retry storms on Tuesday"). Set up alerts on error rates to catch systemic issues early.
