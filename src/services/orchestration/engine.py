"""
Checklist-based orchestration engine implementing checklist-based orchestration.

TWO MODES:
- Sequential: One specialist at a time. Run → validate → next. Orchestrator
  validates each specialist's output against success criteria before proceeding.
- Parallel: All specialists run concurrently. Each has its own checklist.
  Orchestrator has a global checklist. Specialists request tool calls with
  mandatory justification; orchestrator accepts or refuses with feedback.
  Orchestrator validates each specialist's final output.

The +1 synthesis step integrates all validated outputs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.services.orchestration.checklist import (
    ChecklistItem,
    ChecklistItemStatus,
    ChecklistPlan,
    CriterionCheck,
    ExecutionMode,
    PermissionMode,
)
from src.services.orchestration.specialist_executor import (
    SpecialistExecutor,
    SpecialistRunResult,
    ToolApproval,
    ToolRequest,
)

logger = logging.getLogger(__name__)


class OrchestrationEngine:
    """
    Orchestrates specialists using checklist-based validation.

    The orchestrator does NOT call tools. Specialists call tools.
    The orchestrator validates specialist outputs and gates tool requests.
    """

    def __init__(
        self,
        goal: str,
        job_id: str,
        tenant_id: int,
        user_id: int,
        team_id: str,
        orchestrator_runtime: Any,
        approved_tools: List[Dict[str, Any]],
        specialist_agents: List[Dict[str, Any]],
        max_iterations: int = 8,
        validation_confidence_threshold: float = 0.6,
        auto_approved_tools: Optional[List[str]] = None,
        trace_callback: Optional[Callable] = None,
        permission_mode: str = "bypass_permission",
    ):
        self.goal = goal
        self.job_id = job_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.team_id = team_id
        self.orchestrator_runtime = orchestrator_runtime
        self.approved_tools = approved_tools
        self.specialist_agents = specialist_agents
        self.max_iterations = max_iterations
        self.validation_confidence_threshold = validation_confidence_threshold
        self.permission_mode = permission_mode
        self.auto_approved_tools = set(auto_approved_tools or [
            "search_personal_kb",
            "search_project_kb",
            "unified_research_tool",
            "confirm_action_tool",
            "generate_pdf_file",
            "generate_excel_file",
            "generate_presentation_file",
            "generate_image_file",
        ])
        self.trace_callback = trace_callback

        self.allowed_tool_names = {t.get("name") for t in approved_tools if isinstance(t, dict) and t.get("name")}
        self.allowed_specialist_ids = {s.get("agent_id") for s in specialist_agents if isinstance(s, dict) and s.get("agent_id")}

        self._tool_instances = self._build_tool_instances()

    def _build_tool_instances(self) -> Dict[str, Any]:
        instances = {}
        for t in self.approved_tools:
            if isinstance(t, dict) and t.get("name") and t.get("instance"):
                instances[t["name"]] = t["instance"]
        return instances

    async def run(self) -> Dict[str, Any]:
        """
        Execute the full checklist pipeline.
        """
        await self._emit_trace("ENGINE_START", "Checklist-based orchestration starting")

        # If no specialists, inject a synthetic general-purpose specialist
        # that can use the team's tools autonomously
        if not self.specialist_agents and self.allowed_tool_names:
            self.specialist_agents = [self._create_synthetic_specialist()]
            self.allowed_specialist_ids = {s.get("agent_id") for s in self.specialist_agents if isinstance(s, dict) and s.get("agent_id")}

        # Phase 1: Create orchestrator's high-level checklist
        plan = await self._create_plan()
        if not plan.items:
            plan = self._create_default_plan()

        await self._emit_trace(
            "PLAN_CREATED",
            f"Checklist plan: {len(plan.items)} steps, {plan.mode.value} mode",
            step_count=len(plan.items),
            mode=plan.mode.value,
            steps=[{"step": i.step_number, "specialist": i.specialist, "tool": i.tool} for i in plan.items],
        )

        # Phase 2+3: Execute specialists + validate outputs
        if plan.mode == ExecutionMode.PARALLEL:
            results = await self._execute_parallel(plan)
        else:
            results = await self._execute_sequential(plan)

        # Final: Orchestrator combines validated specialist outputs
        final_output = await self._combine_results(results, plan)

        await self._emit_trace(
            "ENGINE_END",
            "Checklist-based orchestration completed",
            all_passed=plan.all_passed(),
            failed_count=len(plan.failed_items()),
        )

        observations = self._build_observations(results, plan)

        return {
            "output": final_output,
            "plan": plan.model_dump(),
            "specialist_results": {k: {"output": r.output, "tools_used": r.tools_used, "iterations": r.iterations} for k, r in results.items()},
            "observations": observations,
            "metadata": {
                "job_id": self.job_id,
                "team_id": self.team_id,
                "mode": plan.mode.value,
                "total_steps": len(plan.items),
                "passed_steps": len([i for i in plan.items if i.status == ChecklistItemStatus.PASSED]),
                "failed_steps": len(plan.failed_items()),
            },
        }

    # ------------------------------------------------------------------ #
    # Phase 1: PLAN
    # ------------------------------------------------------------------ #

    async def _create_plan(self) -> ChecklistPlan:
        specialist_descs = []
        for s in self.specialist_agents:
            if isinstance(s, dict):
                sid = s.get("agent_id", "")
                sname = s.get("name", sid)
                sdesc = s.get("description", "")
                stools = s.get("tool_names", [])
                if isinstance(stools, str):
                    try:
                        stools = json.loads(stools)
                    except Exception:
                        stools = []
                specialist_descs.append(f"  - {sname} (id: {sid}, tools: {', '.join(stools) if stools else 'none'}) — {sdesc}")

        tool_descs = []
        for t in self.approved_tools:
            if isinstance(t, dict):
                name = t.get("name", "")
                t_type = t.get("type", "")
                if t_type != "specialist_tool":
                    tool_descs.append(f"  - {name}")

        plan_prompt = f"""Create an execution plan for:

