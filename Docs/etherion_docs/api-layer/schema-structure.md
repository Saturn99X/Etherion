# Schema Structure and Type System

## Strawberry Framework Overview

Etherion uses Strawberry, a Python GraphQL library that embraces Python's type system. Instead of manually writing GraphQL schema strings, we define Python dataclasses and decorate them with `@strawberry.type`. Strawberry introspects these classes and generates the GraphQL schema automatically.

This approach has three major benefits:

1. **Type Safety**: Type hints become part of the contract. An IDE can autocomplete field names and catch errors.
2. **Minimal Boilerplate**: No separate schema definition files. The Python class *is* the schema.
3. **Async Native**: Strawberry resolvers use `async def`, making it natural to call async services without blocking.

## Schema Organization

Our schema lives in `src/etherion_ai/graphql_schema/` and is organized into files:

```
graphql_schema/
├── queries.py           # Query root type and all read-only resolvers
├── mutations.py         # Mutation root type and all state-modifying resolvers
├── subscriptions.py     # Subscription root type for real-time updates
├── auth_mutations.py    # Authentication-specific mutations
├── output_types.py      # GraphQL output types (response objects)
├── input_types.py       # GraphQL input types (request parameters)
└── input_validators.py  # Pydantic validators for input sanitization
```

The schema is assembled in `src/etherion_ai/app.py`:

```python
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    config=StrawberryConfig(auto_camel_case=False),
)

graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/graphql")
```

This creates the `/graphql` endpoint that handles both HTTP POST (for queries and mutations) and WebSocket upgrades (for subscriptions).

## Type Definitions

### Output Types (Response Objects)

Output types are marked with `@strawberry.type` and represent what the server sends back:

```python
@strawberry.type
class JobHistoryItem:
    id: str
    goal: str
    status: str
    createdAt: str
    completedAt: Optional[str]
    duration: str
    totalCost: str
    modelUsed: Optional[str]
    tokenCount: Optional[int]
    successRate: Optional[float]
```

Fields are simple Python attributes. Strawberry converts field names automatically (snake_case → camelCase) unless disabled in the schema config. Fields can be:

- **Scalars**: `str`, `int`, `float`, `bool`
- **Custom Objects**: Other `@strawberry.type` classes
- **Lists**: `List[SomeType]`
- **Optionals**: `Optional[SomeType]` for nullable fields
- **Enums**: Classes decorated with `@strawberry.enum`

### Input Types (Request Parameters)

Input types represent what clients send to mutations:

```python
@strawberry.input
class GoalInput:
    goal: str
    context: Optional[str] = None
    output_format_instructions: Optional[str] = None
    userId: str
    agentTeamId: Optional[str] = None
    threadId: Optional[str] = None
```

Input types use `@strawberry.input` and are similar to output types but are used as function arguments in mutations.

### Resolver Functions

A resolver is a Python async function that computes a field's value. In Strawberry, resolvers are methods on the Query, Mutation, or Subscription class:

```python
@strawberry.type
class Query:
    @strawberry.field
    async def getJobDetails(self, info: Info, job_id: str) -> Optional[JobDetails]:
        """
        Get detailed information about a specific job.
        """
        # Get auth context from GraphQL request
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        # Query database (scoped to tenant)
        job = db_session.exec(
            select(Job).where(
                Job.job_id == job_id,
                Job.tenant_id == current_user.tenant_id,
                Job.user_id == current_user.id  # User-level isolation
            )
        ).first()

        if not job:
            return None

        # Convert ORM object to GraphQL type
        return JobDetails(
            job_id=job.job_id,
            status=job.status.value,
            created_at=job.created_at.isoformat() if job.created_at else "",
            input_data=job.get_input_data(),
            output_data=job.get_output_data(),
        )
```

**Key points**:

1. **Info Object**: The `info: Info` parameter is injected by Strawberry. It contains context from the request, including the authenticated user and database session.

2. **Argument Mapping**: Python function arguments become GraphQL mutation/query arguments. A function argument `job_id: str` becomes a required `jobId: String!` in GraphQL (unless marked `Optional`).

3. **Return Type**: The function's return type annotation becomes the GraphQL return type. `Optional[JobDetails]` becomes `JobDetails` in the schema (nullable).

4. **Async**: All resolvers are `async`, allowing us to use async database queries and service calls without blocking.

## The Context Getter

GraphQL requests need a context object passed to resolvers. In Etherion, the context getter is defined in `app.py`:

```python
async def get_context(connection: HTTPConnection, connection_params: Optional[dict] = None):
    """Get GraphQL context for both HTTP requests and WebSocket connections."""
    tenant_id = getattr(connection.state, "tenant_id", None)
    auth_ctx = getattr(connection.state, "auth_context", None)

    # For WebSocket connections, extract auth from connection_params (graphql-ws protocol)
    connection_params = connection_params or {}

    if auth_ctx is None:
        current_user, resolved_tenant_id = await resolve_current_user_from_headers(connection.headers)
        if tenant_id is None:
            tenant_id = resolved_tenant_id

        # Attach auth context to connection state for reuse
        connection.state.auth_context = {
            "current_user": current_user,
            "db_session": None,
            "tenant_id": tenant_id,
        }
        connection.state.tenant_id = tenant_id

    set_tenant_context(tenant_id)

    return {
        "request": connection,
        "tenant_id": tenant_id,
        "connection_params": connection_params,
    }
```

This context is passed to every resolver, accessible via `info.context`. It contains:

- `request`: The HTTP or WebSocket connection
- `tenant_id`: The tenant this request belongs to
- `connection_params`: Extra parameters from WebSocket clients

Resolvers extract auth context from the request state:
```python
auth_context = info.context["request"].state.auth_context
current_user = auth_context["current_user"]
```

## Database Session Scoping

Database sessions are attached to the request during middleware processing. The `db_session` in `auth_context` is a scoped session that automatically filters queries by tenant. When a resolver executes `select(Job).where(...)`, the session applies tenant filtering underneath.

This is critical for multi-tenancy: even if a malicious user tries to query jobs without a tenant filter, the session's implicit WHERE clause prevents data leaks.

## Middleware Integration

The request flows through middleware before reaching the GraphQL router:

1. **CSRF Guard** (`add_middleware(GraphQLCSRFGuard)`) — Validates request origin for browser requests
2. **Auth Context** (`app.middleware("http")(graphql_auth_middleware)`) — Extracts JWT, resolves user, attaches auth_context
3. **Tenant Middleware** (`app.middleware("http")(tenant_middleware)`) — Sets tenant context for the entire request
4. **Versioning Middleware** — Parses Accept-Version header, sets api_version in request state
5. **Request Logger** — Assigns request_id, logs request details

By the time the request reaches the GraphQL layer, `request.state` contains:
- `auth_context`: User and tenant info
- `tenant_id`: Resolved tenant
- `api_version`: Requested API version
- `request_id`: Unique request identifier

## Enum Types

Etherion uses enums for fixed sets of values like job status:

```python
@strawberry.enum
class JobStatusEnum(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

In resolvers, we convert ORM status values to enum:

```python
status=JobStatusEnum(job.status.value)
```

This ensures clients only see valid status values and can use them as constants in their code.

## Field Descriptions and Deprecations

Strawberry fields can include descriptions and deprecation info:

```python
@strawberry.type
class Agent:
    id: str = strawberry.field(description="Unique agent identifier")
    name: str = strawberry.field(description="Display name of the agent")
    capabilities: List[str] = strawberry.field(
        description="List of tool capabilities this agent can invoke"
    )
    deprecated_field: Optional[str] = strawberry.field(
        description="Deprecated: use newer_field instead",
        deprecation_reason="Replaced by newer_field in v1.0"
    )
```

These descriptions appear in GraphQL introspection and in tools like Apollo Studio. They're machine-readable, so IDE plugins can warn developers about deprecated fields.

## Custom Scalars

For complex types like JSON objects or timestamps, Strawberry supports custom scalars:

```python
@strawberry.type
class JobDetails:
    input_data: JSON = strawberry.field(
        description="Unstructured input data for the job, serialized as JSON"
    )
```

The `JSON` scalar accepts any JSON-serializable value. Strawberry handles serialization/deserialization automatically.

## Building and Introspection

To view the schema, send an introspection query to `/graphql`:

```graphql
query {
  __schema {
    types {
      name
      fields {
        name
        type { name }
      }
    }
  }
}
```

This returns the entire schema in JSON form. Tools like GraphQL Playground, Apollo Studio, and IDE plugins use this to provide autocomplete and documentation.

The schema is always in sync with the code because it's generated from Python type hints. There's no separate schema file to maintain—the code *is* the schema.

## Next Steps

- **Mutations** (`mutations.md`): Learn how state-modifying operations like `executeGoal` are implemented.
- **Subscriptions** (`subscriptions.md`): Understand how real-time updates flow from Redis through WebSocket to clients.
- **Middleware** (`middleware.md`): Explore the request processing pipeline and logging infrastructure.
