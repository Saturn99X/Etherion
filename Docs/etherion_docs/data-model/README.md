# Etherion Data Model Overview

Welcome to the Etherion data model documentation. This guide explains how data is organized in the platform, the architectural decisions behind it, and how the system ensures that tenant data stays isolated even if a bug creeps into application code.

## Why PostgreSQL?

Etherion uses PostgreSQL as its primary data store. This choice matters because PostgreSQL gives us two critical capabilities we build the entire isolation story around:

1. **Foreign keys and referential integrity** — Ensuring that every record in the system belongs to exactly one tenant through an unbroken chain of ownership.
2. **Row-Level Security (RLS)** — A database-native enforcement mechanism that prevents data leaks at the SQL layer, before application code even runs.

When you query a user's projects in Etherion, you're not relying on the application developer to remember to filter by `tenant_id`. Instead, PostgreSQL's RLS policies physically prevent rows from being returned unless the session has been granted permission.

## The Ownership Chain: Tenant → Everything

Every entity in Etherion traces its ownership back to a single **Tenant**. Think of a tenant as an isolated workspace — perhaps a company with its own ChatGPT-like instance. Here's the ownership structure:

```
Tenant (the root container)
  ├─ User (members of this tenant only)
  ├─ Project (owned by a user, scoped to tenant)
  │   ├─ Conversation (scoped to project → tenant)
  │   │   ├─ Message (scoped to conversation → tenant)
  │   │   └─ MessageArtifact (attached to message → tenant)
  │   └─ ProjectKBFile (knowledge base files)
  ├─ Job (async work execution)
  ├─ CustomAgentDefinition (user-defined agents)
  ├─ AgentTeam (groups of agents)
  ├─ Thread & ThreadMessage (long-running conversations)
  ├─ ExecutionCost (billing per operation)
  └─ UserObservation (behavioral data about users)
```

Every single record has a `tenant_id` field. **This is not optional.** If you're designing a new entity, it must have `tenant_id` as a foreign key to `tenant.id`. No exceptions.

## What Does RLS Provide?

Row-Level Security is a PostgreSQL feature that acts as a second line of defense. When enabled, it ensures that:

- A query like `SELECT * FROM project;` will **only return rows where `tenant_id` matches the current session's context**.
- Even if application code forgets to add a `WHERE tenant_id = ?` clause, the database silently filters the results.
- A user from Tenant A physically cannot read, modify, or delete data belonging to Tenant B.

Here's the critical insight: **RLS policies are enforced after authentication, before results are returned**. They live at the database layer, not the application layer. This means a bug in GraphQL resolvers or API handlers cannot inadvertently leak cross-tenant data.

## How Etherion Uses RLS: The `SET app.tenant_id` Pattern

Etherion uses a specific pattern to enable RLS:

```python
# Before executing any query, set the tenant context:
from src.utils.rls_utils import set_session_tenant_context

session = get_db_session()
set_session_tenant_context(session, tenant_id=42)

# Now any query runs with tenant_id=42 as the "current tenant"
projects = session.query(Project).all()  # Returns only projects where tenant_id=42
```

This pattern works because:

1. The app extracts the tenant ID from the request (via JWT, OAuth, headers, etc.)
2. **Before any database operation**, it calls `set_session_tenant_context(session, tenant_id)`
3. This executes: `SET app.tenant_id = 42` on the database connection
4. PostgreSQL stores this value in the session's config and RLS policies consult it
5. Every subsequent query runs with that context active

The pattern lives in `/home/saturnx/langchain-app/src/utils/rls_utils.py` and includes both sync and async versions.

## Why Even a Bug Can't Leak Data

Let's walk through a vulnerability scenario:

**Scenario**: A developer writes a GraphQL resolver that forgets to filter by tenant_id:

```python
# BAD: Missing tenant_id filter
def resolve_all_conversations(obj, info):
    session = get_db_session()
    return session.query(Conversation).all()  # ← No filter!
```

**Without RLS**, this returns every conversation in the database — a data breach.

**With Etherion's RLS**:

1. The API handler extracts `tenant_id` from the request context
2. It calls `set_session_tenant_context(session, 42)`
3. The developer's resolver runs the bad query
4. PostgreSQL's RLS policy intercepts the query and adds an implicit `WHERE tenant_id = 42`
5. Only conversations belonging to tenant 42 are returned

The bug still exists (and should be fixed!), but the damage is contained by the database itself.

## Data Integrity: Foreign Keys and Ownership

RLS protects access, but **foreign keys protect correctness**. Every relationship in Etherion uses explicit foreign key constraints:

```sql
-- Example: Every Project belongs to exactly one Tenant
ALTER TABLE project
ADD CONSTRAINT fk_project_tenant
FOREIGN KEY (tenant_id) REFERENCES tenant(id);

-- And Project must be owned by a User in that same Tenant
ALTER TABLE project
ADD CONSTRAINT fk_project_user
FOREIGN KEY (user_id) REFERENCES "user"(id);
```

This means:
- You cannot create a Project without a valid `tenant_id`
- You cannot orphan a Project by deleting its Tenant
- Referential integrity is enforced at the database level, not in code

## The Entities: A Quick Map

- **Tenant** — An isolated workspace (company, organization, etc.)
- **User** — A human who belongs to exactly one Tenant
- **Project** — A logical grouping owned by a User
- **Conversation** — A chat session inside a Project
- **Message** — A single turn in a Conversation (user, assistant, or system)
- **Job** — An async execution task (agent runs, background work)
- **CustomAgentDefinition** — A user-configured AI agent
- **AgentTeam** — A collection of agents with pre-approved tools
- **Thread & ThreadMessage** — Long-running conversation threads (for streaming, tool calls)
- **ExecutionCost** — Billing record for a Job's API calls
- **UserObservation** — Behavioral patterns learned about a User

Each entity is documented in detail in the following files.

## Reading This Documentation

1. **entities.md** — Understand each entity's purpose, fields, and why those fields exist
2. **relationships.md** — See the ER diagram and understand how ownership works
3. **rls-deep-dive.md** — Learn how RLS is configured and why it matters

By the end, you'll understand not just what data is stored, but *why* it's stored that way and *how* it's protected.
