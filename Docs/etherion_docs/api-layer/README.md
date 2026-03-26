# GraphQL API Layer

## Why GraphQL for Etherion

When building Etherion, we made a deliberate choice to move beyond REST and adopt GraphQL as our primary API interface. This wasn't arbitrary—it reflects the complexity of our domain and the shape of data our clients need.

### The REST Problem

A REST API for a system like Etherion quickly becomes a maze of endpoints. Consider querying a job's execution details. You'd need `/jobs/:id` to get the job, then separately call `/jobs/:id/status`, `/jobs/:id/outputs`, `/jobs/:id/metrics`, and perhaps `/jobs/:id/artifacts`. Each call adds latency; each response carries overhead. Clients end up making dozens of roundtrips to assemble what they need.

In Etherion's case, different UI screens ask different questions. The job history list doesn't care about execution traces, but the job detail modal needs them. A dashboard might want top-level metrics but not step-by-step transcripts. REST forces you to either **over-fetch** (getting data you don't need) or **under-fetch** (making extra calls). Both waste bandwidth and hurt perceived performance.

### How GraphQL Solves This

GraphQL inverts the paradigm. The client defines its shape:

```graphql
query JobDetails($jobId: String!) {
  getJobDetails(job_id: $jobId) {
    job_id
    status
    created_at
    completed_at
    input_data
    output_data {
      final_output
      total_cost
      model_used
    }
    execution_steps {
      step_id
      tool_name
      duration_ms
    }
  }
}
```

The server responds with exactly what was asked for, nothing more. Different clients can use the same endpoint but fetch different shapes of data. The dashboard queries one shape; the job detail view queries another. A mobile client, bandwidth-conscious, queries a minimal subset. All hit the same GraphQL endpoint.

### Three Killer Features for Etherion

**1. Flexible Queries**

Jobs in Etherion have complex nested structures: inputs, outputs, execution traces, cost data, thread information, artifacts. A GraphQL query lets you traverse these relationships in one roundtrip. You're not locked into a predefined response shape.

**2. Subscriptions for Real-Time Updates**

When a user submits a goal and Etherion begins orchestrating it, they want live updates: status changes, progress on each step, intermediate outputs. GraphQL subscriptions are a natural fit. Over a WebSocket, the server pushes updates as they arrive in Redis. No polling, no artificial delays. In `subscribeToJobStatus`, users see status, progress, and errors as the job executes.

**3. Self-Documenting Schema**

GraphQL schemas are machine-readable and introspectable. Any client can call the GraphQL server with an introspection query and discover all available operations, their arguments, return types, and descriptions. Tools like Apollo Client's dev tools, GraphQL playgrounds, and LSP servers automatically understand your API. No separate OpenAPI spec to keep in sync. Your documentation lives in the schema itself.

## The Etherion Schema Architecture

Our GraphQL schema is organized into three root types:

- **Query**: Read-only operations to fetch data
- **Mutation**: Operations that modify state (create jobs, update teams, configure integrations)
- **Subscription**: Real-time updates pushed from server to client

All three are powered by Strawberry, a Python-native GraphQL framework that uses type hints and decorators. This means our resolvers are Pythonic and our types are validated at the Python level before serialization.

### Query Root

The `Query` type contains read operations for data retrieval:

- `getProjectsByTenant`: List all projects for the authenticated user's tenant
- `getConversationsByProject`: Fetch conversation history
- `getJobHistory`: Paginated job listing with filtering
- `getJobDetails`: Retrieve full job execution trace
- `listAgentTeams`: Enumerate custom agent teams
- `getAvailableMCPTools`: Discover available integrations
- `getCurrentUser`: Retrieve authenticated user info
- `getUserSettings`: Fetch per-tenant user preferences

### Mutation Root

The `Mutation` type groups all state-modifying operations:

- **Authentication**: `googleLogin`, `githubLogin`, `passwordSignup`, `logout`
- **Job Management**: `executeGoal`, `cancelJob`, `submitFeedback`
- **Team Management**: `createAgentTeam`, `updateAgentTeam`, `deleteAgentTeam`
- **Integration Management**: `connectIntegration`, `testIntegration`, `disconnectIntegration`
- **Custom Agents**: `createCustomAgent`, `updateCustomAgent`, `deleteCustomAgent`

### Subscription Root

The `Subscription` type defines real-time channels:

- `subscribeToJobStatus`: Push status updates for a specific job
- `subscribeToExecutionTrace`: Stream execution steps as they happen
- `subscribeToUIEvents`: Broadcast events (new teammates joined, permission changes)

## How Queries Flow Through the System

When a client sends a GraphQL query, here's what happens:

```
1. Request arrives at FastAPI app (/graphql endpoint)
2. Middleware stack runs:
   - CSRF guard (validates request origin)
   - Auth middleware (extracts and validates JWT from Authorization header)
   - Tenant middleware (resolves tenant_id from claims)
   - Versioning middleware (reads Accept-Version header)
   - Request logger (logs request + assigns request_id)
3. Strawberry GraphQL router receives the query
4. Schema validation: Strawberry type-checks the query against the schema
5. Resolver for each field is executed in dependency order
6. Auth context is passed to each resolver via the Info object
7. Resolver queries database, calls services, formats response
8. Response is serialized to JSON and sent back to client
```

Every resolver has access to the authenticated user and tenant via `info.context["request"].state.auth_context`. This allows us to enforce tenant-level data isolation and user-level permissions without repeating auth logic in every resolver.

## Advantages Over REST for Etherion's Use Case

1. **Reduced Network Traffic**: Clients fetch only the fields they need. A mobile client asking for recent jobs gets just the job ID, status, and created date—not megabytes of execution trace.

2. **Type Safety**: Strawberry generates TypeScript types from the schema. Frontend code is type-checked against the API schema at build time. Breaking a resolver's return type is caught immediately.

3. **Painless API Evolution**: Adding a new field to an output type doesn't break existing clients. Deprecating fields is supported. The schema tells clients which fields are outdated.

4. **Single Endpoint**: All API traffic flows through `/graphql`. No versioning chaos with `/v1/jobs` vs `/v2/jobs`. One endpoint, one schema version indicator in the Accept-Version header.

5. **Real-Time Capabilities**: Subscriptions are built into the spec. No need to bolt on a separate WebSocket handler; Strawberry manages the WebSocket upgrade and subscription lifecycle.

## Security Model

Every resolver runs with an authenticated user context. Strawberry resolvers use Python's async/await, so they're non-blocking. The database session is scoped to the current tenant, meaning queries cannot leak data across tenants. All inputs are validated and sanitized at the Strawberry layer before reaching business logic.

CSRF protection is enforced at the middleware level for mutations originating from browsers. Subscriptions use token-based authentication over WebSocket, decoded from the connection parameters.

## Next Steps

- **Schema Structure** (`schema-structure.md`): Dive into how the Strawberry schema is organized, how types are defined, and where resolvers live.
- **Mutations** (`mutations.md`): Study key mutations like `executeGoal` and `createAgentTeam`, tracing the path from resolver to database write.
- **Subscriptions** (`subscriptions.md`): Learn how real-time updates flow through Redis pub/sub to connected clients.
- **Middleware** (`middleware.md`): Understand the request pipeline, logging, error handling, and request ID injection.
