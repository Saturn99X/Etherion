# Agent-First Contribution Guide

**Welcome to Etherion.** This is not a typical open source project. The platform is built by AI agents, for AI agents — and all contributors are expected to follow the same standard.

---

## The Core Principle: No Incomplete Context

The single biggest source of bugs in AI-assisted development is **incomplete context**. An agent that doesn't fully understand the system will hallucinate, break existing integrations, and produce code that looks right but isn't. We've solved this by maintaining exhaustive documentation that captures every architectural decision.

Reading that documentation is not optional.

---

## Required Reading Before ANY Contribution

Before writing a single line of code, your AI agent **must** read:

1. **`Z/tech.md`** — Complete technical architecture. Start here.
2. **`Docs/etherion_docs/guide.md`** — Structured documentation index across all 12 platform areas.
3. **The 3 most recent files in `Logs/Daily/`** — Current state and recent decisions.

If you're working on a specific area, also read the relevant `Docs/etherion_docs/{area}/` files.

---

## Contribution Workflow

### Step 1: Gather Context (mandatory)

```
1. Read Z/tech.md in full
2. Read Docs/etherion_docs/guide.md
3. Read 3 most recent Logs/Daily/ entries
4. Search Logs/ for prior work on the area you're touching
```

### Step 2: Make Your Changes

- Follow the exact architectural patterns documented in `tech.md`
- Every line must be production-ready — no placeholders, no TODOs, no mock data
- Test locally against real services (not mocks)
- All tests must pass

### Step 3: Document Your Work (mandatory)

Every PR must include **both**:

#### A) `Z/tech.md` update

Add a section documenting your changes:

```markdown
## X.Y) Feature Name (YYYY-MM-DD)

### A) What changed
### B) Why it changed
### C) Integration points
```

#### B) Contribution log

Create `Logs/Daily/<your-email>`:

```markdown
# Contribution Log: [Feature Name]

**Date**: YYYY-MM-DD
**Contributor**: @yourgithub

## Context
What problem were you solving?

## Files Affected
- path/to/file.py — what changed

## Technical Explanation
How does it work?

## Reasoning
Why these choices? What alternatives were considered?

## Testing
What was tested and how?

## tech.md Updates
Which section(s) were added/updated?
```

### Step 4: Submit PR

PR description must include:
- Link to your contribution log
- Summary of `tech.md` updates
- Confirmation that required context files were read

---

## PR Checklist

- [ ] Read `Z/tech.md` completely
- [ ] Read `Docs/etherion_docs/guide.md`
- [ ] Read 3 most recent `Logs/Daily/` files
- [ ] Created `Logs/Daily/<email>` log
- [ ] Updated `Z/tech.md` with architectural changes
- [ ] All tests pass locally
- [ ] No secrets, credentials, or hardcoded values in code

---

## Code Quality Standards

### Non-negotiable rules

**Never write placeholder code.** Every line must be production-ready. If you don't have what you need to write it correctly, stop and ask.

**Never write static or mock data** outside of tests.

**Never write TODO implementations.** Either implement it fully or don't include it.

**Never guess.** If something is unclear, search the codebase and logs. If still unclear, ask in the issue before touching it.

### Security

- Never commit secrets, API keys, or credentials
- Never hardcode domain names or project IDs — use env vars
- Follow the security patterns in `Z/tech.md` (auth, RLS, CSRF, rate limiting)
- OAuth apps are registered by the operator — never embed any OAuth credentials in code

---

## Architecture Principles

These guide all development decisions:

### Multi-Tenant by Design
Every table has Row-Level Security. Every query is tenant-scoped. The database enforces isolation — application bugs cannot cause cross-tenant leaks.

### Goal-Oriented, Not Task-Oriented
The Orchestrator receives a goal and handles decomposition. Contributors should never break this abstraction by exposing internal task structure to users.

### Asynchronous Execution
Long-running work happens in Celery workers. The API is fast and non-blocking. Jobs are tracked in the database via the checklist system.

### Operator Ownership
The platform runs on the operator's infrastructure. No centralized credentials, no SaaS dependencies, no telemetry. All integrations use env-var-configured credentials that the operator registers with each provider themselves.

### Agent-First Everything
The platform is built by agents, for agents. When building a new feature, ask: "could an AI agent use this safely and correctly?" If not, redesign it.

---

## Common Patterns

### Database access (always use scoped sessions — RLS is automatic)

```python
from src.database.db import get_scoped_session

async with get_scoped_session() as session:
    result = await session.execute(query)
    # tenant_id set automatically via SET LOCAL app.tenant_id
```

### Redis Pub/Sub (for live updates)

```python
from src.core.redis import get_redis_client

redis = get_redis_client()
await redis.publish(f"job_trace_{job_id}", {
    "type": "SPECIALIST_START",
    "specialist": "research_agent",
    "timestamp": datetime.utcnow().isoformat()
})
```

### OAuth credential resolution (never hardcode — always env vars)

```python
# silo_oauth_service.py pattern
client_id = self._env(["OAUTH_GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_ID"])
# Returns first non-empty value from the list, or None
```

---

## Testing Requirements

### Unit tests
- Test business logic in isolation
- Mock LLM calls and external HTTP in unit tests only
- Use pytest fixtures for common setup

### Integration tests
- Test against real running services (Postgres, Redis, MinIO)
- Verify full end-to-end flows through the API
- Never mock the database in integration tests

---

## High-Value Contribution Areas

- Core orchestration improvements (parallelism, fault tolerance)
- New MCP tool integrations
- Knowledge base enhancements (retrieval quality, ingest pipelines)
- Performance and concurrency optimisations
- Security hardening
- Frontend features (Next.js / LobeChat integration)

See `ROADMAP.md` for specific items marked as "Help Wanted".

---

## Questions

Open an issue with the `question` label. Include:
- Which section of `tech.md` or `Docs/` you read
- What specifically is unclear
- What you've already tried

Vague questions ("how does the auth work?") will be redirected to `Z/tech.md`.
Specific questions ("section 3.2 says X but the code does Y — which is correct?") get answered fast.

---

**Email**: [architect@etherionai.com](mailto:architect@etherionai.com)
