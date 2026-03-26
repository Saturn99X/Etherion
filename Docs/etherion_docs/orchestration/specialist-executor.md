# Specialist Executor: Inside a Single Specialist Run

When the Team Orchestrator calls a specialist (e.g., "Data Analyst, fetch Q3 sales trends"), what happens? This document traces the execution from instruction to result, showing how the specialist is instantiated, prompted, runs tools, and reports back.

## The Runtime Executor

The specialist's runtime is `CustomAgentRuntimeExecutor`. This is the bridge between the database-stored `CustomAgentDefinition` and the actual LLM execution.

```python
# From src/agents/specialists/custom_agent_runtime_executor.py
class CustomAgentRuntimeExecutor:
    def __init__(
        self,
        tenant_id: int = 0,
        job_id: str = "",
        custom_agent_id: str = "default_custom_agent",
    ):
        self.tenant_id = tenant_id
        self.job_id = job_id
        self.custom_agent_id = custom_agent_id

    async def ainvoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the specialist with the given instruction."""
        instruction = payload.get("instruction") or payload.get("input") or ""
        return {
            "custom_agent_id": self.custom_agent_id,
            "output": str(instruction),
        }
```

In production, `ainvoke` does much more than this placeholder—it loads the specialist config, prepares prompts, invokes the LLM, calls tools, and serializes results. Let's walk through that flow.

## Execution Flow: Step by Step

### Step 1: Load Specialist Configuration

The orchestrator has the specialist ID (e.g., `"ca_data_analyst_001"`). The first task is to load its definition from the database:

```python
# Pseudocode: Specialist Loading
def load_specialist(specialist_id: str, tenant_id: int) -> CustomAgentDefinition:
    session = get_session()
    specialist = session.query(CustomAgentDefinition).filter(
        CustomAgentDefinition.custom_agent_id == specialist_id,
        CustomAgentDefinition.tenant_id == tenant_id,
        CustomAgentDefinition.is_active == True,
    ).first()

    if not specialist:
        raise ValueError(f"Specialist {specialist_id} not found or inactive")

    errors = specialist.validate_configuration()
    if errors:
        raise ValueError(f"Specialist configuration invalid: {errors}")

    return specialist
```

Result: We have the full `CustomAgentDefinition` with:
- `system_prompt` — The role definition
- `tool_names` — Allowed tools as a JSON string
- `model_name` — LLM to use (e.g., "gemini-2.5-flash")
- `max_iterations` — Max tool-call loops
- `temperature` — LLM randomness (typically 0.1 for specialists)

### Step 2: Construct the Prompt

The specialist's reasoning happens via an LLM prompt. The prompt combines:

1. **System message** — From `CustomAgentDefinition.system_prompt`
2. **Context** — From the orchestrator (goal, previous results, observation instructions)
3. **Instruction** — What the orchestrator is asking for right now
4. **Tool descriptions** — What tools are available

Example:

```
=== SYSTEM PROMPT ===
You are the Data Analyst specialist. Your role is to extract, validate, and
summarize quantitative data. Be precise. Always cite data sources.

=== AVAILABLE TOOLS ===
- kb_search: Search the tenant's knowledge base. Returns documents with content.
- sql_query: Execute a SQL query against the data warehouse. Returns rows.
- spreadsheet_reader: Read CSV or Excel files from tenant storage.

=== CONTEXT ===
Overall Goal: Analyze Q3 sales trends.
Previous Results: (none yet)
User Personality: Prefers detailed tables over prose; risk-averse on forecasts.

=== INSTRUCTION ===
Extract Q3 sales data by region. Include:
- Total revenue per region
- Month-over-month growth %
- Top 3 products by region
Format as a markdown table. Cite the source (KB document ID or data warehouse table name).

=== YOUR RESPONSE ===
[Specialist responds here, may invoke tools]
```

### Step 3: Invoke the LLM

The specialist calls the configured LLM with the prompt. Depending on `model_name`:

