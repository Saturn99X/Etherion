# Etherion Documentation

Welcome to the Etherion AI Platform documentation. This is your starting point for understanding how the platform is built, why it works the way it does, and how to operate it.

The docs are written for engineers — not as a config reference, but as a teaching resource. Each section explains what a component does, why it exists, and how it fits into the whole.

---

## How to Read This

If you are new to Etherion, start with **Platform Overview** to understand the big picture, then follow the chain from data model → authentication → API → orchestration. The other sections can be read in any order based on what you need to work on.

If you are debugging a specific area, jump directly to that section's README.

---

## Sections

### [Platform Overview](platform-overview/README.md)
What Etherion is, who it serves, and how the five core services fit together. Includes a complete walkthrough of a request from the client all the way to a finished AI job and back.

- [Architecture](platform-overview/architecture.md) — the five services and their roles
- [Request Lifecycle](platform-overview/request-lifecycle.md) — one complete job, every hop

---

### [Data Model](data-model/README.md)
The PostgreSQL schema: every entity, every relationship, and the philosophy behind it. Explains how multi-tenancy is enforced at the database level.

- [Entities](data-model/entities.md) — Tenant, User, Project, Job, Agent, and more
- [Relationships](data-model/relationships.md) — ownership chains with ER diagram
- [RLS Deep Dive](data-model/rls-deep-dive.md) — how Row-Level Security enforces tenant isolation

---

### [Authentication](authentication/README.md)
Two sign-in paths (OAuth and local), JWTs, sessions, MFA, and the middleware pipeline that validates every request.

- [OAuth Flow](authentication/oauth-flow.md) — Google/GitHub/Microsoft, step by step
- [Local Auth](authentication/local-auth.md) — password hashing, reset flow, TOTP
- [JWT and Sessions](authentication/jwt-and-sessions.md) — what a token contains and how it's validated
- [Middleware Pipeline](authentication/middleware-pipeline.md) — the six layers every request passes through

---

### [API Layer](api-layer/README.md)
The GraphQL API built with FastAPI and Strawberry. Explains why GraphQL, how the schema is structured, and how resolvers connect to the rest of the system.

- [Schema Structure](api-layer/schema-structure.md) — types, resolvers, Strawberry decorators
- [Mutations](api-layer/mutations.md) — key mutations end-to-end
- [Subscriptions](api-layer/subscriptions.md) — real-time via GraphQL over WebSocket
- [Middleware](api-layer/middleware.md) — logging, error handling, request IDs

---

### [Orchestration](orchestration/README.md)
How AI jobs are executed: agent teams, the 2N+1 reasoning loop, specialist execution, and tool dispatch.

- [Agent Teams](orchestration/agent-teams.md) — composition and configuration
- [Execution Loop](orchestration/execution-loop.md) — the 2N+1 algorithm with diagram
- [Specialist Executor](orchestration/specialist-executor.md) — inside a single specialist run
- [Tool Dispatch](orchestration/tool-dispatch.md) — the tool registry and approval flow

---

### [Async Jobs](async-jobs/README.md)
Why agent runs are asynchronous and how Celery with Redis handles them reliably.

- [Celery Setup](async-jobs/celery-setup.md) — broker, queues, concurrency model
- [Task Lifecycle](async-jobs/task-lifecycle.md) — pending → running → completed/failed
- [Worker and Beat](async-jobs/worker-and-beat.md) — the two daemon processes
- [Error Handling](async-jobs/error-handling.md) — retries, dead letters, failure propagation

---

### [Knowledge Base](knowledge-base/README.md)
Per-tenant semantic document stores powered by pgvector. How documents are ingested, embedded, and retrieved.

- [How Vectors Work](knowledge-base/how-vectors-work.md) — embeddings explained intuitively
- [Document Ingestion](knowledge-base/document-ingestion.md) — upload → extract → embed → store
- [Vector Search](knowledge-base/vector-search.md) — cosine similarity queries at retrieval time
- [KB Backend Abstraction](knowledge-base/kb-backend-abstraction.md) — the pluggable backend interface

---

### [Real-Time Updates](real-time/README.md)
How job progress streams to connected clients in real time using Redis pub/sub and GraphQL subscriptions.

- [Redis Pub/Sub](real-time/redis-pubsub.md) — channels, events, publish flow
- [GraphQL Subscriptions](real-time/graphql-subscriptions.md) — the async generator pattern
- [WebSocket Lifecycle](real-time/websocket-lifecycle.md) — upgrade, auth, events, close

---

### [Storage](storage/README.md)
MinIO object storage for files, artifacts, and knowledge base documents. The StorageBackend abstraction and the full artifact lifecycle.

- [MinIO Setup](storage/minio-setup.md) — configuration, buckets, presigned URLs
- [Storage Backend Abstraction](storage/storage-backend-abstraction.md) — the ABC and three implementations
- [Artifact Lifecycle](storage/artifact-lifecycle.md) — upload through expiry

---

### [Security](security/README.md)
Defense in depth: credential management, audit logging, rate limiting, CSRF, input sanitization, and network controls.

- [Credential Management](security/credential-management.md) — SecureCredential + Vault (AppRole, KV v2)
- [Audit Logging](security/audit-logging.md) — what is logged, the log structure, retention
- [Rate Limiting and CSRF](security/rate-limiting-and-csrf.md) — per-tenant limits, double-submit cookies, security headers
- [Network Security](security/network-security.md) — IP allowlisting, VPN detection, security zones

---

### [CLI and Infrastructure](cli-and-infra/README.md)
The `etherion` CLI and the bare-metal production stack: NixOS, Ansible, systemd, HAProxy, Vault.

- [Commands](cli-and-infra/commands.md) — every command in depth
- [.env Guards](cli-and-infra/dot-env-guards.md) — fail-fast validation before any real work
- [Bare-Metal Stack](cli-and-infra/bare-metal-stack.md) — why this stack, how it fits together
- [NixOS and Ansible](cli-and-infra/nix-and-ansible.md) — deploy, update, scale

---

### [Terminal UI](terminal-ui/README.md)
The Bubble Tea TUI: architecture, tabs, service lifecycle management, and configuration.

- [Architecture](terminal-ui/architecture.md) — Elm Architecture, RootModel, message routing
- [Tabs Reference](terminal-ui/tabs-reference.md) — what each of the 8 tabs does
- [Service Lifecycle](terminal-ui/service-lifecycle.md) — detached process management
- [Configuration](terminal-ui/configuration.md) — config file, binary resolution, cross-platform
