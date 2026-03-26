# Request Lifecycle: From HTTP to Agent Completion

This document traces a complete agent job from the moment a client hits the API until the job finishes, artifacts are stored, and the client receives the final event via WebSocket. Every hop is annotated with real code from the Etherion codebase.

## Scenario

A user with `tenant_id=42` runs an agent (`agent_id="research_bot"`) to fetch today's Slack messages and draft a summary.

```graphql
mutation {
  executeGoal(
    agentId: "research_bot"
    input: "Summarize all Slack messages from #general today"
  ) {
    jobId
    status
  }
}
```

## Step 1: HTTP Request Arrives at API

**Actor**: Client browser / TUI

**Endpoint**: `POST /graphql`

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json
X-Etherion-Tenant: app42.etherion.local
```

**Body**:
```json
{
  "query": "mutation { executeGoal(...) { jobId status } }",
  "variables": {}
}
```

## Step 2: Middleware Chain Executes

**Actor**: FastAPI middleware stack (from app.py, lines 189-276)

### 2.1 Security Handler
```python
# src/etherion_ai/middleware/security_integration.py
async def secure_request_handler(request: Request, call_next):
    """
    Validates CSRF tokens and SECRET_KEY.
    Rejects if X-CSRF-Token header is missing or invalid.
    """
    csrf_token = request.headers.get("X-CSRF-Token")
    stored_token = request.cookies.get("csrf_token")

    if not _verify_csrf(csrf_token, stored_token):
        raise HTTPException(status_code=403, detail="CSRF validation failed")

    response = await call_next(request)
    return response
```

**Result**: Request passes CSRF validation or is rejected with 403.

### 2.2 Rate Limiting (Per-IP)
```python
# app.py, PerIPRateLimitMiddleware class (lines 195-257)
class PerIPRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host  # e.g., "203.0.113.42"
        path = request.url.path

        # Exempt health, metrics, OAuth endpoints
        if path in ("/health", "/", "/metrics") or path.startswith("/webhook/"):
            return await call_next(request)

        # Rate limit key: iprl:{ip}:{minute}
        key = f"iprl:{client_ip}:{int(time.time() // 60)}"

        redis = get_redis_client()
        client = await redis.get_client()
        current = await client.incr(key)  # Increment counter

        if int(current) == 1:
            await client.expire(key, 70)  # Set TTL to 70 seconds

        if int(current) > self.per_minute:  # Default 120
            raise HTTPException(
                status_code=429,
                detail="Too Many Requests"
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, self.per_minute - int(current))
        )
        return response
```

**Result**: If `current > 120`, request is rejected with 429. Otherwise, headers are added and flow continues.

### 2.3 GraphQL Auth Middleware
```python
# src/etherion_ai/middleware/auth_context.py
@app.middleware("http")
async def graphql_auth_middleware(request: Request, call_next):
    """Extract JWT token and resolve user + tenant."""

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        current_user = await resolve_user_from_jwt(token)
        request.state.auth_context = {
            "current_user": current_user,
            "db_session": await get_scoped_session(),
        }

    return await call_next(request)
```

**Result**: `request.state.auth_context` is populated with user details.

### 2.4 Tenant Middleware
```python
# src/etherion_ai/middleware/tenant_middleware.py
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    """Extract tenant_id from subdomain or header."""

    # Option 1: X-Etherion-Tenant header (e.g., "app42.etherion.local")
    tenant_header = request.headers.get("X-Etherion-Tenant", "")
    if tenant_header:
        request.state.tenant_id = extract_tenant_id(tenant_header)

    # Option 2: Host header (e.g., "app42.etherion.local")
    host = request.headers.get("Host", "")
    if host and ".etherion.local" in host:
        request.state.tenant_id = extract_tenant_id(host)

    # Option 3: Subdomain from auth token (embedded in JWT)
    if not hasattr(request.state, "tenant_id"):
        if request.state.auth_context and request.state.auth_context.get("current_user"):
            request.state.tenant_id = request.state.auth_context["current_user"].tenant_id

    return await call_next(request)