```python
# Pseudocode: LLM Invocation
if specialist.model_name == "gemini-2.5-flash":
    llm = create_gemini_llm(model="gemini-2.5-flash", temperature=specialist.temperature)
elif specialist.model_name == "gemini-3-flash-preview":
    llm = create_gemini_llm(model="gemini-3-flash-preview", temperature=specialist.temperature)
else:
    raise ValueError(f"Unsupported model: {specialist.model_name}")

# Stream or block for response
response = await llm.ainvoke(prompt, temperature=specialist.temperature)
```

The LLM's response might be:

```
I need to query the data warehouse for Q3 sales. Let me start by searching the KB for table schemas.

[Calls tool: kb_search with "Q3 sales data schema"]
```

Or it might directly provide structured output if the instruction is simple.

### Step 4: Tool Invocation Loop

If the LLM response is a **tool call** (a request to use a tool), the specialist enters a loop:

```python
# Pseudocode: Tool Invocation Loop
iteration = 0
while iteration < specialist.max_iterations:
    iteration += 1

    # Parse LLM response for tool calls
    tool_calls = parse_tool_calls(response)

    if not tool_calls:
        # No more tools; we have a final response
        break

    for tool_call in tool_calls:
        tool_name = tool_call['name']
        tool_args = tool_call['arguments']

        # Verify tool is allowed
        allowed_tools = specialist.get_tool_names()
        if tool_name not in allowed_tools:
            # Append error and re-invoke LLM
            response += f"\n[ERROR] Tool '{tool_name}' is not allowed. Allowed tools: {allowed_tools}"
        else:
            # Execute the tool
            try:
                result = await invoke_tool(tool_name, tool_args)
                response += f"\n[TOOL RESULT] {tool_name}: {result}"
            except Exception as e:
                response += f"\n[TOOL ERROR] {tool_name}: {str(e)}"

    # Re-invoke LLM with tool results appended
    response = await llm.ainvoke(prompt + response)

if iteration >= specialist.max_iterations:
    raise TimeoutError(f"Specialist exceeded max iterations ({specialist.max_iterations})")
```

**Key points:**

- Only tools in `specialist.tool_names` are allowed. Anything else is rejected with an error.
- The result of each tool is appended to the conversation, forming a chain of reasoning.
- The loop exits when the LLM produces a final response (no more tool calls).

### Step 5: Result Serialization

Once the LLM produces a final response (no tool calls), the specialist serializes it:

```python
# Pseudocode: Result Serialization
result = {
    "output": final_response,  # The text response
    "specialist_id": specialist.custom_agent_id,
    "specialist_name": specialist.name,
    "tools_used": [tc['name'] for tc in all_tool_calls],
    "iterations": iteration,
    "cost_estimate": cost_tracker.estimate_cost(
        model=specialist.model_name,
        input_tokens=input_tokens_count,
        output_tokens=output_tokens_count,
    ),
    "model": specialist.model_name,
}
```

This dictionary is returned to the orchestrator.

### Step 6: Trace Publishing

All of this (prompts, tool calls, results) is logged to the **execution trace**. This is crucial for auditability and debugging.

```python
# Pseudocode: Trace Publishing
trace_step = ExecutionTraceStep(
    job_id=job_id,
    tenant_id=tenant_id,
    step_number=step_number,
    timestamp=datetime.utcnow(),
    step_type=StepType.SPECIALIST_EXECUTION,
    actor=f"specialist:{specialist.custom_agent_id}",
    thought=final_response[:500],  # First 500 chars
    action_tool=", ".join([tc['name'] for tc in all_tool_calls]),
    action_input=json.dumps(all_tool_calls),
    observation_result=", ".join([f"{tc['name']}: OK" for tc in all_tool_calls]),
    step_cost=cost_estimate,
    model_used=specialist.model_name,
    raw_data=json.dumps({
        "full_response": final_response,
        "iteration_count": iteration,
        "tools_used": [tc['name'] for tc in all_tool_calls],
    }),
)
session.add(trace_step)
session.commit()

# Also publish to Redis for real-time observation
publish_trace_event({
    "job_id": job_id,
    "type": "specialist_step_completed",
    "specialist_id": specialist.custom_agent_id,
    "cost": cost_estimate,
    "output_preview": final_response[:100],
})
```

The execution trace is the complete audit record and can be replayed later for debugging or compliance.

## Configuration and Constraints

The specialist's behavior is tuned by its configuration fields:

| Field | Purpose | Example |
|-------|---------|---------|
| `system_prompt` | Role and behavior definition | "You are a meticulous data analyst..." |
| `tool_names` | JSON list of allowed tools | `["kb_search", "sql_query"]` |
| `model_name` | LLM to use | `"gemini-2.5-flash"` |
| `temperature` | LLM sampling randomness | `0.1` (low = deterministic) |
| `max_iterations` | Max tool-call loops | `10` |
| `timeout_seconds` | Wall-clock limit | `300` (5 minutes) |

### Temperature and Model Selection

- **Low temperature (0.1)** — Specialists use low temperature for consistency. They should be predictable.
- **Model selection** — Different models have different speeds and costs. "gemini-2.5-flash" is fast and cheap; "gemini-3-pro-preview" is slower but more capable.

Tenants can define different specialists with the same role but different models:

```python
# Conservative specialist: fast, cheap, deterministic
fast_analyst = CustomAgentDefinition(
    name="Quick Analyst",
    model_name="gemini-2.5-flash",
    temperature=0.05,
    max_iterations=5,
)

# Deep thinker: slower, more capable, flexible
thorough_analyst = CustomAgentDefinition(
    name="Thorough Analyst",
    model_name="gemini-3-pro-preview",
    temperature=0.2,
    max_iterations=10,
)
```

## Error Handling

If a specialist encounters an error, it's caught and reported:

```python
# Pseudocode: Error Handling
try:
    result = await specialist_executor.ainvoke(payload)
    # Success
except TimeoutError as e:
    logger.error(f"Specialist {specialist_id} timed out: {e}")
    raise SpecialistExecutionFailed(
        reason="timeout",
        specialist_id=specialist_id,
        original_error=str(e),
    )
except ValueError as e:
    logger.error(f"Specialist {specialist_id} configuration error: {e}")
    raise SpecialistExecutionFailed(
        reason="configuration_error",
        specialist_id=specialist_id,
        original_error=str(e),
    )
except Exception as e:
    logger.error(f"Specialist {specialist_id} unexpected error: {e}")
    raise SpecialistExecutionFailed(
        reason="unknown",
        specialist_id=specialist_id,
        original_error=str(e),
    )
```

The orchestrator catches `SpecialistExecutionFailed` and decides: retry, escalate, or abort.

## Cost Tracking

Every specialist run incurs a cost (LLM API fees). The cost is tracked throughout:

```python
# Pseudocode: Cost Tracking
cost_tracker = CostTracker(job_id=job_id, tenant_id=tenant_id)

# Each LLM invocation adds cost
cost_tracker.add_llm_call(
    model=specialist.model_name,
    input_tokens=prompt_token_count,
    output_tokens=response_token_count,
)

# Each tool call may add cost (if the tool is metered)
cost_tracker.add_tool_call(tool_name="sql_query", cost=0.05)

# Before each specialist runs, check we're under budget
if cost_tracker.total_cost() > team_orchestrator_config.cost_guardrails.max_total_cost_usd:
    raise CostGuardrailExceeded(
        total_cost=cost_tracker.total_cost(),
        max_allowed=team_orchestrator_config.cost_guardrails.max_total_cost_usd,
    )
```

## Integration with the Orchestrator

When the orchestrator calls a specialist:

```python
# From team_orchestrator.py
specialist_tool = agent_to_tool(specialist_executor, name=specialist.name)
result = await specialist_tool.invoke({
    "input": orchestrator_instruction,
    "context": previous_results,
})
```

The orchestrator receives:

```python
{
    "output": "...[final response]...",
    "specialist_id": "ca_analyst_001",
    "tools_used": ["kb_search", "sql_query"],
    "cost_estimate": 0.15,
    "model": "gemini-2.5-flash",
}
```

The orchestrator then validates this result against the step's success criteria (see `execution-loop.md`) and decides whether to move to the next step or retry.

## Summary

- A specialist is instantiated from a `CustomAgentDefinition` record.
- Its execution is a loop: prompt → LLM → tool calls → LLM → ... → final response.
- Only allowed tools (from `tool_names`) can be called.
- Each step is traced (audit log) and costs are tracked (budget).
- The orchestrator validates the result and either advances or retries.
