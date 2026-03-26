# Mutations: State-Modifying Operations

## Overview

Mutations in Etherion represent any operation that changes server state: creating jobs, updating teams, connecting integrations, or signing up new users. Unlike queries, which are read-only and can be cached, mutations are always executed immediately and have side effects.

In GraphQL, mutation semantics are simple: all mutations run sequentially in the order the client specifies. This prevents race conditions and ensures predictable ordering when clients submit multiple mutations together.

## Authentication Mutations

Authentication is handled separately in `auth_mutations.py` because it's the entry point before a user has a session context.

### googleLogin Mutation

When a user clicks "Sign in with Google," the frontend receives an authorization code from Google's OAuth flow. The client sends that code to our GraphQL mutation:

```python
@strawberry.mutation
async def googleLogin(
    self,
    info: Info,
    code: str,
    invite_token: Optional[str] = None,
    redirect_uri: Optional[str] = None
) -> AuthResponse:
    """
    Authenticate user with Google OAuth.

    This mutation exchanges a Google OAuth authorization code for an access token
    and creates or updates the user in the database.
    """
    try:
        auth_context = info.context.get("request").state.auth_context
        db_session = auth_context["db_session"]

        request = info.context.get("request")
        client_ip = get_client_ip(request)

        # Delegate to auth service
        result = await handle_oauth_callback(
            "google",
            code,
            db_session,
            invite_token=invite_token,
            redirect_uri=redirect_uri,
            client_ip=client_ip
        )

        return AuthResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            user=result["user"]
        )
    except ValueError as e:
        raise Exception(str(e))
    except Exception as e:
        if hasattr(e, 'detail'):
            raise Exception(e.detail)
        raise Exception(f"Google login failed: {str(e)}")
```

**Flow**:

1. Client POST to `/graphql` with `googleLogin` mutation and the authorization `code` from Google
2. Resolver calls `handle_oauth_callback("google", code, ...)` in `src/auth/service.py`
3. Auth service:
   - Uses Google's OAuth2 library to exchange code for tokens
   - Fetches user info from Google (email, name, profile picture)
   - Creates a new user in the database if not exists, or updates the existing user
   - Generates a JWT access token and refresh token
4. Returns `AuthResponse` containing the JWT and user object
5. Client stores JWT in localStorage or a secure cookie
6. Subsequent requests include JWT in `Authorization: Bearer <token>` header

**Error handling**: If OAuth fails (invalid code, network error, user info fetch fails), the resolver catches the exception and raises a GraphQL error. The error message is user-facing (e.g., "Google OAuth service unavailable").

### passwordSignup Mutation