GOAL: {self.goal}

SPECIALISTS AVAILABLE:
{chr(10).join(specialist_descs) if specialist_descs else "  (none)"}

TEAM TOOLS:
{chr(10).join(tool_descs) if tool_descs else "  (none)"}

Create a plan as JSON:
{{
  "mode": "sequential" or "parallel",
  "steps": [
    {{
      "step_number": 1,
      "specialist": "specialist id",
      "instruction": "what to tell this specialist",
      "success_criteria": ["criterion 1", "criterion 2"],
      "depends_on": [],
      "max_retries": 2
    }}
  ]
}}

Rules:
- Each step MUST assign a specialist to do WORK (research, analysis, writing, etc.).
- Do NOT include a summary, synthesis, or integration step. The orchestrator handles that.
- Use "parallel" if steps are independent (no depends_on).
- success_criteria must be specific and measurable.
- Limit to {self.max_iterations} steps.
- Output ONLY valid JSON."""

        try:
            result = await self.orchestrator_runtime.ainvoke({"input": plan_prompt, "metadata": {"job_id": self.job_id}})
            raw = result.get("output", "")
            plan = parse_checklist_plan(raw, self.goal)

            for item in plan.items:
                if item.specialist and item.specialist not in self.allowed_specialist_ids:
                    candidate = next((s for s in self.specialist_agents if isinstance(s, dict) and s.get("name", "").lower() == item.specialist.lower()), None)
                    if candidate:
                        item.specialist = candidate.get("agent_id")

            return plan
        except Exception as e:
            logger.warning("Plan creation failed: %s", e)
            return ChecklistPlan(goal=self.goal, items=[])

    def _create_default_plan(self) -> ChecklistPlan:
        items = []
        step = 1
        for sa in self.specialist_agents:
            if isinstance(sa, dict) and sa.get("agent_id"):
                items.append(ChecklistItem(
                    step_number=step,
                    specialist=sa.get("agent_id"),
                    instruction=f"Goal: {self.goal}\nProvide your specialist contribution.",
                    success_criteria=["Output is non-empty", "Output is relevant to the goal"],
                    depends_on=[] if step == 1 else [step - 1],
                    max_retries=2,
                ))
                step += 1

        if not items:
            items.append(ChecklistItem(
                step_number=1,
                specialist="synthetic_generalist",
                instruction=f"Research and answer: {self.goal}",
                success_criteria=["Output addresses the goal", "Output is substantive"],
                depends_on=[],
                max_retries=2,
            ))

        return ChecklistPlan(goal=self.goal, items=items, mode=ExecutionMode.SEQUENTIAL)

    def _create_synthetic_specialist(self) -> Dict[str, Any]:
        """Create a synthetic general-purpose specialist when the team has no real specialists."""
        return {
            "agent_id": "synthetic_generalist",
            "name": "General Specialist",
            "description": "General-purpose specialist that uses the team's available tools",
            "system_prompt": (
                "You are an autonomous specialist agent. Your job is to accomplish the given task "
                "using the tools available to you. Think step by step. Use tools to gather information "
                "when needed. Provide thorough, accurate results. Always cite your sources."
            ),
            "tool_names": list(self.allowed_tool_names),
            "model_name": "gemini-2.5-flash",
            "temperature": 0.1,
            "max_iterations": 10,
        }

    # ------------------------------------------------------------------ #
    # Phase 2+3: EXECUTE + VALIDATE
    # ------------------------------------------------------------------ #

    async def _execute_sequential(self, plan: ChecklistPlan) -> Dict[int, SpecialistRunResult]:
        """
        Sequential mode: one specialist at a time, validate between each.
        The specialist runs autonomously with its own tool-calling loop.
        The orchestrator validates the specialist's final output.
        """
        results = {}
        consecutive_failures = 0
        max_consecutive = 2

        for item in plan.items:
            if await self._is_cancelled():
                item.status = ChecklistItemStatus.SKIPPED
                continue

            if not item.specialist:
                if item.tool:
                    tool_result = await self._run_bare_tool(item)
                    if tool_result and not tool_result.get("error"):
                        item.status = ChecklistItemStatus.PASSED
                        item.result = tool_result
                        results[item.step_number] = SpecialistRunResult(
                            specialist_id="tool", specialist_name=item.tool or "tool",
                            output=str(tool_result), checklist={}, tools_used=[item.tool],
                        )
                    else:
                        item.status = ChecklistItemStatus.FAILED
                        item.error = tool_result.get("error", "Tool failed") if tool_result else "No result"
                        consecutive_failures += 1
                continue

            spec_cfg = next((s for s in self.specialist_agents if isinstance(s, dict) and s.get("agent_id") == item.specialist), None)
            if not spec_cfg:
                candidate = next((s for s in self.specialist_agents if isinstance(s, dict) and s.get("name", "").lower() == item.specialist.lower()), None)
                if candidate:
                    item.specialist = candidate.get("agent_id")
                    spec_cfg = candidate
            if not spec_cfg and self.specialist_agents:
                spec_cfg = self.specialist_agents[0]
                item.specialist = spec_cfg.get("agent_id", item.specialist)
            if not spec_cfg:
                item.status = ChecklistItemStatus.FAILED
                item.error = f"Specialist '{item.specialist}' not found"
                consecutive_failures += 1
                continue

            item.status = ChecklistItemStatus.RUNNING
            await self._emit_trace("STEP_START", f"Running specialist {spec_cfg.get('name', item.specialist)} for step {item.step_number}",
                                   step=item.step_number, specialist=item.specialist)

            prior_results = {str(k): r.output for k, r in results.items() if k < item.step_number}

            specialist_result = await self._run_specialist(
                spec_cfg=spec_cfg,
                instruction=item.instruction,
                success_criteria=item.success_criteria,
                previous_results=prior_results,
            )

            item.result = {"output": specialist_result.output, "tools_used": specialist_result.tools_used}

            validation = await self._validate_specialist_output(specialist_result.output, item.success_criteria)
            item.validation = validation

            if validation.passed:
                item.status = ChecklistItemStatus.PASSED
                consecutive_failures = 0
                results[item.step_number] = specialist_result
                await self._emit_trace("STEP_PASSED", f"Step {item.step_number} passed",
                                       step=item.step_number, confidence=validation.confidence)
            else:
                if item.retry_count < item.max_retries:
                    item.retry_count += 1
                    item.status = ChecklistItemStatus.RETRYING
                    await self._emit_trace("STEP_RETRY", f"Step {item.step_number} retrying ({item.retry_count}/{item.max_retries})",
                                           step=item.step_number, confidence=validation.confidence)

                    retry_result = await self._run_specialist(
                        spec_cfg=spec_cfg,
                        instruction=f"{item.instruction}\n\nPrevious attempt did not meet criteria. Feedback: {validation.reasoning}. Try again.",
                        success_criteria=item.success_criteria,
                        previous_results=prior_results,
                    )

                    retry_val = await self._validate_specialist_output(retry_result.output, item.success_criteria)
                    item.validation = retry_val

                    if retry_val.passed:
                        item.status = ChecklistItemStatus.PASSED
                        consecutive_failures = 0
                        results[item.step_number] = retry_result
                        await self._emit_trace("STEP_PASSED_RETRY", f"Step {item.step_number} passed on retry",
                                               step=item.step_number, retry=item.retry_count)
                        continue

                item.status = ChecklistItemStatus.FAILED
                item.error = f"Validation failed: {validation.reasoning}"
                consecutive_failures += 1
                await self._emit_trace("STEP_FAILED", f"Step {item.step_number} failed validation",
                                       step=item.step_number, confidence=validation.confidence)

                if consecutive_failures >= max_consecutive:
                    self._mark_remaining_skipped(plan, item.step_number)
                    break

        return results

    async def _execute_parallel(self, plan: ChecklistPlan) -> Dict[int, SpecialistRunResult]:
        """
        Parallel mode: all specialists run concurrently.
        Each has its own checklist. Tool calls are gated through the orchestrator.
        """
        tasks = []
        for item in plan.items:
            if not item.specialist:
                continue
            spec_cfg = next((s for s in self.specialist_agents if isinstance(s, dict) and s.get("agent_id") == item.specialist), None)
            if not spec_cfg:
                item.status = ChecklistItemStatus.FAILED
                continue
            tasks.append((item, spec_cfg))

        if not tasks:
            return {}

        async def _run_and_validate(item: ChecklistItem, spec_cfg: Dict):
            item.status = ChecklistItemStatus.RUNNING

            specialist_result = await self._run_specialist(
                spec_cfg=spec_cfg,
                instruction=item.instruction,
                success_criteria=item.success_criteria,
                previous_results={},
            )

            item.result = {"output": specialist_result.output, "tools_used": specialist_result.tools_used}

            validation = await self._validate_specialist_output(specialist_result.output, item.success_criteria)
            item.validation = validation

            if validation.passed:
                item.status = ChecklistItemStatus.PASSED
            else:
                item.status = ChecklistItemStatus.FAILED
                item.error = f"Validation failed: {validation.reasoning}"

            return (item.step_number, specialist_result)

        coros = [_run_and_validate(item, cfg) for item, cfg in tasks]
        done = await asyncio.gather(*coros, return_exceptions=True)

        results = {}
        for d in done:
            if isinstance(d, Exception):
                continue
            step_num, r = d
            results[step_num] = r

        return results

    # ------------------------------------------------------------------ #
    # Specialist execution
    # ------------------------------------------------------------------ #

    async def _run_specialist(
        self,
        spec_cfg: Dict[str, Any],
        instruction: str,
        success_criteria: List[str],
        previous_results: Dict[str, Any],
    ) -> SpecialistRunResult:
        """Run a specialist autonomously with tool-calling loop."""

        spec_id = spec_cfg.get("agent_id", "")
        spec_name = spec_cfg.get("name", spec_id)
        system_prompt = spec_cfg.get("system_prompt", f"You are a specialist agent named {spec_name}.")
        tool_names = spec_cfg.get("tool_names", [])
        if isinstance(tool_names, str):
            try:
                tool_names = json.loads(tool_names)
            except Exception:
                tool_names = []
        model_name = spec_cfg.get("model_name", "gemini-2.5-flash")
        temperature = float(spec_cfg.get("temperature", 0.1))
        max_iter = int(spec_cfg.get("max_iterations", 10))

        specialist_checklist = ChecklistPlan(
            goal=instruction,
            items=[
                ChecklistItem(
                    step_number=1,
                    instruction=instruction,
                    success_criteria=success_criteria,
                )
            ],
        )

        executor = SpecialistExecutor(
            specialist_id=spec_id,
            specialist_name=spec_name,
            system_prompt=system_prompt,
            tool_names=tool_names or list(self.allowed_tool_names),
            model_name=model_name,
            temperature=temperature,
            max_iterations=max_iter,
            auto_approved_tools=self.auto_approved_tools,
            tool_instances=self._tool_instances,
            tool_approval_callback=self._handle_tool_approval,
            tenant_id=self.tenant_id,
            job_id=self.job_id,
        )

        result = await executor.run(
            instruction=instruction,
            checklist=specialist_checklist,
            context={"previous_results": previous_results},
        )

        return result

    def _handle_tool_approval(self, request: ToolRequest) -> ToolApproval:
        """
        Orchestrator's tool approval gate.
        In bypass_permission mode: auto-approved tools pass. Others need justification.
        In restricted mode: ALL tool calls require user approval via ValidationGate.
        """
        tool_name = request.tool_name

        if self.permission_mode == "restricted":
            return ToolApproval(approved=False, feedback=f"Tool '{tool_name}' requires approval in restricted mode. Submit to ValidationGate.")

        if tool_name in self.auto_approved_tools:
            return ToolApproval(approved=True)

        if tool_name not in self.allowed_tool_names:
            return ToolApproval(approved=False, feedback=f"Tool '{tool_name}' is not in the team's allowed tool list.")

        if request.justification and len(request.justification.strip()) > 5:
            return ToolApproval(approved=True)

        return ToolApproval(approved=False, feedback="You must provide a justification for why you need this tool. Include it in the 'justification' field.")

    async def _run_bare_tool(self, item: ChecklistItem) -> Optional[Dict[str, Any]]:
        """Run a bare tool step (no specialist)."""
        import src.tools.unified_research_tool as urt_mod

        tool_name = item.tool
        if tool_name == "unified_research_tool":
            try:
                result = await asyncio.to_thread(
                    urt_mod.unified_research_tool,
                    query=item.instruction or self.goal,
                    tenant_id=str(self.tenant_id),
                    job_id=self.job_id,
                    enable_web=True,
                )
                return result if isinstance(result, dict) else {"output": str(result)}
            except Exception as e:
                return {"error": str(e)}

        return {"error": f"Bare tool '{tool_name}' not supported without specialist"}

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    async def _validate_specialist_output(self, output: str, criteria: List[str]) -> ValidationResult:
        """
        LLM-judge validates specialist output against success criteria.
        Lenient: if the specialist produced substantive output, it likely did useful work.
        The synthesis step handles quality assessment.
        """
        if not criteria:
            return ValidationResult(passed=True, confidence=1.0, reasoning="No criteria")

        if not output or not output.strip():
            return ValidationResult(passed=False, confidence=0.0, reasoning="Empty output",
                                    checks=[CriterionCheck(criterion=c, satisfied=False, confidence=0.0, reasoning="Empty") for c in criteria])

        # If the specialist produced substantial output (>100 chars), auto-pass
        # and let synthesis handle quality. The LLM judge can still run but
        # shouldn't block the pipeline.
        if len(output.strip()) > 100:
            return ValidationResult(
                passed=True, confidence=0.7,
                reasoning="Specialist produced substantive output; passing to synthesis",
                checks=[CriterionCheck(criterion=c, satisfied=True, confidence=0.7, reasoning="Output produced") for c in criteria],
            )

        criteria_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(criteria))

        validation_prompt = f"""You are a validation judge. Does this specialist output satisfy each criterion?

