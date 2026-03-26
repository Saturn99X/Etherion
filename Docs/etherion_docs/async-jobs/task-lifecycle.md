# Task Lifecycle: From Mutation to Job Completion

## The Mutation Enqueues the Task

When a client calls the `executeGoal` GraphQL mutation, the resolver code enqueues a Celery task instead of running it inline:

```python
# In a GraphQL mutation resolver
from src.services.goal_orchestrator import execute_goal

result = execute_goal.apply_async(
    args=[goal_spec, user_id, tenant_id],
    kwargs={},
    countdown=0,  # Execute ASAP
)
job_id = result.id  # Celery task ID
```

The mutation creates a Job record in the database:

```python
from src.database.models import Job, JobStatus

job = Job(
    job_id=result.id,
    tenant_id=tenant_id,
    user_id=user_id,
    status=JobStatus.QUEUED,
    job_type="execute_goal",
    input_data=json.dumps(goal_spec),
)
session.add(job)
session.commit()
```

The mutation returns immediately with the job_id. The client stores this ID and can subscribe to job status updates via GraphQL subscription.

## Task Serialization and Enqueue

When `apply_async()` is called, Celery:

1. Serializes task arguments as JSON
2. Creates a task message with metadata (task name, ID, args, kwargs, retry count, etc.)
3. Pushes the message onto the Redis queue (default queue is `worker-agents`)

```
Redis queue "worker-agents": [
    {
        "task": "goal_orchestrator.execute_goal",
        "id": "abc-123-def-456",
        "args": [{"goal": "research X"}, 42, 999],
        "kwargs": {},
        "retry": 0,
        "eta": null,
        "expires": 3600,
    }
]
```

The message is now durable in Redis. If the Redis server crashes in the next second, the message survives on disk (depending on persistence settings).

## Worker Dequeues and Begins Execution

A worker listening on the `worker-agents` queue polls Redis continuously (every ~100ms by default). When it finds a task message:

1. Pops the message from the queue
2. Deserializes the arguments
3. Looks up the task function by name and imports it
4. Fires the `task_prerun` signal (logged with task ID and arguments)
5. Executes the task function

```python
# Task definition (in src/services/goal_orchestrator.py)
@celery_app.task(bind=True, name="goal_orchestrator.execute_goal")
def execute_goal(self, goal_spec, user_id, tenant_id):
    """Execute an agent goal."""
    # self.request.id is the Celery task ID
    logger.info(f"Executing goal {self.request.id}")

    # Set job status to RUNNING
    job = session.query(Job).filter(Job.job_id == self.request.id).first()
    job.update_status(JobStatus.RUNNING)
    job.started_at = datetime.utcnow()
    session.commit()

    # Agent loop: think → act → observe → repeat
    result = agent_loop(goal_spec, user_id, tenant_id)

    return {"status": "completed", "result": result}
```

## Job Status Transitions

The Job model tracks status throughout execution:

```python
class JobStatus(str, Enum):
    QUEUED = "QUEUED"        # Enqueued, waiting for worker
    RUNNING = "RUNNING"      # Worker started execution
    COMPLETED = "COMPLETED"  # Execution succeeded
    FAILED = "FAILED"        # Execution failed (all retries exhausted)
    CANCELLED = "CANCELLED"  # User cancelled via StopJob mutation
```

Transitions follow this flow:

```
QUEUED
  ↓
RUNNING (when worker starts executing)
  ↓
COMPLETED (if execute_goal returns successfully)
  OR
FAILED (if execute_goal raises an exception after retries)
  OR
CANCELLED (if user calls StopJob mutation)
```

## Logging Each Step

As the task executes, it logs major steps:

```python
# In the agent loop
for step in range(max_steps):
    # Think
    thought = agent.think(state)
    logger.info(f"Step {step}: thought = {thought[:100]}...")

    # Act
    action, tool, input = agent.decide_action(thought)
    logger.info(f"Step {step}: action = {tool} with {input}")

    # Observe
    observation = tool(input)
    logger.info(f"Step {step}: observation = {observation[:100]}...")

    # Save step to execution trace
    trace_step = ExecutionTraceStep(
        job_id=self.request.id,
        step_number=step,
        thought=thought,
        action_tool=tool,
        action_input=input,
        observation_result=observation,
        timestamp=datetime.utcnow(),
    )
    session.add(trace_step)
    session.commit()
```

These ExecutionTraceStep records are the audit trail. Later, they're archived to GCS as JSONL and Markdown for replay and analysis.

## Task Completion and Postrun

When the task function returns:

1. Celery fires the `task_postrun` signal (logged)
2. Task function result is written to the Job record as output_data
3. Job status is updated to COMPLETED

```python
def execute_goal(self, goal_spec, user_id, tenant_id):
    try:
        # ... agent loop logic ...
        result = agent_loop(goal_spec, user_id, tenant_id)

        # Update job with result
        job.set_output_data({
            "final_thought": result.thought,
            "final_output": result.output,
            "steps_executed": result.step_count,
        })
        job.update_status(JobStatus.COMPLETED)
        session.commit()

        return result
    except Exception as exc:
        # Will be caught by failure handler
        raise
```

## Publishing the Status Update

When job status changes, an internal task publishes the change to Redis (used by GraphQL subscriptions):

```python
import asyncio
from src.core.redis import publish_job_status

status_data = {
    "job_id": self.request.id,
    "status": "COMPLETED",
    "timestamp": datetime.utcnow().isoformat(),
    "tenant_id": tenant_id,
}

# Publish to subscriptions
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

GraphQL subscriptions listening on `jobStatusUpdated(jobId: "abc-123")` receive this event and push it to the client immediately.

## Archival on Completion

When a job completes successfully, a background task is enqueued to archive execution traces:

```python
# In job status update handler
if status.lower() == JobStatus.COMPLETED.value.lower():
    try:
        archive_execution_trace_task.apply_async(
            args=[job_id],
            kwargs={"tenant_id": tenant_id},
        )
    except Exception as e:
        logger.warning(f"Failed to enqueue archival for job {job_id}: {e}")
```

This task uploads ExecutionTraceStep records to GCS as JSONL, generates a human-readable markdown transcript, and optionally registers the transcript in the knowledge base for retrieval-augmented generation.

## Tenant-Scoped Execution

All tasks that access tenant data use the `@tenant_task` decorator:

```python
from src.core.tenant_tasks import tenant_task

@tenant_task(bind=True, name="goal_orchestrator.execute_goal")
def execute_goal(self, goal_spec, user_id, tenant_id):
    # tenant_id is automatically set in thread-local context
    # get_tenant_context() returns the tenant_id
    # Database queries filter by tenant_id automatically
```

This ensures database isolation: each task's queries are scoped to its tenant, preventing data leaks between multitenancy boundaries.
