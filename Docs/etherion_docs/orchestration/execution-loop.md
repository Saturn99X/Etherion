# Execution Loop: The 2N+1 Reasoning Algorithm

The **2N+1 loop** is Etherion's core reasoning algorithm. It defines how the Team Orchestrator (an LLM) coordinates specialist agents to solve a problem step by step, validating at each stage.

## What is 2N+1?

- **N** = Number of specialist execution steps
- **N** = Number of validation steps (one after each specialist)
- **+1** = Final synthesis step

The pattern is: **execute specialist → validate → execute specialist → validate → ... → synthesize**.

This ensures that:

1. Each specialist's output is checked before the next step uses it.
2. If validation fails, the orchestrator can diagnose, retry, or escalate.
3. The final synthesis integrates all work into a cohesive response.

## The Loop in Pictures

Here's a visual representation of a 2N+1 loop with 2 specialists (N=2):

```
┌─────────────────────────────────────────────────────────────────────┐
│                     JOB ARRIVES                                     │
│                  (user instruction)                                 │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
        ┌──────────────────────────────────────────┐
        │  STEP 1: SELECT & EXECUTE SPECIALIST 1   │
        │  - Orchestrator reads goal                │
        │  - Selects specialist (e.g., Researcher) │
        │  - Crafts instruction with context       │
        │  - Calls specialist via Tool invocation  │
        └──────────────────┬───────────────────────┘
                           │
                           v
        ┌──────────────────────────────────────────┐
        │  VALIDATION 1: CHECK SPECIALIST 1        │
        │  - Does output match spec? (length, type)│
        │  - Is confidence > threshold?             │
        │  - Any errors or exceptions?              │
        └──────────┬──────────────────┬──────────────┘
                   │                  │
        Pass       │                  │  Fail
                   │                  │
                   v                  v
           [Continue]         ┌─────────────────┐
                              │ Retry/Escalate? │
                              │ Max retries: 2  │
                              └────────┬─────────┘
                                       │
                        Success: Continue
                        Fail: Escalate to Platform Orch.

        ┌──────────────────────────────────────────┐
        │  STEP 2: SELECT & EXECUTE SPECIALIST 2   │
        │  - Read validated output from Step 1     │
        │  - Select next specialist (e.g., Writer) │
        │  - Craft instruction building on Step 1  │
        │  - Invoke specialist                     │
        └──────────────────┬───────────────────────┘
                           │
                           v
        ┌──────────────────────────────────────────┐
        │  VALIDATION 2: CHECK SPECIALIST 2        │
        │  - Does output integrate with Step 1?    │
        │  - Sufficient detail?                    │
        │  - No contradictions?                    │
        └──────────┬──────────────────┬──────────────┘
                   │                  │
        Pass       │                  │  Fail
                   │                  │
                   v                  v
           [Continue]         [Retry or Escalate]

        ┌──────────────────────────────────────────┐
        │  SYNTHESIS: FINAL +1 STEP                │
        │  - Orchestrator reviews all outputs      │
        │  - Integrates findings                   │
        │  - Formats final response                │
        │  - Publishes decision trace              │
        └──────────────────┬───────────────────────┘
                           │
                           v
                  ┌────────────────────┐
                  │   JOB COMPLETED    │
                  │  (result + trace)  │
                  └────────────────────┘
```

## How the Orchestrator Decides: Plan and Dispatch

The orchestrator doesn't make random choices. It follows a **plan** and **dispatches** specialists methodically. Here's a concrete flow:

### Phase 1: Planning

The orchestrator receives a goal and creates a plan. Example:

```
Goal: "Summarize Q3 sales trends and recommend marketing focus areas."

Plan (internal reasoning):
1. First, get raw Q3 sales data and trends (need: Data Analyst)
2. Then, analyze competitor landscape (need: Market Researcher)
3. Finally, synthesize insights and draft recommendations (I will do this)
```

This plan is expressed as structured JSON:

```json
{
  "goal": "Summarize Q3 sales trends and recommend marketing focus areas",
  "steps": [
    {
      "step_number": 1,
      "specialist": "Data Analyst",
      "instruction": "Extract Q3 sales data by region. Provide trends as a table.",
      "success_criteria": ["Data is in table format", "All regions included", "Trends are clear"],
      "depends_on": []
    },
    {
      "step_number": 2,
      "specialist": "Market Researcher",
      "instruction": "Given the Q3 sales trends, identify competitor actions and market shifts. Cite sources.",
      "success_criteria": ["3+ sources cited", "Competitor names identified", "No speculation"],
      "depends_on": [1]
    }
  ]
}
```

### Phase 2: Dispatch and Validate

The orchestrator then executes the plan step by step:

```python
# Pseudocode from Team Orchestrator
for step in plan['steps']:
    specialist_name = step['specialist']
    instruction = step['instruction']
    criteria = step['success_criteria']

    # Dispatch to specialist
    result = await specialist_tool.invoke({
        "input": instruction,
        "context": previous_results,  # Include all prior steps
    })

    # Validate
    validation = await validate_step(result, criteria)
    if validation['passed']:
        results[step_number] = result
    else:
        # Diagnose and retry or escalate
        retry_count = 0
        while retry_count < max_retries and not validation['passed']:
            retry_count += 1
            result = await specialist_tool.invoke({...modified instruction...})
            validation = await validate_step(result, criteria)

        if not validation['passed']:
            # Too many failures: request replan from Platform Orchestrator
            raise ReplanRequired(f"Step {step_number} failed validation {max_retries} times")
```

### Phase 3: Synthesis

After all N steps succeed, the orchestrator synthesizes:

```python
# Final +1: synthesis step
synthesis_prompt = f"""
You are the Team Orchestrator. You have received the following outputs from your specialists:

{format_all_results(results)}

Your goal is to integrate these findings into a coherent, final response that:
- Directly addresses the user's original question
- Cites the specialist outputs where relevant
- Is actionable and clear
- Identifies any assumptions or limitations

Provide the final response now.
"""

final_response = await orchestrator_llm.complete(synthesis_prompt)
```

## Key Mechanisms

### 1. Context Passing

Each specialist has access to all previous results. This is **crucial** for chain-of-thought reasoning:

```python
instruction = f"""
You are the Market Analyst specialist.

**Goal:** {overall_goal}

**Previous Findings:**
{json.dumps(previous_results, indent=2)}

**Your Task:**
{step_instruction}

**Success Criteria:**
- Your output should build on the previous findings
- You may contradict them if you have strong evidence
- Cite all sources
"""
```

### 2. Validation Criteria

Each step specifies measurable criteria. The orchestrator checks them programmatically:

```python
async def validate_step(output: str, criteria: List[str]) -> Dict[str, Any]:
    """Validate specialist output against success criteria."""
    checks = []
    for criterion in criteria:
        # Use an LLM to check criterion-by-criterion
        check_result = await llm.judge(
            f"Does the following output satisfy this criterion: {criterion}?\n\n{output}"
        )
        checks.append({
            "criterion": criterion,
            "satisfied": check_result['confidence'] > 0.7,
            "reasoning": check_result['reasoning'],
        })

    all_passed = all(c['satisfied'] for c in checks)
    return {
        "passed": all_passed,
        "checks": checks,
        "confidence": sum(c['satisfied'] for c in checks) / len(checks),
    }
```

### 3. Retry and Escalation

If validation fails, the orchestrator has options:

```python
if not validation['passed']:
    # Option 1: Simple retry (change phrasing of the instruction)
    if retry_count < max_retries:
        logger.info(f"Validation failed, retrying with adjusted instruction")
        # Re-invoke with clarified criteria

    # Option 2: Escalate to Platform Orchestrator
    else:
        logger.warning(f"Max retries exceeded, escalating")
        raise ReplanRequired(
            reason="Specialist unable to satisfy criteria",
            specialist=specialist_name,
            failed_criteria=validation['failed_checks'],
        )
```

## Orchestrator Configuration

The 2N+1 behavior is tuned via the `OrchestratorProfile`. For the Team Orchestrator:

```python
# From orchestrator_runtime.py
TEAM_ORCHESTRATOR_PROFILE = OrchestratorProfile(
    name="team_orchestrator",
    system_prompt=(
        "You are the Team Orchestrator. You receive a structured plan from the Platform "
        "Orchestrator and must execute it through the team's specialist agents. For every step:\n"
        "1. Restate your understanding and confirm alignment.\n"
        "2. Select the appropriate specialist and craft an instruction.\n"
        "3. Validate the specialist output against success criteria.\n"
        "4. Log confidence, cost, and risks.\n"
        "If two validation failures occur consecutively, halt and return a replan request."
    ),
    loop=LoopParameters(
        max_specialists_per_plan=4,        # Max N
        max_iterations=8,                  # Max total steps (including validation)
        per_step_timeout_seconds=210,      # Timeout per specialist
        retry_limit=1,                     # Retries before escalate
        replan_on_validation_failure=True, # Escalate on 2 failures
        plan_weight=0.4,                   # How much to weigh planning
        execution_weight=0.6,              # How much to weigh execution
    ),
    cost_guardrails=CostGuardrails(
        max_total_cost_usd=12.0,           # Budget cap
        max_step_cost_usd=2.5,             # Per-specialist cap
        warn_at_usd=9.0,                   # Warning threshold
    ),
    validation=ValidationThresholds(
        minimum_confidence=0.6,            # Validation confidence floor
        minimum_output_chars=40,           # Output must be non-trivial
        max_consecutive_failures=2,        # Then escalate
        replan_trigger="validation-confidence-below-threshold",
    ),
)
```

## Example: A Real 2N+1 Loop

Here's how a real job might flow:

**Goal:** "Analyze our top 10 customers' usage patterns and recommend upsell opportunities."

**Loop Execution:**

1. **Dispatch to Data Analyst**
   - Instruction: "Extract usage metrics for top 10 customers (by MRR) over the last 90 days."
   - Output: Table with feature adoption, login frequency, API calls per feature.
   - Validation: Check format (table), verify all 10 customers, verify 90-day window. ✓ PASS

2. **Dispatch to Sales Strategist**
   - Instruction: "Given the usage patterns, identify underutilized features and recommend upsell angles. Use insights from Market Research KB."
   - Output: For each customer, list 2-3 feature bundles with adoption rates and estimated upsell value.
   - Validation: Check that recommendations are tied to usage data, not generic. ✓ PASS

3. **Dispatch to Content Writer** (optional, N can vary)
   - Instruction: "Draft personalized upsell emails for top 3 customers based on the strategist's recommendations."
   - Output: 3 email drafts, each with subject line, opening, value prop, and CTA.
   - Validation: Check tone, ensure personalization, verify CTAs. ✓ PASS

4. **Synthesis (+1)**
   - Orchestrator combines all outputs into a final executive summary.
   - Includes: customer segments, upsell tactics, draft outreach templates, estimated revenue impact.
   - Output formatted as markdown with sections and tables.

**Total:** 3 specialists + 1 synthesis = 2(3)+1 = 7 reasoning steps, all validated.

## Convergence and Termination

The loop terminates when:

1. **Success**: All N steps pass validation and synthesis completes.
2. **Max iterations exceeded**: Escalate and mark as failed.
3. **Cost guardrail exceeded**: Abort and escalate to Platform Orchestrator (with cost warning).
4. **Timeout**: Any individual specialist exceeds per_step_timeout_seconds.

The loop is guaranteed to converge because:

- Each step has a timeout.
- Retry count is bounded.
- Total iteration count is bounded.
- Escalation to Platform Orchestrator is a defined exit path.

## Summary

- The **2N+1 loop** is: N specialist steps, N validation checks, +1 synthesis.
- The **orchestrator plan** breaks a goal into specialist tasks with success criteria.
- **Dispatch** executes specialists in order, passing context forward.
- **Validation** checks criteria programmatically; if failures exceed threshold, escalate.
- **Synthesis** integrates all results into a final response.
- Configuration via `OrchestratorProfile` controls loop parameters, timeouts, and costs.