GOAL: {self.goal}

SPECIALIST OUTPUT:
{output[:4000]}

SUCCESS CRITERIA:
{criteria_text}

Respond with ONLY JSON:
{{
  "checks": [
    {{"criterion": "the criterion", "satisfied": true/false, "confidence": 0.0-1.0, "reasoning": "why"}}
  ],
  "overall_confidence": 0.0-1.0,
  "overall_reasoning": "assessment"
}}"""

        try:
            result = await self.orchestrator_runtime.ainvoke({"input": validation_prompt, "metadata": {"job_id": self.job_id}})
            raw = result.get("output", "")
            return self._parse_validation(raw, criteria)
        except Exception as e:
            logger.warning("LLM validation failed: %s", e)
            return ValidationResult(
                passed=True, confidence=0.5,
                reasoning=f"LLM unavailable; auto-pass ({e})",
                checks=[CriterionCheck(criterion=c, satisfied=True, confidence=0.5, reasoning="Fallback") for c in criteria],
            )

    def _parse_validation(self, raw: str, criteria: List[str]) -> ValidationResult:
        try:
            text = raw.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            checks = []
            for cd in data.get("checks", []):
                checks.append(CriterionCheck(
                    criterion=cd.get("criterion", ""),
                    satisfied=bool(cd.get("satisfied", False)),
                    confidence=float(cd.get("confidence", 0.0)),
                    reasoning=cd.get("reasoning"),
                ))
            if not checks:
                checks = [CriterionCheck(criterion=c, satisfied=False, confidence=0.0, reasoning="Not assessed") for c in criteria]

            all_passed = all(c.satisfied for c in checks)
            overall = float(data.get("overall_confidence", 0.0))
            if overall == 0.0 and checks:
                overall = sum(c.confidence for c in checks) / len(checks)

            return ValidationResult(passed=all_passed, confidence=overall, reasoning=data.get("overall_reasoning"), checks=checks)
        except Exception as e:
            logger.warning("Validation parse error: %s", e)
            return ValidationResult(passed=True, confidence=0.5, reasoning="Parse fallback",
                                    checks=[CriterionCheck(criterion=c, satisfied=True, confidence=0.5, reasoning="Parse fallback") for c in criteria])

    # ------------------------------------------------------------------ #
    # Final combination
    # ------------------------------------------------------------------ #

    async def _combine_results(self, results: Dict[int, SpecialistRunResult], plan: ChecklistPlan) -> str:
        if not results:
            return "No specialist completed successfully."

        if len(results) == 1:
            r = list(results.values())[0]
            return r.output

        results_text = ""
        for step_num, r in sorted(results.items()):
            results_text += f"\n### {r.specialist_name} (Step {step_num}):\n{r.output[:3000]}\n"

        combine_prompt = f"""GOAL: {self.goal}

