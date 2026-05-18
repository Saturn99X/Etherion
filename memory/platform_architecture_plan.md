# Platform Architecture Rebuild Plan

## Current (Broken)
```
User Goal
  → IO (Platform Orchestrator)
      → Dual Search (KB + Web)
      → Create Blueprint
      → Auto-create Team (no user validation)
      → Execute Job via Team Orchestrator  ← WRONG: IO should not execute jobs
      → Return Result
```

## Target Architecture

```
User writes a goal / chats with IO
  → IO (Platform Orchestrator)
      → Can search (web, KB, AI assets) to answer questions
      → Can MANAGE TEAMS:
          - Propose creating a new team → User validates → Created
          - Propose adding/removing tools → User validates → Updated
          - Propose adding/removing agents → User validates → Updated
          - Propose deleting a team → User validates → Deleted
          - Propose updating system instructions → User validates → Updated
      → DOES NOT EXECUTE JOBS

User writes a goal that requires work
  → GoalOrchestrator (separate from IO)
      → Team Orchestrator (bypass_permission or restricted mode)
      → Execute via specialists
      → Return Result
```

## Implementation Steps

### Step 1: Repurpose IO (Platform Orchestrator)
**File:** `src/services/platform_orchestrator.py`

**Remove:**
- `plan_and_execute()` — IO should not execute anything
- `perform_dual_search()` → move to shared utility
- `create_agent_team_blueprint()` → the LLM-based blueprint creation
- `create_blueprint()` method
- All job execution code paths

**Keep/Refactor:**
- `create_agent_team_blueprint()` → renamed to `propose_team_config()` — IO proposes a team config (agents, tools, instructions) but doesn't create it
- `approve_tools_for_team()` → keep as is
- `_identify_required_tools()` → keep
- `load_user_personality_context()` → keep
- `enhanced_system_prompt()` → keep

**New methods:**
- `propose_create_team(specification)` → returns a TeamConfig proposal (name, agents, tools, instructions), does NOT create
- `propose_update_team(team_id, changes)` → returns a diff of proposed changes
- `propose_delete_team(team_id)` → returns deletion impact
- `search_and_chat(query)` → answers user questions using web/KB/assets search, NO team creation
- `execute_proposal(action_type, proposal_id)` → executes a previously validated proposal

### Step 2: Add User Validation Gate
**New file:** `src/services/validation_gate.py`

```python
class ValidationGate:
    """
    Every write/delete operation by IO goes through the Validation Gate.
    The gate:
    1. Stores the proposed action (type, params, impact summary)
    2. Returns a proposal_id + summary to the user
    3. User must explicitly approve (or reject) before execution
    4. Bypass mode: skip user validation (configurable per team/tenant)
    """
    
    PENDING = "pending"
    APPROVED = "approved" 
    REJECTED = "rejected"
    
    async def propose(self, action_type: str, params: dict, proposer: str) -> str:
        """Store proposal, return proposal_id."""
        
    async def approve(self, proposal_id: str, user_id: str) -> bool:
        """User approves → execute the action."""
        
    async def reject(self, proposal_id: str, user_id: str, reason: str) -> bool:
        """User rejects."""
        
    async def get_pending(self, tenant_id: int) -> list:
        """List pending proposals for user review."""
```

**Integration points:**
- Web UI (TUI / frontend) polls `get_pending()` and shows proposal cards
- Each card has Approve/Reject buttons with impact summary
- API endpoint: `approveProposal(id)`, `rejectProposal(id)`, `listProposals()`

### Step 3: Team Orchestrator Modes
**File:** `src/services/orchestration/engine.py`

Add two execution modes:

```python
class ExecutionMode(Enum):
    BYPASS_PERMISSION = "bypass_permission"  # Full access, no approval gates
    RESTRICTED = "restricted"  # Limited tools, approval gates on every write
```

- `bypass_permission` → current behavior (tools auto-approved if in allowlist)
- `restricted` → every tool call requires user approval via ValidationGate

**System prompt changes:**
- In `restricted` mode, append to specialist system prompt:
  "You are in RESTRICTED mode. Every write operation must be approved by the user."
- In `bypass_permission` mode, append:
  "You are in BYPASS mode. Tool calls execute immediately."

### Step 4: Manual Parity
Every IO operation must have a corresponding API mutation:

| IO Action | API Mutation | Status |
|-----------|-------------|--------|
| Propose create team | `createAgentTeam(team_input)` | ✅ Exists |
| Propose update team | `updateAgentTeam(id, changes)` | ❌ Missing |
| Propose delete team | `deleteAgentTeam(id)` | ✅ Exists |
| Propose add tools | `updateAgentTeam(id, tools)` | ❌ Missing |
| Propose remove tools | `updateAgentTeam(id, tools)` | ❌ Missing |
| Propose update instructions | `updateAgentTeam(id, instructions)` | ❌ Missing |

**New mutations needed:**
- `updateAgentTeam(id, name?, description?, specification?, pre_approved_tool_names?)` 
- This already partially exists but needs to support all fields

### Step 5: Remove Job Execution from IO Flow
**File:** `src/services/goal_orchestrator.py`

The current flow:
```python
# Current (wrong):
IO creates blueprint → IO assigns teams → IO plans execution → specialists run
```

The new flow:
```python
# Target:
User submits goal → GoalOrchestrator checks if team exists
  → If team exists: Team Orchestrator executes directly
  → If no team: IO proposes team config → User validates → Create team → Execute
```

Remove the call to `self.platform_orchestrator.create_agent_team_blueprint()` from `GoalOrchestrator.execute()`.
Instead, `GoalOrchestrator` should:
1. Try to find an existing matching team
2. If found, execute directly via Team Orchestrator
3. If not found, return a "no team available" response asking user to configure one

### Step 6: IO as Chat Agent
**New file or integration:** `src/services/io_agent.py`

IO should be exposed as a chat agent that users can talk to. It uses:
- `unified_research_tool` for web searches
- `multimodal_kb_search` for KB searches
- `vector_search_tool` for AI assets search
- Team management proposals (create/update/delete)

IO does NOT have access to job execution tools.
IO does NOT have tool_choice="any" — it can choose to answer without tools.

## Files to Modify

| File | Change |
|------|--------|
| `src/services/platform_orchestrator.py` | Remove job execution, add proposal methods |
| `src/services/goal_orchestrator.py` | Remove IO from execution path |
| `src/services/orchestration/engine.py` | Add bypass/restricted modes |
| `new: src/services/validation_gate.py` | Proposal storage + approval flow |
| `src/services/orchestration/specialist_executor.py` | Read mode from execution context |
| `src/etherion_ai/graphql_schema/mutations.py` | Add updateAgentTeam, approveProposal, rejectProposal |
| `src/etherion_ai/graphql_schema/output_types.py` | Add Proposal type |
| `tui/internal/ui/agents.go` | Show pending proposals, accept/reject UI |
