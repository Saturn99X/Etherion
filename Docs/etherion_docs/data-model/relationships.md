# Entity Relationships: The Ownership Map

Understanding how entities relate to each other is critical for both schema design and security. In Etherion, relationships follow a strict ownership chain: **Tenant → Owner → Owned Resource**. This document visualizes that chain and explains the reasoning.

## The Ownership Chain

Every piece of data in Etherion traces ownership back to a Tenant:

```
Tenant (root container)
├── User (belongs to exactly one Tenant)
├── Project (owned by User, scoped to Tenant)
│   ├── Conversation (belongs to Project, scoped to Tenant)
│   │   ├── Message (belongs to Conversation, scoped to Tenant)
│   │   └── MessageArtifact (attached to Message, scoped to Tenant)
│   └── ProjectKBFile (belongs to Project, scoped to Tenant)
├── Thread (long-running conversation, scoped to Tenant)
│   ├── ThreadMessage (belongs to Thread, scoped to Tenant)
│   │   └── MessageArtifact (attached to ThreadMessage, scoped to Tenant)
│   └── ToolInvocation (tool calls in Thread, scoped to Tenant)
├── Job (async task, owned by User, scoped to Tenant)
│   └── ExecutionCost (billing for Job, scoped to Tenant)
│   └── ExecutionTraceStep (reasoning trace for Job, scoped to Tenant)
├── CustomAgentDefinition (user-defined agent, scoped to Tenant)
├── AgentTeam (collection of agents, scoped to Tenant)
├── Expense (spending record, owned by User, scoped to Tenant)
├── ExecutionCost (billing, scoped to Tenant)
├── UserObservation (behavioral data, owned by User, scoped to Tenant)
├── ToneProfile (communication preferences, owned by User, scoped to Tenant)
├── TenantInvite (signup token, scoped to Tenant)
├── IPAddressUsage (rate limiting, optional Tenant)
└── CreditLedger (account balance, owned by User, scoped to Tenant)
```

Notice the pattern: **every entity either owns resources or is owned by one**. There are no cross-tenant relationships. No Job belongs to two Tenants. No Project references a Conversation from a different Tenant.

## Detailed Relationships

### Tenant → User

```
Tenant (1) ──────── (N) User
```

**Type**: One-to-many. A Tenant has many Users; each User belongs to exactly one Tenant.

**Foreign key**: `user.tenant_id` → `tenant.id`

**Meaning**: When a User is created, they must specify which Tenant they join. A user cannot exist outside a tenant, and cannot span multiple tenants. To have the same person in two tenants, create two separate User records.

**In code**:
```python
# From src/database/ts_models.py
class User(SQLModel, table=True):
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    tenant: Tenant = Relationship(back_populates="users")
```

### Tenant → Project

```
Tenant (1) ──────── (N) Project
User (1) ────────── (N) Project
```

**Type**: One-to-many (twice). A Tenant has many Projects; a User has many Projects. Each Project has one owner User and belongs to one Tenant.

**Foreign keys**:
- `project.tenant_id` → `tenant.id`
- `project.user_id` → `user.id`

**Meaning**: Projects group conversations and knowledge base files. A Project is always created by a User and scoped to that User's Tenant. Two users in different tenants cannot both own the same project.

**In code**:
```python
class Project(SQLModel, table=True):
    name: str
    user_id: int = Field(foreign_key="user.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
```

### Project → Conversation

```
Project (1) ──────── (N) Conversation
Tenant (1) ───────── (N) Conversation
```

**Type**: Conversations belong to a Project and are scoped to a Tenant.

**Foreign keys**:
- `conversation.project_id` → `project.id`
- `conversation.tenant_id` → `tenant.id` (for RLS efficiency)

**Meaning**: When you start a new chat session, you create a Conversation within a Project. All conversations in Etherion belong to exactly one project. The redundant `tenant_id` field allows queries like "get all conversations in this tenant" without joining through Project.

**In code**:
```python
class Conversation(SQLModel, table=True):
    project_id: int = Field(foreign_key="project.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
```

### Conversation → Message

```
Conversation (1) ──────── (N) Message
Tenant (1) ────────────── (N) Message
```

**Type**: Messages are turns in a Conversation.

**Foreign keys**:
- `message.conversation_id` → `conversation.id`
- `message.tenant_id` → `tenant.id`

**Meaning**: Every message belongs to exactly one conversation. When you delete a conversation, all its messages should be deleted (via foreign key cascade). The `tenant_id` field ensures RLS filtering.