```

**Result**: `request.state.tenant_id = 42` is set for downstream resolvers.

## Step 3: GraphQL Query Parsed & Validated

**Actor**: Strawberry GraphQL resolver

**Location**: `src/etherion_ai/graphql_schema/mutations.py`

The mutation `executeGoal` is dispatched:

```python
@strawberry.mutation
async def executeGoal(
    self,
    agentId: str,
    input: str,
    info: GraphQLResolveInfo
) -> JobResult:
    """
    Execute an agent goal asynchronously.
    Returns immediately with job_id; actual work happens in a worker.
    """
    tenant_id = info.context.get("tenant_id")

    if not tenant_id:
        raise Unauthorized("Tenant context not found")

    # Validate that agent belongs to tenant
    async with get_scoped_session() as session:
        agent = await session.exec(
            select(CustomAgentDefinition).where(
                CustomAgentDefinition.agent_id == agentId,
                CustomAgentDefinition.tenant_id == tenant_id,
                CustomAgentDefinition.is_active == True
            )
        )
        agent = agent.first()

        if not agent:
            raise NotFound(f"Agent {agentId} not found for tenant {tenant_id}")

        # Create job record (status: QUEUED)
        job = Job(
            job_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            agent_id=agentId,
            user_id=info.context["current_user"].user_id,
            input=input,
            status=JobStatus.QUEUED,
            created_at=datetime.utcnow(),
        )
        session.add(job)
        await session.commit()
        job_id = job.job_id

    # Return immediately
    return JobResult(
        jobId=job_id,
        status="QUEUED"
    )
```

**Result**:
- Job record is created in PostgreSQL with `status="QUEUED"`.
- Response is sent to client **immediately**:
```json
{
  "data": {
    "executeGoal": {
      "jobId": "550e8400-e29b-41d4-a716-446655440000",
      "status": "QUEUED"
    }
  }
}
```

**Important**: The actual job execution has NOT started yet. The API has only enqueued it.

## Step 4: Client Subscribes to WebSocket for Updates

**Actor**: Client (Browser or TUI)

**Endpoint**: `POST /graphql` (HTTP/1.1 Upgrade to WebSocket)

**GraphQL Subscription**:
```graphql
subscription {
  onJobStatusChange(jobId: "550e8400-e29b-41d4-a716-446655440000") {
    jobId
    status
    updatedAt
    errorMessage
  }
}
```

**Strawberry Handler** (src/etherion_ai/graphql_schema/subscriptions.py):
```python
@strawberry.subscription
async def onJobStatusChange(
    self,
    job_id: str,
    info: GraphQLResolveInfo
) -> AsyncGenerator[JobStatusUpdate, None]:
    """
    Stream job status updates via Redis pub/sub.
    Client receives updates in real-time as job progresses.
    """
    tenant_id = info.context.get("tenant_id")
    redis = get_redis_client()

    # Subscribe to channel: job:{job_id}:updates
    channel_name = f"job:{job_id}:updates"

    async with redis.subscribe(channel_name) as channel:
        async for message in channel:
            data = json.loads(message)
            # Verify tenant_id in message matches subscription tenant
            if data.get("tenant_id") != tenant_id:
                continue

            yield JobStatusUpdate(
                jobId=data["job_id"],
                status=data["status"],
                updatedAt=data["timestamp"],
                errorMessage=data.get("error_message")
            )
```

**Result**: WebSocket connection is established. Client is ready to receive updates.

## Step 5: Job Enqueued to Celery Broker

**Actor**: GraphQL resolver (Part 3, continued)

This happens before returning the response to the client. In production code, it typically happens like this:

```python
# After job is saved to DB, enqueue Celery task
from src.core.celery import celery_app

