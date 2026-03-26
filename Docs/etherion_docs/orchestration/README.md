# Orchestration in Etherion

Orchestration is the choreography of AI work—how tasks decompose, how agents coordinate, and how decisions cascade through the system. At its core, Etherion's orchestration layer answers three questions:

1. **What needs to happen?** (planning)
2. **Who does it?** (delegation)
3. **Is the result good?** (validation)

This document introduces the three fundamental concepts that make Etherion's orchestration work: **jobs**, **agent teams**, and **specialists**.

## The Three Concepts

### A Job: The Unit of Work

A **job** is a single, user-initiated task. When you send an instruction to Etherion—"analyze this report" or "search for trends in Q3 sales"—you create a job. Every job has:

- A unique ID (`job_id`)
- An associated tenant (user or organization)
- A status lifecycle: `PENDING` → `RUNNING` → `COMPLETED` (or `FAILED`)
- An execution trace—a record of every decision the system made

Jobs live in the database (SQLModel) and are managed by Celery, Etherion's task queue. The job's status feeds back to clients in real-time via Redis pub/sub.

```python
# From src/database/models/job.py (conceptual)
class Job(SQLModel, table=True):
    job_id: str  # UUID identifier
    tenant_id: int  # Multi-tenant isolation
    status: JobStatus  # PENDING, RUNNING, COMPLETED, FAILED
    execution_trace_steps: List[ExecutionTraceStep]  # Complete audit trail
    output_data: Optional[str]  # JSON result (serialized)
    error_message: Optional[str]  # If failed, why
```

### An Agent Team: The Group

An **AgentTeam** is a **collection of specialist agents** plus a **set of pre-approved tools**. Think of it as a consulting firm: the firm (team) has several experts on staff (specialists) and access to a pre-approved toolkit (tools).

AgentTeams are defined at the database level and retrieved at runtime. They allow tenants to partition their AI capabilities: perhaps the "Research Team" gets access to web search and document tools, while the "Data Analysis Team" gets spreadsheet and SQL tools.

```python
# From src/database/models/agent_team.py
class AgentTeam(SQLModel, table=True):
    agent_team_id: str
    tenant_id: int
    name: str  # "Research Team"
    description: str
    custom_agent_ids: str  # JSON list of specialist IDs
    pre_approved_tool_names: str  # JSON list of tool names
    is_active: bool
    max_concurrent_executions: Optional[int] = 5
    default_timeout_seconds: Optional[int] = 1800  # 30 min
```

Each team belongs to exactly one tenant. When a job is assigned to a team, the team orchestrator loads the team's config and invokes the specialists within that team.

### A Specialist: The Expert

A **specialist** is a single LLM agent with a specific purpose. Each specialist has:

- A **system prompt** that defines its expertise ("You are a data analyst...")
- An **allowed tool list** (which tools it can call)
- A **model** (which LLM provider and version to use)
- Configuration (max iterations, timeout, temperature)

```python
# From src/database/models/custom_agent.py
class CustomAgentDefinition(SQLModel, table=True):
    custom_agent_id: str
    tenant_id: int
    name: str  # "Sales Analyst"
    description: str
    system_prompt: str  # Defines its role and constraints
    tool_names: str  # JSON list of tools it can use
    model_name: str  # e.g., "gemini-2.5-flash"
    max_iterations: Optional[int] = 10
    timeout_seconds: Optional[int] = 300
    temperature: Optional[float] = 0.1
```

A specialist is **not** a standalone agent that runs alone. Rather, it's a definition that lives in the database. When a team needs the specialist, the system instantiates it at runtime using `CustomAgentRuntimeExecutor`.

## How They Relate

Here's the hierarchy:

```
Job (user request)
    ↓ assigned to
AgentTeam (e.g., "Research Team")
    ├── Pre-approved Tools (e.g., "web_search", "kb_search")
    └── Specialists (expert agents)
        ├── Specialist 1 (Data Analyst)
        ├── Specialist 2 (Report Writer)
        └── Specialist 3 (Validator)
```

When a job is assigned to a team, the **Team Orchestrator** (a special LLM) takes over. It reads the job's instruction, inspects the team's roster, and decides which specialist to call and what to ask it to do. The specialist responds, the orchestrator validates, and the cycle repeats until the job is complete.

## The Dual Orchestrator Architecture

Etherion actually has *two* orchestrators:

1. **Platform Orchestrator** — Tenant-scoped master planner. Decomposes high-level goals, recommends or creates teams, and hands off work strategically.
2. **Team Orchestrator** — Executes the plan within a single team using the 2N+1 reasoning loop (see `execution-loop.md`).

For most use cases, you'll interact with the Team Orchestrator. The Platform Orchestrator is a future capability for multi-team coordination.

## Why This Design?

**Isolation & Scale**: Each team is isolated by tenant and can be scaled independently. A customer can have 10 specialized teams, each with different tools and constraints.

**Auditability**: Every step is logged. When a tool is called, who called it, and why—it's all recorded in the execution trace.

**Safety**: Pre-approved tools prevent a misbehaving specialist from calling dangerous operations. The tool_request_queue allows human-in-the-loop confirmation for sensitive actions.

**Flexibility**: New specialists can be added without redeploying code. Tenants define their own agents and teams via the API.

## Next Steps

- **Agent Teams**: Understand how to compose and configure teams. See `agent-teams.md`.
- **Execution Loop**: Learn the 2N+1 algorithm that drives specialist execution. See `execution-loop.md`.
- **Specialist Executor**: See what happens inside a single specialist run. See `specialist-executor.md`.
- **Tool Dispatch**: Understand how tools are invoked and approved. See `tool-dispatch.md`.