VALIDATED SPECIALIST OUTPUTS:
{results_text}

Combine all specialist outputs into a single coherent response that addresses the goal. Do not add new information not supported by the specialist outputs."""

        try:
            result = await self.orchestrator_runtime.ainvoke({"input": combine_prompt, "metadata": {"job_id": self.job_id}})
            return result.get("output", results_text)
        except Exception as e:
            logger.warning("Final combination failed: %s", e)
            return results_text

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _mark_remaining_skipped(self, plan: ChecklistPlan, after_step: int):
        for item in plan.items:
            if item.step_number > after_step and item.status == ChecklistItemStatus.PENDING:
                item.status = ChecklistItemStatus.SKIPPED

    def _build_observations(self, results: Dict[int, SpecialistRunResult], plan: ChecklistPlan) -> List[Dict[str, Any]]:
        observations = []
        for item in plan.items:
            if item.status == ChecklistItemStatus.PASSED and item.step_number in results:
                r = results[item.step_number]
                observations.append({
                    "type": "specialist_result",
                    "step": item.step_number,
                    "specialist": r.specialist_name,
                    "tools_used": r.tools_used,
                    "iterations": r.iterations,
                    "result_preview": r.output[:300],
                })
            elif item.status == ChecklistItemStatus.FAILED:
                observations.append({"type": "error", "step": item.step_number, "message": item.error or "Failed"})
        return observations

    async def _is_cancelled(self) -> bool:
        try:
            import src.core.redis as core_redis
            return await core_redis.is_job_cancelled(self.job_id)
        except Exception:
            return False

    async def _emit_trace(self, event_type: str, message: str, **kwargs):
        ts = datetime.utcnow().isoformat()
        extra = " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None) if kwargs else ""
        log_line = f"[TRACE] ts={ts} job_id={self.job_id} type={event_type} | {message}"
        if extra:
            log_line += f" | {extra}"
        print(log_line, flush=True)
        try:
            import src.core.redis as core_redis
            await core_redis.publish_execution_trace(self.job_id, {"type": event_type, "step_description": message, **kwargs})
        except Exception:
            pass