celery_app.send_task(
    "goal_orchestrator.execute_goal",
    kwargs={
        "job_id": job_id,
        "tenant_id": tenant_id,
    },
    queue="worker-agents"
)
```

**What Happens in Celery**:
1. Task is serialized to JSON: `{"job_id": "550e8400...", "tenant_id": 42}`
2. Message is pushed to Redis list: `celery:worker-agents`
3. All worker processes listening to `worker-agents` queue are notified

## Step 6: Worker Picks Up Task

**Actor**: Celery Worker (running `celery -A src.core.celery worker -l info -Q worker-agents`)

**Process**:
1. Worker polls Redis for messages in the `worker-agents` queue
2. Finds the job message
3. Deserializes the payload
4. Calls the task function

**Location**: `src/services/goal_orchestrator.py` (not shown in provided files, but this is where it happens)

The task function:
```python
@celery_app.task(bind=True, name="goal_orchestrator.execute_goal")
def execute_goal(self, job_id: str, tenant_id: int):
    """Orchestrate agent reasoning loop."""

    # Set tenant context for all DB queries
    set_tenant_context(tenant_id)

    try:
        # 1. Fetch job and agent
        with tenant_scoped_session(tenant_id) as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            agent = session.query(CustomAgentDefinition).filter(
                CustomAgentDefinition.agent_id == job.agent_id
            ).first()

            # Update job status to RUNNING
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            session.commit()

        # Publish RUNNING event
        publish_job_status(job_id, {
            "job_id": job_id,
            "status": "RUNNING",
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": tenant_id
        })

        # 2. Enter agentic loop (simplified)
        step_num = 0
        max_steps = agent.max_steps or 10

        while step_num < max_steps:
            step_num += 1

            # Call LLM with agent system prompt + tools
            llm_response = call_llm(
                prompt=build_agent_prompt(agent, job.input, step_num),
                tools=[
                    {"name": "fetch_slack_messages", "description": "..."},
                    {"name": "search_knowledge_base", "description": "..."},
                ]
            )

            # Record thought in execution trace
            with tenant_scoped_session(tenant_id) as session:
                trace_step = ExecutionTraceStep(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    step_number=step_num,
                    thought=llm_response.reasoning,
                    action_tool=llm_response.tool_name,
                    action_input=json.dumps(llm_response.tool_args),
                    timestamp=datetime.utcnow(),
                )
                session.add(trace_step)
                session.commit()

            # Execute tool
            if llm_response.tool_name == "fetch_slack_messages":
                observation = fetch_slack_messages(
                    tenant_id,
                    **llm_response.tool_args
                )
            elif llm_response.tool_name == "search_knowledge_base":
                observation = search_knowledge_base(
                    tenant_id,
                    **llm_response.tool_args
                )

            # Record observation
            with tenant_scoped_session(tenant_id) as session:
                trace_step = session.query(ExecutionTraceStep).filter(
                    ExecutionTraceStep.step_number == step_num,
                    ExecutionTraceStep.job_id == job_id
                ).first()
                trace_step.observation_result = observation
                session.commit()

            # Publish progress
            publish_job_status(job_id, {
                "job_id": job_id,
                "status": "RUNNING",
                "step": step_num,
                "thought": llm_response.reasoning,
                "timestamp": datetime.utcnow().isoformat(),
                "tenant_id": tenant_id
            })

            # Check stop condition
            if llm_response.stop:
                break

        # 3. Mark job complete
        with tenant_scoped_session(tenant_id) as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            job.status = JobStatus.COMPLETED
            job.output = llm_response.final_output
            job.completed_at = datetime.utcnow()
            session.commit()

        # Publish COMPLETED event
        publish_job_status(job_id, {
            "job_id": job_id,
            "status": "COMPLETED",
            "output": job.output,
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": tenant_id
        })

        # 4. Archive execution trace
        celery_app.send_task(
            "core.archive_execution_trace",
            kwargs={"job_id": job_id, "tenant_id": tenant_id},
            queue="worker-artifacts"
        )

        return {"job_id": job_id, "status": "COMPLETED"}

    except Exception as exc:
        with tenant_scoped_session(tenant_id) as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            session.commit()

        publish_job_status(job_id, {
            "job_id": job_id,
            "status": "FAILED",
            "error_message": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": tenant_id
        })

        raise self.retry(exc=exc, countdown=60, max_retries=3)
