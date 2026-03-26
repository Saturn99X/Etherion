# Architecture: The Five Core Services

Etherion's architecture is built around five interdependent services that orchestrate AI agent execution at scale. This document walks through each service, its responsibilities, and how they communicate.

## Service Topology

```
                          Client Browser / TUI
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │   GraphQL API Server    │
                    │  (FastAPI + Strawberry) │
                    │  Port 8000              │
                    │  - Query / Mutation /   │
                    │    Subscription         │
                    │  - Auth middleware      │
                    │  - Rate limiting        │
                    │  - Tenant context       │
                    └────────┬────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
           ▼                 ▼                 ▼
    ┌────────────┐   ┌────────────────┐   ┌──────────────┐
    │ PostgreSQL │   │  Redis Cache   │   │ MinIO/GCS    │
    │   (DB)     │   │  & Message Bus │   │  (Object     │
    │ - Jobs     │   │ - Job state    │   │   Storage)   │
    │ - Users    │   │ - Status feed  │   │ - Artifacts  │
    │ - Agents   │   │ - Credentials  │   │ - Knowledge  │
    │ - Assets   │   │ - Rate limits  │   │ - Ledger     │
    └─────┬──────┘   └────────┬───────┘   └──────────────┘
          │                   │
          │                   ▼
          │          ┌────────────────────┐
          │          │  Celery Workers    │
          │          │  (Multiple nodes)  │
          │          │  - worker-agents   │
          │          │  - worker-artifacts│
          │          │  - high_priority   │
          │          │  - low_priority    │
          └──────────►                    │
                     │ Task Results       │
                     │ & Pub/Sub Events   │
                     └────────┬───────────┘
                              │
                              ▼
                    ┌─────────────────────────┐
                    │  External Services      │
                    │  - Gmail API            │
                    │  - Slack API            │
                    │  - Notion API           │
                    │  - Jira API             │
                    │  - Shopify API          │
                    │  - Salesforce API       │
                    │  - OpenAI / Gemini      │
                    └─────────────────────────┘
```

## Service 1: GraphQL API Server

**Purpose**: Accept requests, enforce authentication + tenancy, and coordinate with backend workers.

**Technology**: FastAPI (Python async framework) + Strawberry (GraphQL implementation)

**Port**: 8000

**Key Responsibilities**:
- Route mutations to Celery (async job submission)
- Manage WebSocket subscriptions for real-time status updates
- Enforce OAuth token validation via JWT middleware
- Apply per-IP rate limiting (120 req/min default, configurable)
- Extract and validate tenant context from request headers
- Serve OAuth callback handlers for third-party integrations (Gmail, Slack, Jira, etc.)

**Request Flow**:
```python
# Example GraphQL mutation (from app.py)
# Client calls:
mutation {
  executeGoal(agentId: "agent_123", input: "...") {
    jobId
    status
  }
}

# Strawberry resolver:
@strawberry.mutation
async def executeGoal(
    self,
    agent_id: str,
    input: str,
    info: GraphQLResolveInfo
) -> JobResult:
    tenant_id = get_tenant_from_context(info)

    # Validate agent belongs to tenant (RLS at DB layer)
    agent = await db.get_agent(agent_id, tenant_id)
    if not agent:
        raise Forbidden()

    # Enqueue job with Celery
    job = await db.create_job(agent_id, tenant_id, input)
    celery_app.send_task(
        "goal_orchestrator.execute_goal",
        kwargs={"job_id": job.id, "tenant_id": tenant_id},
        queue="worker-agents"
    )

    return JobResult(jobId=job.id, status="QUEUED")
```

**Middleware Stack** (in order):
1. **Security Handler** — Validates SECRET_KEY, CSRF tokens
2. **Rate Limiting** — Blocks if IP exceeds 120 req/min (reads from Redis)
3. **Versioning** — Adds version header to responses
4. **Request Logger** — Logs all HTTP requests
5. **GraphQL Auth** — Extracts JWT and validates signature
6. **Tenant Middleware** — Sets `request.state.tenant_id` based on subdomain or header

## Service 2: PostgreSQL Database

**Purpose**: Persistent storage of all state (users, agents, jobs, execution traces, assets).

**Deployment**: Managed service (Postgres 14+)

**Key Tables**:
- `job` — Agent execution jobs with status tracking
- `user` — User accounts with email + password hashes
- `tenant` — Workspace/organization records
- `agent_team` — Teams of agents
- `execution_trace_step` — Step-by-step reasoning trace for each job
- `thread`, `thread_message` — Conversation threads (for future multi-turn support)
- `asset` — AI-generated documents stored in object storage

**Row-Level Security (RLS)**:
Every SELECT/UPDATE/DELETE on tenant-scoped tables includes a WHERE clause:
```sql
WHERE tenant_id = current_tenant_id
```

This is enforced at the database level, not just in application code. Even if a worker is compromised, it cannot query another tenant's data.

