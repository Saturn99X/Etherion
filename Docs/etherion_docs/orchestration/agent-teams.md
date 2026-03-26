# Agent Teams: Composition and Tool Approval

An **AgentTeam** is the binding contract between a set of specialists and a set of tools. This document explains what that contract means and how teams are composed, loaded, and validated.

## What Defines a Team

A team is a database record with these key properties:

```python
class AgentTeam(SQLModel, table=True):
    agent_team_id: str               # Unique ID, e.g., "at_abc123..."
    tenant_id: int                   # Which tenant owns this team
    name: str                        # Human name, e.g., "Sales Analytics"
    description: str                 # What the team does

    custom_agent_ids: str            # JSON list of specialist IDs
    pre_approved_tool_names: str     # JSON list of tool names (strings)

    is_active: bool                  # Can it be used?
    version: str                     # Semantic version (e.g., "1.0.0")
    is_latest_version: bool          # Is this the current version?

    max_concurrent_executions: int   # How many jobs run in parallel
    default_timeout_seconds: int     # Wall-clock limit per job
```

The two fields that matter most are:

1. **`custom_agent_ids`** — A JSON array of specialist definitions the team has access to.
2. **`pre_approved_tool_names`** — A JSON array of tool names (strings) the team is allowed to use.

### Allowed Tool Names vs. Specialist Tools

There's an important distinction:

- **Pre-approved tools** are standard tools registered in the Tool registry (e.g., "search_personal_kb", "web_search"). They're strings representing stable tool implementations.
- **Specialists are also tools** (via wrapping) but they're represented as objects with metadata like `specialist_agent_id`.

When the Team Orchestrator runs, it merges both lists:

```python
# From team_orchestrator.py (simplified)
self.approved_tools = self.team_config.get('approved_tools', [])

# Then, wrap each specialist as a tool
for specialist_agent in specialist_agents:
    tool = agent_to_tool(specialist_executor, name=specialist_agent['name'])
    self.approved_tools.append(tool)
```

The orchestrator then sees a unified list of available tools—both pre-approved tools and specialists—and can invoke them based on need.

## Composing a Team

Let's say you want to create a team called "Content Creation" with two specialists and three tools. Here's the conceptual flow:

### Step 1: Define Specialists

First, create two `CustomAgentDefinition` records:

```python
# Specialist 1: Editor
editor_agent = CustomAgentDefinition(
    custom_agent_id="ca_editor001",
    tenant_id=42,
    name="Content Editor",
    description="Refines and edits written content",
    system_prompt=(
        "You are a professional editor. Your job is to improve clarity, "
        "grammar, and tone. Provide redlined feedback and a polished version."
    ),
    tool_names=json.dumps(["document_reader", "grammar_checker"]),
    model_name="gemini-2.5-flash",
    max_iterations=5,
    timeout_seconds=300,
    temperature=0.1
)
session.add(editor_agent)

# Specialist 2: Researcher
researcher_agent = CustomAgentDefinition(
    custom_agent_id="ca_research001",
    tenant_id=42,
    name="Content Researcher",
    description="Gathers evidence and citations for content",
    system_prompt=(
        "You are a research specialist. Find credible sources, "
        "verify facts, and compile citations in APA format."
    ),
    tool_names=json.dumps(["web_search", "kb_search", "citation_formatter"]),
    model_name="gemini-3-flash-preview",
    max_iterations=8,
    timeout_seconds=600,
    temperature=0.1
)
session.add(researcher_agent)
session.commit()
```

### Step 2: Register Tools

Ensure tools are registered in the Tool table:

```python
from src.database.models import Tool, ToolStatus

tools = [
    Tool(name="document_reader", description="Reads and extracts text from documents", status=ToolStatus.STABLE),
    Tool(name="grammar_checker", description="Checks grammar and style", status=ToolStatus.STABLE),
    Tool(name="web_search", description="Searches the public web", status=ToolStatus.STABLE),
    Tool(name="kb_search", description="Searches tenant knowledge base", status=ToolStatus.STABLE),
    Tool(name="citation_formatter", description="Formats citations", status=ToolStatus.BETA),
]
for tool in tools:
    session.add(tool)
session.commit()
```

### Step 3: Create the Team

```python
team = AgentTeam(
    agent_team_id="at_content_team001",
    tenant_id=42,
    name="Content Creation",
    description="Creates, edits, and researches content with citations",
    is_active=True,
    version="1.0.0",
    is_latest_version=True,
    max_concurrent_executions=3,
    default_timeout_seconds=1800,
)
team.set_custom_agent_ids(["ca_editor001", "ca_research001"])
team.set_pre_approved_tool_names(["document_reader", "grammar_checker", "web_search", "kb_search", "citation_formatter"])
session.add(team)
session.commit()
```

## Loading a Team at Runtime

When a job is assigned to a team, the system loads the team configuration. Here's how:

```python
# From team_orchestrator.py
async def execute_2n_plus_1_loop(self, goal: str, team_config: Dict[str, Any]) -> Dict[str, Any]:
    # Load team configuration from database
    self.team_config = await self._load_team_config(team_config)

    # Enrichment from DB (fail-open, so non-blocking)
    try:
        loader = get_agent_loader()
        loaded = await loader.load_agent_team(
            agent_team_id=self.team_id,
            tenant_id=self.tenant_id,
            job_id=str(team_config.get('job_id')),
            user_id=self.user_id,
        )
        if loaded:
            self.team_config['specialist_agents'] = loaded.get('custom_agents', [])
            self.team_config['approved_tools'] = loaded.get('pre_approved_tools', [])
    except Exception:
        pass  # Fail open: use in-memory config if DB load fails
```

The loader queries the AgentTeam and CustomAgentDefinition tables, extracts the lists, and deserializes them. Each specialist becomes an executor object, and each pre-approved tool name is resolved to its actual LangChain Tool implementation.

## Pre-Approved Tools and Security

The **pre_approved_tool_names** field is the core of the approval system. Here's why it matters:

### Scenario 1: Static Approval

A tenant creates a team and says: "Only these tools are allowed."

```python
team.set_pre_approved_tool_names([
    "web_search",
    "kb_search",
    "document_summarizer",
])
```

Now, any specialist in the team can *request* to use `web_search`, but cannot request `delete_all_documents` (not on the list). If a specialist tries to call an unapproved tool, the orchestrator rejects it.

### Scenario 2: Human-in-the-Loop

For sensitive operations, a tool request enters a **tool approval queue** (Redis-backed). The system creates a request with the tool name, arguments, and job context, then waits for human approval:

```python
# From tool_dispatch.md examples
tool_request_queue = ToolRequestQueue()
request_id = tool_request_queue.enqueue(
    job_id="job_123",
    tool_name="send_email",
    args={"recipient": "user@example.com", "subject": "..."}
)
approved = tool_request_queue.wait_for_approval(request_id, timeout=300)
if approved:
    # Execute the tool
else:
    # Reject and escalate
```

This is configured per-team via the orchestrator profile's `tool_policy`. The Team Orchestrator profile specifies:

```python
tool_policy=ToolApprovalPolicy(
    auto_approved_tools=[
        "search_personal_kb",
        "search_project_kb",
        "confirm_action_tool",
    ],
    manual_review_states=["submitted", "pending_platform_orchestrator"],
    required_reviewers=["platform_orchestrator"],
    fallback_behavior="escalate_to_platform",
)
```

Tools in `auto_approved_tools` are always allowed (if they're in the team's `pre_approved_tool_names`). Others wait for approval.

## Validating Team Configuration

Before a team can run, it must be valid. The database model includes a validation method:

```python
def validate_configuration(self) -> List[str]:
    """Validate the team configuration and return list of validation errors."""
    errors = []

    if not self.name or not self.name.strip():
        errors.append("Team name is required")

    custom_agent_ids = self.get_custom_agent_ids()
    pre_approved_tools = self.get_pre_approved_tool_names()

    if not custom_agent_ids and not pre_approved_tools:
        errors.append("Team must have at least one custom agent or pre-approved tool")

    if len(custom_agent_ids) != len(set(custom_agent_ids)):
        errors.append("Duplicate custom agent IDs found")

    if len(pre_approved_tools) != len(set(pre_approved_tools)):
        errors.append("Duplicate pre-approved tool names found")

    return errors
```

Check this before marking a team as active:

```python
errors = team.validate_configuration()
if errors:
    raise ValueError(f"Team validation failed: {errors}")
team.is_active = True
session.commit()
```

## Versioning Teams

Teams support semantic versioning. When you want to update a team (add a specialist, remove a tool), create a new version:

```python
new_team = old_team.create_new_version(
    new_version="1.1.0",
    version_notes="Added Data Analyst specialist, enabled web_search"
)
session.add(new_team)
session.commit()
```

The old team is marked `is_latest_version=False`, and the new one is marked `True`. At runtime, the system always loads the latest version.

## Execution Context and Isolation

When the Team Orchestrator builds its runtime, it passes the team configuration as part of the execution context:

```python
orchestrator_config = {
    'runtime_profile_name': 'team_orchestrator',
    'execution_context': {
        'user_id': self.user_id,
        'tenant_id': self.tenant_id,
        'team_id': self.team_id,
        'job_id': job_id,
        'approved_tools': self.approved_tools,  # Loaded from team
        'specialist_agents': self.specialist_agents,  # Loaded from team
    },
    'observation_context': user_context,
}
```

This ensures that:

1. **Tenant isolation** — Only agents and tools for this tenant are visible.
2. **Team isolation** — Only specialists in this team are visible.
3. **Audit trail** — The job ID ties all actions back to the original request.

## Summary

- An **AgentTeam** is a database-driven bundle of specialists and tools.
- **custom_agent_ids** lists the specialists; **pre_approved_tool_names** lists the tools.
- Teams are loaded at runtime and merged with user personality observations and KB instructions.
- **Pre-approval** is the security boundary: specialists can only call approved tools.
- Teams support versioning and validation before activation.
- All execution happens within tenant and team isolation boundaries.