For users without OAuth (or on internal networks where OAuth isn't available), we support email/password signup:

```python
@strawberry.mutation
async def passwordSignup(
    self,
    info: Info,
    email: str,
    password: str,
    name: Optional[str] = None,
    invite_token: Optional[str] = None,
    subdomain: Optional[str] = None,
) -> AuthResponse:
    """Sign up with email/password (invite enforced when configured)."""
    auth_context = info.context.get("request").state.auth_context
    db_session = auth_context["db_session"]
    request = info.context.get("request")
    client_ip = get_client_ip(request)

    result = await password_signup(
        email=email,
        password=password,
        session=db_session,
        name=name,
        invite_token=invite_token,
        subdomain=subdomain,
        client_ip=client_ip
    )

    return AuthResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        user=result["user"],
    )
```

The auth service hashes the password using bcrypt and stores it in the database. On login, the service compares the provided password hash to the stored hash. Since signup can create a new tenant, the `subdomain` parameter allows users to choose their workspace subdomain.

## Goal Execution Mutation

The core of Etherion is orchestrating agent goals. The `executeGoal` mutation (in `mutations.py`) is how users submit tasks:

```python
@strawberry.mutation
async def executeGoal(
    self,
    info: Info,
    goal_input: GoalInput,
) -> GoalOutput:
    """
    Execute a goal using the Etherion orchestration system.

    Args:
        goal_input: Input containing goal description, context, etc.

    Returns:
        GoalOutput: Job ID and initial status

    Throws:
        ValidationError: If input fails validation
        AuthenticationError: If user not authenticated
    """
    auth_context = info.context.get("request").state.auth_context
    current_user = auth_context["current_user"]
    db_session = auth_context["db_session"]

    if not current_user:
        raise Exception("Not authenticated")

    # Validate and sanitize input
    sanitized_input = await validate_and_sanitize_goal_input(goal_input, {
        "user_id": current_user.id,
        "tenant_id": current_user.tenant_id,
        "ip_address": get_client_ip(info.context.get("request")),
    })

    # Create a Job record in database
    job = Job(
        job_id=str(uuid4()),
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        status=JobStatus.PENDING,
        job_type="goal_execution",
        input_data={"goal": sanitized_input.goal, "context": sanitized_input.context},
    )

    db_session.add(job)
    db_session.commit()

    # Enqueue background orchestration task
    asyncio.create_task(
        _run_orchestration_with_error_handling(
            job_id=job.job_id,
            goal_description=sanitized_input.goal,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
    )

    return GoalOutput(
        job_id=job.job_id,
        status="PENDING",
        message="Goal queued for execution"
    )
```

**Critical flow**:

1. **Validation**: Input is sanitized (XSS prevention, length limits, etc.) using Pydantic validators
2. **Isolation**: Job is tagged with the authenticated user's tenant_id and user_id
3. **Persistence**: Job record is written to PostgreSQL with PENDING status
4. **Async Dispatch**: Background orchestration task is queued (via asyncio.create_task)
5. **Immediate Response**: Resolver returns immediately with job_id, allowing client to poll/subscribe for updates

The resolver does NOT wait for orchestration to complete. If it did, the HTTP request would hang. Instead, the client later calls `subscribeToJobStatus(job_id)` to receive real-time updates as the job progresses through RUNNING → COMPLETED/FAILED states.

### Orchestration Background Task

The background task runs in an async context:

```python
async def _run_orchestration_with_error_handling(
    job_id: str,
    goal_description: str,
    user_id: int,
    tenant_id: int,
) -> None:
    """Wrapper to catch exceptions from background orchestration tasks."""
    try:
        await orchestrate_goal_task(
            job_id=job_id,
            goal_description=goal_description,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    except Exception as e:
        # Update job status to FAILED
        try:
            from src.database.db import get_scoped_session
            async with get_scoped_session() as session:
                res = await session.exec(select(Job).where(Job.job_id == job_id))
                job = res.first()
                if job:
                    job.error_message = f"Uncaught exception: {str(e)}"
                    job.update_status(JobStatus.FAILED)
                    session.add(job)
        except Exception as inner_e:
            print(f"Failed to update job status: {inner_e}")
```

This wrapper ensures that if orchestration throws an exception, the job is marked FAILED. The actual orchestration logic (calling LLMs, invoking tools, managing state) is in the `orchestrate_goal_task` service.

## Agent Team Management Mutations

Etherion allows users to create and manage teams of agents. These mutations are in the main `Mutation` class:

```python
@strawberry.mutation
async def createAgentTeam(
    self,
    info: Info,
    team_input: AgentTeamInput,
) -> AgentTeamType:
    """
    Create a new agent team for the tenant.

    Args:
        team_input: Team configuration (name, description, member agents)

    Returns:
        AgentTeamType: Created team with generated team_id
    """
    auth_context = info.context.get("request").state.auth_context
    current_user = auth_context["current_user"]
    db_session = auth_context["db_session"]

    if not current_user:
        raise Exception("Not authenticated")

    # Permission check: user must have MANAGE_AGENTS permission
    auth_ctx_obj = await get_authorization_context_for_user(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        db_session=db_session,
    )
    if not auth_ctx_obj.has_permission(Permission.MANAGE_AGENTS):
        raise Exception("Insufficient permissions")

    # Create team record
    team = AgentTeam(
        agent_team_id=str(uuid4()),
        tenant_id=current_user.tenant_id,
        name=team_input.name,
        description=team_input.description,
        is_active=True,
        version=1,
    )

    db_session.add(team)
    db_session.commit()

    return AgentTeamType(
        id=team.agent_team_id,
        name=team.name,
        description=team.description,
        createdAt=team.created_at.isoformat(),
    )
```

**Key points**:

1. **Authorization**: Before creating a team, we check that the user has the `MANAGE_AGENTS` permission. This is loaded from the authorization context.
2. **Tenant Scoping**: The team is automatically tagged with the authenticated user's tenant. No team can be associated with a different tenant.
3. **ID Generation**: Team IDs are UUIDs, ensuring they're globally unique.
4. **Commit**: Changes are immediately persisted to PostgreSQL.

## Integration Management Mutations

Users can connect third-party integrations (Gmail, Slack, Notion, etc.). The `connectIntegration` mutation handles the OAuth flow:

```python
@strawberry.mutation
async def connectIntegration(
    self,
    info: Info,
    integration_input: IntegrationInput,
) -> IntegrationStatus:
    """
    Connect a third-party integration (e.g., Gmail, Slack).

    Returns an authorization URL the client should redirect to.
    """
    auth_context = info.context.get("request").state.auth_context
    current_user = auth_context["current_user"]

    if not current_user:
        raise Exception("Not authenticated")

    # Map integration name to OAuth vendor
    vendor_map = {
        "gmail": "gmail",
        "slack": "slack",
        "notion": "notion",
    }
    vendor = vendor_map.get(integration_input.service_name)
    if not vendor:
        raise Exception(f"Unsupported integration: {integration_input.service_name}")

    # Generate OAuth state (to prevent CSRF)
    nonce = base64.urlsafe_b64encode(os.urandom(18)).decode()
    state_obj = {
        "tenant_id": current_user.tenant_id,
        "vendor": vendor,
        "nonce": nonce,
        "iat": int(time.time()),
    }
    state = _encode_state(state_obj, os.environ.get("OAUTH_STATE_SECRET"))

    # Store nonce in Redis (expires in 10 minutes)
    redis = get_redis_client()
    await redis.set(f"oauth:nonce:{nonce}", "1", expire=600)

    # Build vendor-specific authorize URL
    if vendor == "gmail":
        params = {
            "response_type": "code",
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "redirect_uri": f"{base_url}/oauth/gmail",
            "scope": "https://www.googleapis.com/auth/gmail.send",
            "state": state,
        }
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    elif vendor == "slack":
        url = f"https://slack.com/oauth/v2/authorize?{urlencode({...})}"
    # ... other vendors

    return IntegrationStatus(
        service_name=vendor,
        status="pending_auth",
        authorize_url=url,
    )
```

The resolver returns an authorization URL. The client opens this URL in a popup, the user authorizes Etherion on the vendor's site, and the vendor redirects back to our callback endpoint. The callback (a REST endpoint, not a GraphQL mutation) exchanges the authorization code for tokens and stores them in Vault.

## Error Handling in Mutations

Mutations use try-catch to handle errors gracefully:

```python
try:
    # Perform mutation logic
    result = await some_operation()
    return SuccessResponse(...)
except ValueError as e:
    # Input validation errors (client's fault)
    raise Exception(f"Invalid input: {str(e)}")
except PermissionError as e:
    # Authorization errors
    raise Exception(f"Access denied: {str(e)}")
except Exception as e:
    # Unexpected errors (server's fault)
    logger.error(f"Mutation failed: {str(e)}", exc_info=True)
    raise Exception("An unexpected error occurred")
```

All exceptions are caught and re-raised as GraphQL errors. The GraphQL response includes the error message, allowing clients to show appropriate UI feedback.

## Idempotency

Some mutations (like creating a job) may be retried if the network times out. To prevent duplicate jobs, we could implement idempotency keys. Clients would include an `idempotency_key` parameter; the server would cache the response keyed by (user_id, idempotency_key) and return the cached result on retry.

This is currently not implemented but is a pattern to consider for critical mutations.

## Subscription Triggers

When a mutation completes, it may trigger subscriptions. For example, when `createAgentTeam` succeeds, clients subscribed to `subscribeToTeamUpdates` receive a notification. This is done by publishing to Redis:

```python
# After creating team
await publish_event("team_created", {
    "tenant_id": current_user.tenant_id,
    "team_id": team.agent_team_id,
    "team_name": team.name,
})
```

Subscription resolvers listen on Redis channels and yield events to connected clients. This keeps the UI real-time: if one user creates a team, other users in the same tenant see it appear in their team list immediately.

## Next Steps

- **Subscriptions** (`subscriptions.md`): Learn how mutations trigger real-time updates via Redis pub/sub.
- **Middleware** (`middleware.md`): Understand validation, sanitization, and error handling in the request pipeline.
- **Schema Structure** (`schema-structure.md`): Dive deeper into how input/output types are defined.
