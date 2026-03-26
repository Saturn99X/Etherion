# Row-Level Security Deep Dive

Row-Level Security (RLS) is Etherion's second line of defense against data leaks. Even if application code has a bug and forgets to filter by `tenant_id`, PostgreSQL's RLS policies enforce the filter at the database layer. This document explains how RLS works and how Etherion implements it.

## What is Row-Level Security?

RLS is a PostgreSQL feature that lets you define policies on tables. These policies automatically filter query results based on the current session context.

**Without RLS**:
```sql
SELECT * FROM conversation;
-- Returns ALL conversations in the entire database
-- If your app has a bug and forgets to add WHERE tenant_id = ?,
-- you get a data leak.
```

**With RLS enabled and a policy in place**:
```sql
SELECT * FROM conversation;
-- PostgreSQL intercepts this query.
-- It sees that app.tenant_id = 42 in the session context.
-- It rewrites the query to: SELECT * FROM conversation WHERE tenant_id = 42;
-- You only get conversations from tenant 42.
-- The bug is contained.
```

The policy is enforced **at the database layer, before results are returned to the application**. This means:

1. No matter what query the application sends, the policy applies
2. The policy cannot be bypassed by changing application code
3. Even prepared statements and ORM libraries respect policies
4. A compromised application server cannot exfiltrate cross-tenant data

## How PostgreSQL RLS Policies Work

A PostgreSQL RLS policy has three parts:

```sql
CREATE POLICY policy_name
  ON table_name
  FOR operation_type  -- SELECT, INSERT, UPDATE, DELETE, or ALL
  USING (expression)  -- Expression that must be true for the row to be visible
  [WITH CHECK (expression)];  -- For INSERT/UPDATE, what's allowed
```

**Example: A policy that hides conversations from other tenants**:

```sql
ALTER TABLE conversation ENABLE ROW LEVEL SECURITY;

CREATE POLICY conversation_isolation
  ON conversation
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::int)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::int);
```

What this does:

- `ENABLE ROW LEVEL SECURITY` — Turn on RLS for this table
- `FOR ALL` — This policy applies to SELECT, INSERT, UPDATE, and DELETE
- `USING (tenant_id = current_setting('app.tenant_id')::int)` — For SELECT and UPDATE/DELETE, the row is visible only if its `tenant_id` matches the session variable `app.tenant_id`
- `WITH CHECK (...)` — For INSERT and UPDATE, you can only insert/update rows where `tenant_id` matches the session variable

The key function: `current_setting('app.tenant_id')` reads a session variable set by the application. The application sets this variable once per request, and PostgreSQL checks it on every row.

## Etherion's RLS Setup

Etherion sets up RLS policies for every entity table. Here's the pattern:

### 1. Enable RLS and create the base policy

For each table with a `tenant_id` column:

```sql
-- For message table
ALTER TABLE message ENABLE ROW LEVEL SECURITY;

CREATE POLICY message_tenant_isolation
  ON message
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::int)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::int);
```

This is replicated for every table: project, conversation, job, custom_agent_definition, etc.

### 2. Set app.tenant_id before queries

Before executing any query, the application calls:

```python
# From src/utils/rls_utils.py
def set_session_tenant_context(session, tenant_id: Optional[int]) -> None:
    """Set app.tenant_id on the session's connection for RLS enforcement."""
    if not _is_postgres_session(session):
        return
    conn = session.connection()
    if tenant_id is not None:
        conn.execute(text("SET app.tenant_id = :tenant_id"),
                     {"tenant_id": str(tenant_id)})
    else:
        conn.execute(text("SELECT set_config('app.tenant_id', NULL, false)"))
```

This runs `SET app.tenant_id = 42` on the database connection. PostgreSQL stores this value in the session context and makes it available to all subsequent queries on that connection.

**Critical detail**: The function uses `session.connection()` to get the actual database connection. This ensures that the SET command runs on the same connection that will execute the queries. If you ran SET on a different connection, it wouldn't affect the query.

### 3. Application middleware enforces the pattern

In a typical Etherion API request:

```python
@app.post("/api/conversations")
async def create_conversation(request: Request, db: Session = Depends(get_db)):
    # 1. Extract tenant_id from request context (JWT, OAuth, headers)
    tenant_id = extract_tenant_id(request)

    # 2. Set the RLS context IMMEDIATELY
    set_session_tenant_context(db, tenant_id)

    # 3. Now all queries run with RLS active
    projects = db.query(Project).all()  # Only user's projects

    # 4. Create new conversation (RLS enforces it's for this tenant)
    new_conversation = Conversation(
        project_id=project.id,
        tenant_id=tenant_id,
        title="New chat"
    )
    db.add(new_conversation)
    db.commit()

    return {"conversation_id": new_conversation.id}
```