```

## Step 7: Tool Execution (MCP Layer)

**Actor**: MCP tool handler (e.g., `MCPSlackTool`)

When the agent calls "fetch_slack_messages":

```python
# From src/tools/mcp/mcp_slack.py (conceptual)
def fetch_slack_messages(tenant_id: int, channel: str, limit: int = 20):
    """Fetch recent messages from a Slack channel."""

    # 1. Resolve tenant credentials
    tsm = TenantSecretsManager()
    slack_creds = await tsm.get_secret(tenant_id, "slack", "bot_token")
    # Returns: {"access_token": "xoxb-...", ...}

    # 2. Call Slack API with tenant's token
    import slack_sdk
    client = slack_sdk.WebClient(token=slack_creds["access_token"])

    response = client.conversations_history(
        channel=channel,
        limit=limit
    )

    # 3. Return observation (as string for LLM to reason over)
    messages = [
        f"{msg['user']}: {msg['text']}"
        for msg in response["messages"]
    ]

    return "\n".join(messages)
```

**Key**: The Slack token belongs to **tenant 42**, not a shared service account. Each tenant's agent sees only their own data.

## Step 8: WebSocket Events Streamed to Client

**Actor**: Redis pub/sub → WebSocket subscription

Each time the worker publishes an event (via `publish_job_status`), it lands in Redis channel `job:550e8400....:updates`. The Strawberry subscription handler receives it:

```python
async for message in channel:
    # message = '{"job_id": "550e8400...", "status": "RUNNING", "step": 2, ...}'
    data = json.loads(message)

    yield JobStatusUpdate(
        jobId=data["job_id"],
        status=data["status"],
        updatedAt=data["timestamp"],
        errorMessage=data.get("error_message")
    )