**In code**:
```python
class Message(SQLModel, table=True):
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    role: str  # 'user', 'assistant', 'system'
    content: str
```

### Thread & ThreadMessage (Alternative Structure)

```
Tenant (1) ──────── (N) Thread
Thread (1) ─────── (N) ThreadMessage
```

**Type**: ThreadMessage is a more sophisticated message structure, supporting branching.

**Foreign keys**:
- `thread.tenant_id` → `tenant.id`
- `threadmessage.thread_id` → `thread.thread_id`

**Meaning**: Threads are an evolution of Conversations. They support branching (parent_id, branch_id) for exploring alternative reasoning paths. ThreadMessage can have a `parent_id` to form a tree structure.

### Thread → ToolInvocation

```
Thread (1) ──────── (N) ToolInvocation
ThreadMessage (1) ─ (N) ToolInvocation
```

**Type**: Tool invocations are logged when an agent calls external tools.

**Meaning**: Each tool call is recorded with its parameters, status, result, and cost. This creates an audit trail and enables billing.

### Job Relationships

```
Tenant (1) ──────── (N) Job
User (1) ────────── (N) Job
```

**Type**: Jobs are async execution tasks.

**Foreign keys**:
- `job.tenant_id` → `tenant.id`
- `job.user_id` → `user.id`

**Meaning**: Each job is initiated by a User and scoped to their Tenant. The job can reference a `thread_id` to stream progress back to a conversation.

**In code**:
```python
class Job(SQLModel, table=True):
    job_id: str = Field(unique=True, index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    status: JobStatus
    job_type: str
```

### Job → ExecutionCost

```
Job (1) ──────────── (N) ExecutionCost
```

**Type**: Each job generates one or more ExecutionCost records (one per API call).

**Meaning**: When a job calls Claude or GPT-4, a cost is recorded. The ExecutionCost table is the source of truth for billing.

### Agent Relationships

```
Tenant (1) ────── (N) CustomAgentDefinition
Tenant (1) ────── (N) AgentTeam
```

**Type**: Agents and teams belong to a Tenant.

**Meaning**: Each tenant can define their own agents and teams. Agents are not shared across tenants.

**Agent versioning**:

CustomAgentDefinition and AgentTeam both support versioning:
- `version` — Semantic version (e.g., "1.0.0", "2.1.3")
- `parent_version` — Which version this one was derived from
- `is_latest_version` — Whether this is the current version

This creates a version history graph:

```
Agent v1.0.0 (latest=true)
  ↑
  └─ Agent v1.1.0 (parent_version="1.0.0", latest=true)
       └─ Agent v1.2.0 (parent_version="1.1.0", latest=true)
```

### Team Membership

AgentTeam doesn't use a separate junction table. Instead:

```
AgentTeam.custom_agent_ids = "[ca_abc123, ca_def456, ca_ghi789]"  # JSON list
AgentTeam.pre_approved_tool_names = "[web_search, database_query]"  # JSON list
```

This is a denormalization choice: rather than a `team_agent` join table, we store the list as JSON. It simplifies queries ("get all agents in a team") and avoids an extra table.

### File Storage Relationships

```
Project (1) ────── (N) ProjectKBFile
Tenant (1) ─────── (N) ProjectKBFile
Message (1) ────── (N) MessageArtifact
ThreadMessage (1) ─ (N) MessageArtifact
```

**Type**: Files are attached to projects (KB files) or messages (artifacts).

**Meaning**: ProjectKBFile stores documents in a project's knowledge base. MessageArtifact stores rich media attached to specific messages (images, code, files). Both reference external storage (MinIO, S3) via `file_uri` or `payload_ref`, not raw data in the database.

### User Observation Relationships

```
Tenant (1) ──────── (N) UserObservation
User (1) ────────── (N) UserObservation
```

**Type**: Each user has one primary observation record, updated over time.

**Meaning**: The system learns about a user's preferences and behavioral patterns. Rather than creating a new record per observation, a single UserObservation row is updated with incrementing counts and timestamps.

## Referential Integrity: The Cascade Chain

When you delete a Tenant, PostgreSQL's foreign key constraints create a cascade:

```
DELETE Tenant → CASCADE DELETE User
             → CASCADE DELETE Project (via user)
             → CASCADE DELETE Conversation (via project)
             → CASCADE DELETE Message (via conversation)
             → CASCADE DELETE Job
             → CASCADE DELETE CustomAgentDefinition
             → etc.
```