The flow:

1. Extract `tenant_id` from the request (from JWT claims, OAuth subject, headers, etc.)
2. **Immediately** call `set_session_tenant_context(db, tenant_id)`
3. All subsequent database operations are RLS-protected
4. User can only see/create/update data for their tenant

## Defense in Depth: Why This Matters

Let's walk through a vulnerability scenario:

### Scenario: A GraphQL resolver with a bug

Developer writes a resolver that lists all conversations (forgets to filter):

```python
# BAD CODE - MISSING TENANT FILTER
def resolve_all_conversations(obj, info):
    # get_db_session() returns a session where RLS is already enabled
    session = get_db_session()

    # Intentionally missing: .filter(Conversation.tenant_id == current_user.tenant_id)
    return session.query(Conversation).all()  # ← BUG: No filter!
```

**Without RLS**: This query returns every conversation in the database. If Tenant A has 100 conversations and Tenant B has 50, this returns 150. Data leak!

**With RLS in place**:

1. Request arrives from Tenant A user
2. Middleware extracts `tenant_id = A` from the JWT
3. Middleware calls `set_session_tenant_context(session, A)`
4. PostgreSQL receives: `SET app.tenant_id = A`
5. Developer's buggy resolver runs: `SELECT * FROM conversation;`
6. PostgreSQL intercepts the query
7. PostgreSQL rewrites it to: `SELECT * FROM conversation WHERE tenant_id = A;`
8. Only Tenant A's conversations are returned

The bug still exists (and should be fixed!), but RLS contained the damage.

### Why both application filtering AND RLS?

You might wonder: "If RLS is so secure, why also filter in application code?"

**Answer**: Defense in depth. RLS is your nuclear option, but it has limitations:

1. **Performance** — RLS policies add overhead. For a single tenant, checking RLS on every row is slower than filtering in the WHERE clause. Application filtering is more efficient.
2. **Debugging** — RLS errors can be mysterious ("why are my joins returning empty?"). Application filters make the intent clear.
3. **Testing** — Unit tests often don't set up RLS. Explicit filters make tests pass without a test database.
4. **Redundancy** — If RLS has a bug, application filters still protect you. If application code has a bug, RLS protects you.

## RLS and Complex Queries

RLS plays well with joins. Let's trace a multi-table query:

```python
# Get all messages in a user's conversations
messages = db.query(Message)\
    .join(Conversation)\
    .join(Project)\
    .where(Project.user_id == current_user.id)\
    .all()
```

When this query runs:

1. `set_session_tenant_context(db, current_user.tenant_id)` has been called
2. PostgreSQL sees `SELECT ... FROM message JOIN conversation JOIN project WHERE project.user_id = ?;`
3. RLS policies on each table activate:
   - Message policy: rows must have `tenant_id = current_user.tenant_id`
   - Conversation policy: rows must have `tenant_id = current_user.tenant_id`
   - Project policy: rows must have `tenant_id = current_user.tenant_id`
4. PostgreSQL applies all three policies, ensuring only rows matching the user's tenant are joined

The result: even if the WHERE clause is wrong, RLS still prevents leaks.

## RLS and Inserts

RLS also protects INSERT operations using `WITH CHECK`:

```sql
CREATE POLICY message_isolation
  ON message
  FOR INSERT
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::int);
```

When application code tries to insert:

```python
new_message = Message(
    conversation_id=conv_id,
    tenant_id=42,  # ← What if someone maliciously set this?
    content="Hello"
)
db.add(new_message)
db.commit()
```

PostgreSQL checks: Does the row's `tenant_id` (42) equal `current_setting('app.tenant_id')`?

If RLS context is 99, the INSERT fails. If RLS context is 42, it succeeds. The database enforces that you can only insert records for your own tenant.

## RLS and Async Operations

Etherion uses async jobs. Here's how RLS works with async:

```python
# In a request handler
@app.post("/api/jobs")
async def create_job(request: Request, db: AsyncSession = Depends(get_async_db)):
    tenant_id = extract_tenant_id(request)

    # Set RLS for this request
    await set_session_tenant_context_async(db, tenant_id)

    # Create job
    job = Job(
        tenant_id=tenant_id,
        user_id=current_user.id,
        status=JobStatus.QUEUED
    )
    db.add(job)
    await db.commit()

    # IMPORTANT: Job is now in the queue. The application will process it later.
    # When the async worker picks up the job, it must also set RLS context!
```

The key: **Each database session must set its own RLS context**. When the async worker fetches the job, it does:

```python
# In worker code
async def process_job(job_id: str):
    # Get a new database session
    db = get_async_session()

    # Look up the job
    job = await db.get(Job, job_id)  # This query is not RLS-filtered yet

    # Set RLS to the job's tenant
    await set_session_tenant_context_async(db, job.tenant_id)

    # Now all queries are RLS-filtered
    conversations = await db.execute(
        select(Conversation).where(Conversation.tenant_id == job.tenant_id)
    )
```