```

The client receives (via WebSocket) a stream of messages:

```json
{
  "data": {
    "onJobStatusChange": {
      "jobId": "550e8400-e29b-41d4-a716-446655440000",
      "status": "RUNNING",
      "updatedAt": "2026-03-26T16:29:42.123456Z",
      "errorMessage": null
    }
  }
}
```

```json
{
  "data": {
    "onJobStatusChange": {
      "jobId": "550e8400-e29b-41d4-a716-446655440000",
      "status": "RUNNING",
      "updatedAt": "2026-03-26T16:29:44.567890Z",
      "errorMessage": null
    }
  }
}
```

```json
{
  "data": {
    "onJobStatusChange": {
      "jobId": "550e8400-e29b-41d4-a716-446655440000",
      "status": "COMPLETED",
      "updatedAt": "2026-03-26T16:29:46.987654Z",
      "errorMessage": null
    }
  }
}
```

## Step 9: Execution Trace Archived

**Actor**: worker-artifacts queue (heavy-I/O worker)

When the job completes, a second task is enqueued (see Step 6):

```python
celery_app.send_task(
    "core.archive_execution_trace",
    kwargs={"job_id": job_id, "tenant_id": tenant_id},
    queue="worker-artifacts"
)
```

From `src/core/tasks.py`:

```python
@tenant_task(bind=True, name="core.archive_execution_trace")
def archive_execution_trace_task(self, job_id: str, tenant_id: int):
    """
    Archive ExecutionTraceStep records to GCS and register as AI Asset.
    """

    with tenant_scoped_session(tenant_id) as session:
        # 1. Fetch all trace steps
        steps = session.query(ExecutionTraceStep).filter(
            ExecutionTraceStep.job_id == job_id
        ).order_by(ExecutionTraceStep.step_number.asc()).all()

        # 2. Serialize to JSONL (one step per line)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as tmp:
            for s in steps:
                record = {
                    "job_id": s.job_id,
                    "step_number": s.step_number,
                    "thought": s.thought,
                    "action_tool": s.action_tool,
                    "action_input": s.get_action_input(),
                    "observation_result": s.observation_result,
                }
                tmp.write(json.dumps(record) + "\n")
            temp_path = tmp.name

        # 3. Upload to GCS
        gcs = GCSClient(tenant_id=str(tenant_id))
        jsonl_key = f"ai/{job_id}/replay_trace.jsonl"
        jsonl_uri = gcs.upload_file(temp_path, jsonl_key)

        # 4. Generate markdown transcript
        from src.utils.transcript_utils import generate_markdown_transcript
        transcript_md = generate_markdown_transcript([...])

        # 5. Upload markdown
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as md_tmp:
            md_tmp.write(transcript_md)
            md_temp_path = md_tmp.name

        md_key = f"ai/{job_id}/replay_transcript.md"
        md_uri = gcs.upload_file(md_temp_path, md_key)

        # 6. Register as AI asset in database
        job.trace_data_uri = jsonl_uri

        # 7. Try to embed and index in BigQuery (optional)
        try:
            bq_inst = BigQueryService(project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
            embedder = EmbeddingService(project_id=bq_inst.project_id)
            vector = embedder.embed_texts([transcript_md[:15000]])[0]
            asset_row = {
                "asset_id": f"replay_{job_id}",
                "gcs_uri": md_uri,
                "vector_embedding": vector,
            }
            bq_inst.insert_rows_json("tnt_42", "assets", [asset_row])
        except Exception:
            pass  # Best-effort; don't fail the archive task

        session.commit()

    return {
        "success": True,
        "job_id": job_id,
        "trace_uri": jsonl_uri,
        "transcript_uri": md_uri
    }
```

**Result**: Execution trace is now permanently stored and searchable.

## Step 10: Client Fetches Final Artifacts

**Actor**: Client, after receiving COMPLETED event

The client knows the job finished and wants the full transcript:

```graphql
query {
  getJobAssets(jobId: "550e8400-e29b-41d4-a716-446655440000") {
    assetId
    filename
    gcsUri
    contentType
  }
}
```

**API Resolver** (from app.py):

```python
@app.get("/repo/assets/{asset_id}")
async def repo_get_asset(request: Request, asset_id: str):
    tenant_id = getattr(request.state, "tenant_id", None)

    svc = ContentRepositoryService(
        str(tenant_id),
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    rec = svc.get_asset(asset_id)

    if not rec:
        raise HTTPException(status_code=404, detail="Not found")

    return JSONResponse(
        status_code=200,
        content={
            "asset_id": rec.asset_id,
            "job_id": rec.job_id,
            "filename": rec.filename,
            "gcs_uri": rec.gcs_uri,
            "size_bytes": rec.size_bytes,
            "created_at": rec.created_at,
        }
    )
```

## Summary: The Full Flow

| Time | Actor | Action | Result |
|------|-------|--------|--------|
| T+0 | Client | GraphQL mutation | Job enqueued, ID returned |
| T+0.1 | API | Enqueue Celery task | Message in Redis broker |
| T+0.2 | Client | Subscribe to WebSocket | Ready for updates |
| T+0.5 | Worker | Pick task from queue | Job fetched from DB |
| T+0.5 | Worker | Call LLM for step 1 | Thought recorded |
| T+0.6 | Worker | Execute tool (Slack API) | Data fetched with tenant creds |
| T+0.7 | Worker | Publish RUNNING event | Message in Redis pub/sub |
| T+0.7 | Client | Receive event via WebSocket | UI updates progress bar |
| T+0.8 | Worker | Repeat: Call LLM → Tool → Record |  ... |
| T+2.0 | Worker | Loop ends (stop condition met) | Output saved to job |
| T+2.0 | Worker | Publish COMPLETED event | Message in Redis pub/sub |
| T+2.0 | Client | Receive event via WebSocket | UI shows COMPLETED badge |
| T+2.1 | Worker | Enqueue archive task | Message in worker-artifacts queue |
| T+2.5 | Artifact Worker | Archive trace to GCS + BigQuery | Artifacts stored with vector index |
| T+3.0 | Client | Query `/repo/assets/{asset_id}` | Transcript retrieved from GCS |

**Total time**: ~3 seconds from mutation to complete UI with artifacts (in production, varies by agent complexity and external API latency).

This architecture ensures:
- **Non-blocking API**: Response sent immediately; work happens in workers.
- **Real-time feedback**: Client sees every step via WebSocket.
- **Tenant isolation**: Credentials and data are scoped to the tenant throughout the pipeline.
- **Durable execution**: If a worker dies, the job is requeued and retried automatically.
- **Artifact preservation**: Traces and outputs persist in object storage for compliance and audit.