This is **not** explicitly defined in code; it emerges from the foreign key structure. The database enforces it. If an application bug tries to delete a Tenant without first deleting its Users, the database rejects it.

However, in practice, Etherion uses **soft deletes** for most entities. Rather than:

```sql
DELETE FROM custom_agent_definition WHERE custom_agent_id = 'ca_abc123';
```

It uses:

```sql
UPDATE custom_agent_definition
SET is_deleted = true, deleted_at = NOW()
WHERE custom_agent_id = 'ca_abc123';
```

This preserves the audit trail and avoids cascade deletions. Queries add `WHERE is_deleted = false` to filter out soft-deleted rows.

## ER Diagram: Text-based ASCII

Here's a complete ASCII diagram of the major entity relationships:

```
┌─────────────────────────────────────────────────────────────────────┐
│                            TENANT                                   │
│  (id, tenant_id, subdomain, name, admin_email, is_active, ...)    │
└──────────────┬──────────────────────────────────────────────────────┘
               │
        ┌──────┴──────┬──────────────┬───────────────┬──────────────┐
        │             │              │               │              │
    ┌───▼────┐   ┌───▼─────┐   ┌───▼──────┐   ┌───▼────┐   ┌───▼─────┐
    │  USER  │   │ PROJECT  │   │   THREAD │   │   JOB  │   │CUSTOM   │
    │        │   │          │   │          │   │        │   │AGENT    │
    └────┬───┘   └───┬──────┘   └───┬──────┘   └────┬───┘   └────┬────┘
         │           │              │               │            │
    ┌────▼─────┐ ┌───▼────────┐ ┌──▼──────────┐ ┌──▼────────┐ ┌─▼────┐
    │EXPENSE   │ │CONVERSATION│ │THREAD       │ │EXECUTION  │ │AGENT  │
    │          │ │            │ │MESSAGE      │ │COST       │ │TEAM   │
    └──────────┘ └───┬────────┘ └──┬──────────┘ └───────────┘ └───────┘
                     │             │
              ┌──────▼─────┐   ┌───▼──────────┐
              │  MESSAGE   │   │TOOL          │
              │            │   │INVOCATION    │
              └──────┬──────┘   └──────────────┘
                     │
              ┌──────▼──────────┐
              │MESSAGE          │
              │ARTIFACT         │
              └─────────────────┘

              ALSO ATTACHED TO:
              - ProjectKBFile (to Project)
              - UserObservation (to User)
              - ToneProfile (to User)
              - TenantInvite (to Tenant)
              - IPAddressUsage (optional Tenant/User)
              - CreditLedger (to Tenant, User)
```

## Query Patterns: Following the Chain

Here's how queries typically follow the ownership chain:

**Get all messages in a tenant**:
```sql
SELECT m.* FROM message m
WHERE m.tenant_id = ?;
```

**Get all messages in a user's projects**:
```sql
SELECT m.* FROM message m
JOIN conversation c ON m.conversation_id = c.id
JOIN project p ON c.project_id = p.id
WHERE p.user_id = ?;
```

**Get all costs for a tenant's jobs**:
```sql
SELECT ec.* FROM execution_cost ec
JOIN job j ON ec.job_id = j.job_id
WHERE ec.tenant_id = ?;
```

Notice: queries always include a `tenant_id` filter (either direct or via join). This is how RLS policies know what data is visible.

## Index Strategy

For efficient queries, Etherion indexes:

1. **Tenant ID on every table** — `tenant_id` is indexed for fast filtering
2. **Foreign key columns** — `user_id`, `project_id`, etc., are indexed for joins
3. **Status fields** — `job.status`, `projectkbfile.status` for filtering by state
4. **Timestamps** — `created_at`, `last_activity_at` for time-range queries
5. **Unique identifiers** — `job_id`, `custom_agent_id` for lookup

The result: even on large tenants with millions of records, queries filter down efficiently to just the relevant rows.

---

## Summary

The relationship structure in Etherion is deliberately simple:

- **No cycles** — All relationships flow from Tenant down
- **Consistent foreign keys** — Every child has `tenant_id` for RLS
- **Clear ownership** — Project belongs to User, Job belongs to User, etc.
- **Efficient indexes** — Common query patterns are fast
- **Audit trails** — Timestamps and soft deletes preserve history

This design makes the system secure by default, because the database structure itself enforces isolation. A bug in application code might forget to check permissions, but the database won't let that bug leak cross-tenant data.