Note: The initial lookup of the job by job_id is not RLS-filtered. This is OK because `job_id` is globally unique and opaque (e.g., "job_aBcDeFgHiJkLmNo"), so you can't guess other tenants' job IDs. But once the job is loaded, we immediately set RLS context.

## Common Pitfalls

### Pitfall 1: Forgetting to set RLS context

```python
# BAD
session = get_db_session()
projects = session.query(Project).all()  # ← RLS context not set!
```

If RLS is enabled on the project table, this query might fail or return empty results because `current_setting('app.tenant_id')` is NULL.

**Fix**: Always set context before queries:

```python
# GOOD
session = get_db_session()
set_session_tenant_context(session, tenant_id)
projects = session.query(Project).all()
```

### Pitfall 2: Setting context on the wrong connection

```python
# BAD
session = get_db_session()
set_session_tenant_context(session, tenant_id)  # Sets on session A

# Different session created later
session_b = get_db_session()
projects = session_b.query(Project).all()  # ← session_b has no RLS context!
```

Connection pools can reuse connections, but `SET` is session-specific. If you create a new session later, you must set RLS context again.

**Fix**: Set context immediately after getting a session:

```python
session = get_db_session()
set_session_tenant_context(session, tenant_id)
# Use session for all operations
```

### Pitfall 3: Mixing RLS contexts

```python
# BAD
session = get_db_session()
set_session_tenant_context(session, tenant_id=100)

# Later, forget to update context
set_session_tenant_context(session, tenant_id=200)

# Even later, still using the session
projects = session.query(Project).all()  # ← Which tenant is this filtered for?
```

**Fix**: In FastAPI or other frameworks, context is typically per-request. A new request gets a new session with a fresh context.

### Pitfall 4: RLS policies on one table but not others

```sql
-- Created policy on Project
CREATE POLICY project_isolation ON project FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::int);

-- Forgot to create policy on Message
-- (No RLS on Message table!)
```

Now a developer can do:

```python
# This is RLS-protected
projects = db.query(Project).all()

# But this is NOT
messages = db.query(Message).all()  # ← No RLS filter!
```

**Fix**: Ensure every table with `tenant_id` has an RLS policy. Use migrations to audit this.

## Testing RLS

Testing RLS requires a real PostgreSQL database (not SQLite). Here's a pattern:

```python
# tests/test_rls.py
import pytest
from sqlalchemy import select

@pytest.mark.asyncio
async def test_rls_prevents_cross_tenant_access():
    # Create two sessions (two database connections)
    async with async_sessionmaker() as db_a:
        async with async_sessionmaker() as db_b:

            # Tenant A sets context
            await set_session_tenant_context_async(db_a, tenant_id=1)

            # Tenant B sets context
            await set_session_tenant_context_async(db_b, tenant_id=2)

            # Insert data as Tenant A
            project_a = Project(name="Tenant A Project", tenant_id=1)
            db_a.add(project_a)
            await db_a.commit()

            # Try to query as Tenant B
            result = await db_b.execute(select(Project))
            projects_b_sees = result.scalars().all()

            # RLS should prevent Tenant B from seeing Tenant A's project
            assert len(projects_b_sees) == 0
```

## Migration: Enabling RLS

When adding RLS to an existing table, use an Alembic migration:

```python
# migrations/versions/add_rls_to_conversation.py
from alembic import op

def upgrade():
    # Enable RLS
    op.execute("ALTER TABLE conversation ENABLE ROW LEVEL SECURITY;")

    # Create policy
    op.execute("""
        CREATE POLICY conversation_tenant_isolation
        ON conversation
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id')::int)
        WITH CHECK (tenant_id = current_setting('app.tenant_id')::int);
    """)

def downgrade():
    # Remove policy
    op.execute("DROP POLICY conversation_tenant_isolation ON conversation;")

    # Disable RLS
    op.execute("ALTER TABLE conversation DISABLE ROW LEVEL SECURITY;")
```

## Summary: RLS in Etherion

1. **Every table with `tenant_id` has an RLS policy** that filters by tenant
2. **Before each database operation, middleware calls `set_session_tenant_context()`** to set `app.tenant_id` on the connection
3. **PostgreSQL enforces the policy at the database layer**, regardless of application code
4. **Even a bug in application code cannot leak cross-tenant data** because the database layer is the final enforcer
5. **Both application filtering and RLS are used** for defense in depth and performance

RLS is the reason Etherion's multi-tenant architecture is secure by default. It's not about trusting developers; it's about making sure the database itself prevents data leaks.