**Connection Pooling**:
The API uses SQLAlchemy with a 20-connection pool (configurable via `DB_POOL_SIZE`). Workers use a separate unscoped session to fetch jobs before setting tenant context.

## Service 3: Redis Cache & Message Bus

**Purpose**: Fast, in-memory state for job tracking, credentials, and real-time pub/sub.

**Technology**: Redis 6.0+ (Cluster or Sentinel for HA)

**Key Data Structures**:

| Key Pattern | Type | TTL | Purpose |
|---|---|---|---|
| `iprl:{ip}:{minute}` | Counter | 70s | Rate limit per IP |
| `admin_ingest:{job_id}` | JSON | 1h | Ingest task status |
| `oauth:nonce:{nonce}` | Marker | 10m | OAuth replay prevention |
| `quota:{tenant}:{vendor}:{date}` | Counter | Until midnight | Vendor quota tracking |
| `job:{job_id}:status` | JSON | 1h | Current job state (for polling) |

**Pub/Sub Channels**:
```
job:{job_id}:updates       → Broadcasts job status changes
job:{job_id}:trace         → Streams execution trace steps
tenant:{tenant_id}:credits → Publishes credit balance updates
```

**Credential Storage** (via TenantSecretsManager):
```
tenant:{tenant_id}:{service}:{key} = encrypted_secret
Example: tenant:42:gmail:oauth_credentials = {...access_token, refresh_token...}
```

Each tenant's credentials are namespaced. Workers retrieve them at runtime:
```python
sm = TenantSecretsManager()
gmail_creds = await sm.get_secret(tenant_id, "gmail", "oauth_credentials")
# Returns decrypted JSON with access_token, refresh_token, expiry, scopes
```

## Service 4: Celery Workers

**Purpose**: Execute long-running agent orchestration jobs outside the HTTP request-response cycle.

**Deployment**: Multiple worker pods/instances, each listening to specific queues

**Queues & Routing**:

| Queue | Workers | Routing | Purpose |
|---|---|---|---|
| `worker-agents` | Agent worker pool | Default | Execute `executeGoal` tasks |
| `worker-artifacts` | Ingestion worker | Heavy I/O | Multimodal document parsing, BigQuery writes |
| `high_priority` | All workers | Webhook callbacks | Process Slack/Jira/Notion events |
| `low_priority` | All workers (idle) | Cleanup | Archival, reconciliation |

**Task Lifecycle**:

```python
@celery_app.task(bind=True, name="goal_orchestrator.execute_goal")
def execute_goal(self, job_id: str, tenant_id: int):
    """Orchestrate an agent through its reasoning loop."""

    # 1. Set tenant context (threads all subsequent DB queries)
    set_tenant_context(tenant_id)

    # 2. Fetch job and agent
    job = db.get_job(job_id)
    agent = db.get_agent(job.agent_id)

    # 3. Enter agentic loop
    step_num = 0
    while job.status in [RUNNING, QUEUED]:
        step_num += 1

        # Call LLM with tool context
        response = llm.call(
            prompt=build_prompt(agent, job.input, step_num),
            tools=[
                {"name": "fetch_gmail", "description": "..."},
                {"name": "send_slack", "description": "..."},
            ]
        )

        # Record thought
        trace_step = db.create_execution_trace(
            job_id, tenant_id, step_num,
            thought=response.reasoning,
            action_tool=response.tool_name,
            action_input=response.tool_args
        )

        # Execute tool (calls MCP handler)
        if response.tool_name == "fetch_gmail":
            observation = call_gmail_tool(response.tool_args, tenant_id)
        elif response.tool_name == "send_slack":
            observation = call_slack_tool(response.tool_args, tenant_id)

        # Record observation
        trace_step.observation_result = observation
        db.update_execution_trace(trace_step)

        # Publish progress
        await publish_job_status(job_id, "RUNNING")

        # Check stop condition
        if response.stop:
            break

    # 4. Mark complete
    job.status = COMPLETED
    job.output = response.final_output
    db.update_job(job)

    # 5. Archive execution trace
    celery_app.send_task(
        "core.archive_execution_trace",
        kwargs={"job_id": job_id, "tenant_id": tenant_id},
        queue="worker-artifacts"
    )

    return {"job_id": job_id, "status": "COMPLETED"}
```

**Retry & Failure Handling**:

```python
# From celery.py:
celery_app.conf.update(
    task_acks_late=True,                    # Acknowledge after completion
    task_reject_on_worker_shutdown=True,    # Requeue on graceful shutdown
    task_default_max_retries=3,
    task_default_retry_delay=60,            # 1 minute
    task_retry_backoff=True,                # Exponential: 60s, 120s, 240s
    task_retry_jitter=True,                 # Add jitter to prevent thundering herd
)
```

If a worker dies mid-task, the task remains in the broker queue (Redis) and is picked up by another worker. This ensures no work is lost.

## Service 5: External Services (Data Silos)

**Purpose**: Represent the systems where agents execute tool calls (Gmail, Slack, Notion, etc.).

**Access Pattern**:
1. Agent decides to call "fetch_gmail"
2. Worker invokes the MCP Gmail tool with tenant credentials
3. MCP tool uses OAuth tokens stored in Redis/Vault to authenticate
4. Call is rate-limited per vendor (e.g., max 5000 Gmail API calls/day per tenant)
5. Result flows back to agent

**Webhook Handling** (for reactive agents):
```
External service (Slack) emits event
        ↓
POST /webhook/slack/{tenant_id}
        ↓
Validate signature (HMAC-SHA256)
        ↓
Increment quota counter
        ↓
Enqueue task to "high_priority" queue
        ↓
Worker processes event, possibly triggering an agent execution
```

Example from app.py:
```python
@app.post("/webhook/slack/{tenant_id}")
async def slack_webhook(tenant_id: int, request: Request):
    body_bytes = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    # Validate signature
    from src.tools.mcp.mcp_slack import MCPSlackTool
    tool = MCPSlackTool()
    is_valid = await tool.handle_webhook(
        tenant_id=str(tenant_id),
        timestamp=timestamp,
        body=body_bytes.decode(),
        signature=signature
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Quota check (fail if tenant exceeded Slack quota today)
    await _quota_increment_or_429(tenant_id, "slack")

    # Enqueue processing
    celery_app.send_task(
        "webhooks.process_slack_event",
        args=[tenant_id, json.loads(body_bytes.decode())],
        queue="high_priority"
    )

    return JSONResponse({"ok": True})
```

## Communication Patterns

### Sync: API → Worker
**Use**: Submitting a job
```python
# In API handler
celery_app.send_task(
    "goal_orchestrator.execute_goal",
    kwargs={"job_id": job.id, "tenant_id": tenant_id},
    queue="worker-agents"
)
# Returns immediately; task is queued in Redis
```

### Async: Worker → Client (via Event Bus)
**Use**: Pushing real-time job status updates
```python
# In worker
import asyncio
status_data = {
    "job_id": job_id,
    "status": "RUNNING",
    "timestamp": datetime.utcnow().isoformat(),
    "error_message": None,
    "tenant_id": tenant_id
}

try:
    loop = asyncio.get_running_loop()
    asyncio.create_task(publish_job_status(job_id, status_data))
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(publish_job_status(job_id, status_data))
    loop.close()
```

```python
# In publish_job_status (from redis.py)
async def publish_job_status(job_id: str, status_data: Dict[str, Any]):
    redis = get_redis_client()
    channel = f"job:{job_id}:updates"
    await redis.publish(channel, json.dumps(status_data))
```

```graphql
# Client subscribes (GraphQL subscription)
subscription {
  onJobStatusChange(jobId: "job_123") {
    jobId
    status
    updatedAt
    errorMessage
  }
}

# Strawberry resolver handles the pub/sub
@strawberry.subscription
async def onJobStatusChange(self, job_id: str, info: GraphQLResolveInfo):
    redis = get_redis_client()
    async with redis.subscribe(f"job:{job_id}:updates") as channel:
        async for message in channel:
            yield json.loads(message)
```

## Scaling Considerations

### Horizontal Scaling
- **API servers**: Stateless, add behind a load balancer. Each connects to the same PostgreSQL + Redis.
- **Workers**: Scale by adding more worker pods listening to the same Celery broker. Jobs are automatically distributed.
- **Database**: Use read replicas for reporting queries; write operations go to the primary.
- **Redis**: Run in Cluster mode (16 shards) for 100k+ concurrent jobs.

### Vertical Scaling
- **API**: Increase process count with Gunicorn (4-8 processes per 2 CPU cores).
- **Workers**: More memory allows larger context windows for LLM prompts. CPU bound on token processing.
- **Database**: Larger buffer pool (25-30% of RAM) for query cache.

### Cost Optimization
- Use spot/preemptible instances for worker-artifacts (they're retriable).
- Reserve capacity for worker-agents (they handle revenue-generating jobs).
- Enable Redis eviction (`maxmemory-policy allkeys-lru`) for credentials cache.

## Health & Monitoring

Etherion exports three health endpoints:

```python
# GET /health
→ {"status": "OK"}  # Fast; used by load balancers

# GET /metrics
→ Prometheus metrics (task count, latency, errors)

# POST /admin/health
→ Detailed report of database, Redis, workers, external services
```

From `src/core/health.py`, the HealthChecker runs concurrent checks:
- Database latency and pool utilization
- Redis connectivity and memory usage
- Celery worker count and task queue depth
- External service reachability (OpenAI, Google AI APIs)
- System resources (CPU, memory, disk)

An unhealthy check sets the overall status to DEGRADED or UNHEALTHY, which triggers PagerDuty alerts.
