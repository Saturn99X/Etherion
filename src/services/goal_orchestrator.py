import logging
import uuid
from typing import Dict, Any, Optional, List

import os
import sys
from datetime import datetime, timedelta
from src.services.platform_orchestrator import PlatformOrchestrator
from src.services.team_orchestrator import TeamOrchestrator
from src.core.security.audit_logger import log_security_event
from src.services.pricing.cost_tracker import CostTracker
from src.services.pricing.credit_manager import CreditManager
from src.services.pricing.ledger import PricingLedger
from src.services.tool_instrumentation import instrument_base_tool
from src.services.prompt_security import get_prompt_security
from src.utils.input_sanitization import InputSanitizer
from src.services.behavior_monitor import get_behavior_monitor
from src.core.redis import publish_execution_trace, get_redis_client, publish_job_status, is_job_cancelled
from src.services.user_observation_service import get_user_observation_service
from src.tools.unified_research_tool import unified_research_tool
from src.database.db import get_scoped_session
from src.database.ts_models import ExecutionCost
from sqlmodel import select
from src.database.models import Job, JobStatus
from src.core.celery import celery_app
import asyncio
from src.database.models import AgentTeam
from sqlalchemy import func

logger = logging.getLogger(__name__)


def _log_trace(job_id: str, event_type: str, message: str, **kwargs):
    """Log trace event to stdout with structured format for observability.
    
    This ensures ALL trace events are visible in Cloud Run logs, not just Redis pub/sub.
    Format: [TRACE] job_id={job_id} type={event_type} | {message} | {extra_data}
    """
    ts = datetime.utcnow().isoformat()
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None) if kwargs else ""
    log_line = f"[TRACE] ts={ts} job_id={job_id} type={event_type} | {message}"
    if extra:
        log_line += f" | {extra}"
    print(log_line, file=sys.stdout, flush=True)


class GoalOrchestrator:
    """
    Main entry point for orchestrating agentic workflows using the dual orchestrator architecture.
    """

    def __init__(self, goal: str, user_id: int, tenant_id: int, job_id: Optional[str] = None):
        self.goal = goal
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.job_id = job_id or f"job_{uuid.uuid4().hex[:8]}"
        _log_trace(self.job_id, "INIT", "Initializing GoalOrchestrator",
                   user_id=user_id, tenant_id=tenant_id, goal_preview=str(goal)[:100])
        try:
            self.platform_orchestrator = PlatformOrchestrator(tenant_id=self.tenant_id, user_id=self.user_id, job_id=self.job_id)
            _log_trace(self.job_id, "INIT", "PlatformOrchestrator initialized successfully")
        except Exception as e:
            _log_trace(self.job_id, "INIT_ERROR", f"PlatformOrchestrator initialization failed: {type(e).__name__}: {str(e)}")
            raise
        self.team_orchestrators: Dict[str, TeamOrchestrator] = {}

    async def execute(self) -> Dict[str, Any]:
        """
        Execute the goal by orchestrating agent teams.
        """
        _log_trace(self.job_id, "EXECUTE_START", "Starting goal execution")
        
        # Pre-run balance check (no negative balance allowed) with dev bypass
        credit_mgr = CreditManager()
        dev_bypass = os.getenv("DEV_BYPASS_AUTH", "0") == "1" or os.getenv("CREDITS_BYPASS", "0") == "1"
        if not dev_bypass:
            balance = await credit_mgr.get_balance(self.user_id, tenant_id=str(self.tenant_id))
            _log_trace(self.job_id, "CREDIT_CHECK", f"Credit balance check",
                       balance=balance, user_id=self.user_id, tenant_id=self.tenant_id)
            if balance <= 0:
                _log_trace(self.job_id, "CREDIT_FAIL", f"INSUFFICIENT_CREDITS - balance={balance}")
                return {"success": False, "error": "INSUFFICIENT_CREDITS", "job_id": self.job_id}

        # Daily cap enforcement (per user per tenant)
        try:
            cap = int(os.getenv("DAILY_CREDIT_CAP", "25") or 25)
        except Exception:
            cap = 25
        if cap > 0:
            redis = get_redis_client()
            today = datetime.utcnow().strftime("%Y%m%d")
            daily_key = f"credits:daily_used:{self.tenant_id}:{self.user_id}:{today}"
            used_today = int((await redis.get(daily_key, 0)) or 0)
            _log_trace(self.job_id, "DAILY_CAP_CHECK", f"Daily cap check", used_today=used_today, cap=cap)
            if used_today >= cap:
                # Compute reset time (midnight UTC)
                now = datetime.utcnow()
                reset_at = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
                _log_trace(self.job_id, "DAILY_CAP_FAIL", f"DAILY_CREDIT_CAP_EXCEEDED - used={used_today}, cap={cap}")
                return {
                    "success": False,
                    "error": "DAILY_CREDIT_CAP_EXCEEDED",
                    "job_id": self.job_id,
                    "reset_at": reset_at,
                    "used": used_today,
                    "cap": cap,
                }

        # Input validation & prompt security (Phase 9 - Step 1)
        # 1) Basic sanitation with strict checks
        try:
            sanitized_goal = InputSanitizer.sanitize_with_security_checks(
                self.goal,
                max_length=2000,
                allowed_pattern=None,
                check_dangerous=True,
                check_sql_injection=True,
            )
        except ValueError as ve:
            print(f"[FAILURE] Job {self.job_id}: INVALID_INPUT - {str(ve)}")
            await log_security_event(
                event_type="input_validation_failure",
                user_id=str(self.user_id),
                tenant_id=str(self.tenant_id),
                details={
                    "job_id": self.job_id,
                    "validation_errors": [str(ve)],
                    "input_data": {"goal_preview": str(self.goal)[:120]},
                },
            )
            return {"success": False, "error": "INVALID_INPUT", "job_id": self.job_id}

        # 2) Prompt injection detection + behavior lockout
        bm = get_behavior_monitor()
        user_key = f"tenant:{self.tenant_id}:user:{self.user_id}"
        if await bm.is_locked_out(user_key):
            print(f"[FAILURE] Job {self.job_id}: LOCKED_OUT_DUE_TO_SECURITY")
            return {"success": False, "error": "LOCKED_OUT_DUE_TO_SECURITY", "job_id": self.job_id}

        # Analyze sanitized goal
        ps = get_prompt_security()
        analysis = await ps.analyze_text_async(sanitized_goal, user_key=user_key)
        if analysis["action"] == "block":
            print(f"[FAILURE] Job {self.job_id}: PROMPT_INJECTION_BLOCKED - risk_score={analysis.get('risk_score')}")
            await bm.record_incident(user_key)
            await log_security_event(
                event_type="security_violation",
                user_id=str(self.user_id),
                tenant_id=str(self.tenant_id),
                details={
                    "job_id": self.job_id,
                    "violation_type": "prompt_injection_blocked",
                    "risk_score": analysis.get("risk_score"),
                    "matches": analysis.get("matches", []),
                },
            )
            return {"success": False, "error": "PROMPT_INJECTION_BLOCKED", "job_id": self.job_id}
        elif analysis["action"] == "sanitize":
            sanitized_goal = ps.sanitize_text(sanitized_goal)
            await bm.record_incident(user_key)
            await log_security_event(
                event_type="security_violation",
                user_id=str(self.user_id),
                tenant_id=str(self.tenant_id),
                details={
                    "job_id": self.job_id,
                    "violation_type": "prompt_injection_sanitized",
                    "risk_score": analysis.get("risk_score"),
                    "matches": analysis.get("matches", []),
                },
            )
        await log_security_event(
            event_type="goal_orchestration_started",
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            details={"job_id": self.job_id, "goal": self.goal},
        )
        await publish_execution_trace(self.job_id, {"type": "START", "step_description": "Orchestration started"})

        # Early cancel guard
        if await is_job_cancelled(self.job_id):
            try:
                async with get_scoped_session() as session:
                    res = await session.exec(select(Job).where(Job.job_id == self.job_id))
                    job = res.first()
                    if job:
                        job.update_status(JobStatus.CANCELLED)
                        session.add(job)
                await publish_job_status(self.job_id, {"job_id": self.job_id, "status": "CANCELLED", "message": "Stop acknowledged (pre-run)"})
                await publish_execution_trace(self.job_id, {"type": "STOP_ACK", "step_description": "Stop acknowledged before execution"})
            except Exception:
                pass
            return {"success": False, "error": "CANCELLED", "job_id": self.job_id}

        # Phase 7: Inject user observation context and prepare retrieval strategy
        try:
            observation_service = get_user_observation_service()
            observation_text = await observation_service.generate_system_instructions(self.user_id, self.tenant_id)
        except Exception:
            observation_text = ""

        # Augment the goal with observation context (kept small and prefixed)
        augmented_goal = sanitized_goal
        if observation_text:
            # Keep within a safe bound to avoid ballooning prompt size
            obs_trim = observation_text[:2000]
            augmented_goal = (
                f"USER PERSONALIZATION CONTEXT:\n{obs_trim}\n\nGOAL:\n{sanitized_goal}"
            )

        # Lookup execution preferences early to decide retrieval behavior (search_force)
        plan_mode_pref: Optional[bool] = None
        search_force_pref: Optional[bool] = None
        try:
            async with get_scoped_session() as session:
                res = await session.exec(select(Job).where(Job.job_id == self.job_id))
                job_row = res.first()
                if job_row:
                    md = job_row.get_job_metadata() or {}
                    if isinstance(md, dict):
                        pm = md.get("plan_mode")
                        sf = md.get("search_force")
                        if isinstance(pm, bool):
                            plan_mode_pref = pm
                        if isinstance(sf, bool):
                            search_force_pref = sf
        except Exception:
            plan_mode_pref = plan_mode_pref
            search_force_pref = search_force_pref

        # Retrieval: KB always; Web when search_force is enabled or for Dual Search
        dual_search_counts = {"project": 0, "personal": 0, "vertex": 0, "web": 0}
        dual_search_error: Optional[str] = None
        dual_search_tool_errors: Optional[Dict[str, Any]] = None
        try:
            # LOG: Dual Search start
            _log_trace(self.job_id, "DUAL_SEARCH_START", f"Starting Dual Search",
                       goal_preview=str(sanitized_goal)[:100], enable_web=search_force_pref is not False)
            dual_search_timeout_s = float(os.getenv("DUAL_SEARCH_TIMEOUT_SECONDS", "20") or 20)
            _dual_search_start = datetime.utcnow()
            research = await asyncio.wait_for(
                asyncio.to_thread(
                    unified_research_tool,
                    query=sanitized_goal,
                    tenant_id=str(self.tenant_id),
                    job_id=self.job_id,
                    # Enable web by default for GoalOrchestrator to ensure comprehensive initial search
                    enable_web=True if search_force_pref is not False else False,
                ),
                timeout=dual_search_timeout_s,
            )
            _dual_search_duration_ms = int((datetime.utcnow() - _dual_search_start).total_seconds() * 1000)
            dual_search_counts["project"] = len(research.get("project_results", []) or [])
            dual_search_counts["personal"] = len(research.get("personal_results", []) or [])
            dual_search_counts["vertex"] = len(research.get("vector_results", []) or [])
            dual_search_counts["web"] = len(research.get("web_results", []) or [])
            
            # LOG: Dual Search completed
            _log_trace(self.job_id, "DUAL_SEARCH_END", f"Dual Search completed",
                       duration_ms=_dual_search_duration_ms,
                       project=dual_search_counts["project"],
                       personal=dual_search_counts["personal"],
                       vertex=dual_search_counts["vertex"],
                       web=dual_search_counts["web"])
            
            try:
                if isinstance(research, dict):
                    dual_search_tool_errors = research.get("errors")
                    if dual_search_tool_errors:
                        _log_trace(self.job_id, "DUAL_SEARCH_ERRORS", f"Dual Search had tool errors",
                                   errors=str(dual_search_tool_errors)[:200])
            except Exception:
                dual_search_tool_errors = None
        except asyncio.TimeoutError:
            _log_trace(self.job_id, "DUAL_SEARCH_TIMEOUT", f"Dual Search timed out after {dual_search_timeout_s}s")
            dual_search_error = "timeout"
        except Exception as e:
            # Fail-open: continue without blocking goal execution
            _log_trace(self.job_id, "DUAL_SEARCH_ERROR", f"Dual Search failed: {type(e).__name__}: {str(e)}")
            try:
                logger.exception(
                    "Dual Search failed",
                    extra={"job_id": self.job_id, "tenant_id": str(self.tenant_id), "user_id": self.user_id},
                )
            except Exception:
                pass
            dual_search_error = "exception"
        # Mid-run cancel guard after dual-search
        if await is_job_cancelled(self.job_id):
            _log_trace(self.job_id, "CANCELLED", "Job cancelled after Dual Search")
            try:
                async with get_scoped_session() as session:
                    res = await session.exec(select(Job).where(Job.job_id == self.job_id))
                    job = res.first()
                    if job:
                        job.update_status(JobStatus.CANCELLED)
                        session.add(job)
                await publish_job_status(self.job_id, {"job_id": self.job_id, "status": "CANCELLED", "message": "Stop acknowledged"})
                await publish_execution_trace(self.job_id, {"type": "STOP_ACK", "step_description": "Stop acknowledged (after search)"})
            except Exception:
                pass
            return {"success": False, "error": "CANCELLED", "job_id": self.job_id}

        try:
            await publish_execution_trace(
                self.job_id,
                {
                    "type": "DUAL_SEARCH",
                    "step_description": "KB + Web search executed",
                    "counts": dual_search_counts,
                    "error": dual_search_error,
                    "tool_errors": dual_search_tool_errors,
                },
            )
        except Exception:
            pass

        # Interaction gating: if a specific team was preselected (Interaction page), use it directly
        selected_team_id: Optional[str] = None
        try:
            async with get_scoped_session() as session:
                res = await session.exec(select(Job).where(Job.job_id == self.job_id))
                job_row = res.first()
                if job_row:
                    md = job_row.get_job_metadata() or {}
                    if isinstance(md, dict):
                        selected_team_id = md.get("agent_team_id")
        except Exception:
            selected_team_id = None

        if selected_team_id:
            _log_trace(self.job_id, "TEAM_SELECTED", f"Using preselected team (Interaction)", team_id=selected_team_id)
            try:
                await publish_execution_trace(self.job_id, {
                    "type": "TEAM_SELECTED",
                    "step_description": f"Using preselected team {selected_team_id} (Interaction)",
                    "team_id": selected_team_id,
                })
            except Exception:
                pass
            team_assignments = {"task_1": {"team_id": selected_team_id, "goal": sanitized_goal}}
        else:
            # 1. Decompose goal into a blueprint using Platform Orchestrator (with augmented context)
            _log_trace(self.job_id, "BLUEPRINT_START", "Creating agent team blueprint")
            blueprint = await self.platform_orchestrator.create_agent_team_blueprint(augmented_goal)
            _log_trace(self.job_id, "BLUEPRINT_END", "Blueprint created",
                       requirements_count=len(blueprint.get("agent_requirements", [])) if isinstance(blueprint, dict) else 0)
            await publish_execution_trace(self.job_id, {"type": "BLUEPRINT", "step_description": "Blueprint created"})

            # 2. Assign sub-tasks to specialist teams (simplified for now)
            _log_trace(self.job_id, "TEAM_ASSIGN_START", "Assigning teams from blueprint")
            team_assignments = await self._assign_teams_from_blueprint(blueprint)
            _log_trace(self.job_id, "TEAM_ASSIGN_END", f"Team assignments completed",
                       assignment_count=len(team_assignments) if team_assignments else 0)

            # Hard gate: if assignment required approval, _assign_teams_from_blueprint returns empty.
            if not team_assignments:
                _log_trace(self.job_id, "PENDING_APPROVAL", "Team assignment requires approval")
                return {"success": False, "error": "PENDING_APPROVAL", "job_id": self.job_id}

        # 3. Execute sub-tasks with Team Orchestrators (enforce cost guardrails)
        # Check before tasks
        if await is_job_cancelled(self.job_id):
            _log_trace(self.job_id, "CANCELLED", "Job cancelled before team tasks")
            try:
                async with get_scoped_session() as session:
                    res = await session.exec(select(Job).where(Job.job_id == self.job_id))
                    job = res.first()
                    if job:
                        job.update_status(JobStatus.CANCELLED)
                        session.add(job)
                await publish_job_status(self.job_id, {"job_id": self.job_id, "status": "CANCELLED", "message": "Stop acknowledged"})
                await publish_execution_trace(self.job_id, {"type": "STOP_ACK", "step_description": "Stop acknowledged (before tasks)"})
            except Exception:
                pass
            return {"success": False, "error": "CANCELLED", "job_id": self.job_id}

        _log_trace(self.job_id, "TEAM_TASKS_START", f"Executing team tasks",
                   task_count=len(team_assignments),
                   teams=str(list(team_assignments.keys())))
        _team_tasks_start = datetime.utcnow()
        task_results = await self._execute_team_tasks(team_assignments)
        _team_tasks_duration_ms = int((datetime.utcnow() - _team_tasks_start).total_seconds() * 1000)
        _log_trace(self.job_id, "TEAM_TASKS_END", f"Team tasks completed",
                   duration_ms=_team_tasks_duration_ms,
                   result_count=len(task_results) if task_results else 0)
        
        # Check after tasks
        if await is_job_cancelled(self.job_id):
            _log_trace(self.job_id, "CANCELLED", "Job cancelled after team tasks")
            try:
                async with get_scoped_session() as session:
                    res = await session.exec(select(Job).where(Job.job_id == self.job_id))
                    job = res.first()
                    if job:
                        job.update_status(JobStatus.CANCELLED)
                        session.add(job)
                await publish_job_status(self.job_id, {"job_id": self.job_id, "status": "CANCELLED", "message": "Stop acknowledged"})
                await publish_execution_trace(self.job_id, {"type": "STOP_ACK", "step_description": "Stop acknowledged (after tasks)"})
            except Exception:
                pass
            return {"success": False, "error": "CANCELLED", "job_id": self.job_id}
        await publish_execution_trace(self.job_id, {"type": "TASKS_COMPLETED", "step_description": "Team tasks executed"})

        # Publish preferences event for UI transparency (no behavioral guarantee)
        try:
            await publish_execution_trace(self.job_id, {
                "type": "PREFERENCES",
                "step_description": "Execution preferences applied",
                "plan_mode": plan_mode_pref,
                "search_force": search_force_pref,
            })
        except Exception:
            pass

        # 4. Synthesize results (simplified for now)
        final_result = self._synthesize_results(task_results)

        await log_security_event(
            event_type="goal_orchestration_completed",
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            details={"job_id": self.job_id, "final_result_preview": str(final_result)[:200]},
        )
        await publish_execution_trace(self.job_id, {"type": "END", "step_description": "Orchestration completed"})

        # Post-run: summarize usage and deduct credits
        tracker = CostTracker()
        usage_summary = await tracker.summarize(self.job_id, tenant_id=str(self.tenant_id))
        # Convert USD→credits using configured ratio; no-op if ratio is 0
        try:
            total_cost_usd = float(usage_summary.get("total_cost", 0.0) or 0.0)
        except Exception:
            total_cost_usd = 0.0
        ratio = int(os.getenv("DOLLAR_TO_CREDITS_RATIO", "0") or 0)
        credit_delta = int((total_cost_usd * ratio) + 0.9999) if ratio > 0 else 0  # round up conservatively
        new_balance = await credit_mgr.deduct(self.user_id, credit_delta, tenant_id=str(self.tenant_id))

        # Persist summarized execution cost (job-level row)
        try:
            counters = usage_summary.get("counters", {})
            async with get_scoped_session() as session:
                session.add(ExecutionCost(
                    job_id=self.job_id,
                    tenant_id=int(self.tenant_id),
                    step_name="JOB_SUMMARY",
                    model_used=str(counters.get("llm_model") or ""),
                    input_tokens=int(counters.get("tokens_in") or 0),
                    output_tokens=int(counters.get("tokens_out") or 0),
                    step_cost=float(total_cost_usd),
                ))
        except Exception:
            pass

        # Increment daily usage counter and set TTL to midnight UTC
        try:
            if credit_delta > 0:
                redis = get_redis_client()
                now = datetime.utcnow()
                today = now.strftime("%Y%m%d")
                daily_key = f"credits:daily_used:{self.tenant_id}:{self.user_id}:{today}"
                new_used = await redis.incr(daily_key, credit_delta)
                # Set expiry to midnight UTC
                seconds_until_midnight = int(((now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)) - now).total_seconds())
                await redis.set(daily_key, new_used, expire=max(1, seconds_until_midnight))
        except Exception:
            pass

        # Append ledger entry
        ledger = PricingLedger()
        await ledger.append_usage_event(
            user_id=self.user_id,
            job_id=self.job_id,
            usage_summary=usage_summary,
            credit_delta=credit_delta,
            currency=usage_summary.get("currency", "USD"),
            tenant_id=str(self.tenant_id),
        )

        return {**final_result, "usage": usage_summary, "new_credit_balance": new_balance}

    async def _assign_teams_from_blueprint(self, blueprint: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assign teams based on the blueprint from the Platform Orchestrator.
        """
        assignments = {}
        for i, requirement in enumerate(blueprint.get("agent_requirements", [])):
            task_id = f"task_{i+1}"
            
            # Determine required skill/team type
            skills = requirement.get("required_skills", ["default"])
            primary_skill = skills[0] if skills else "default"
            
            # Try to find an existing team for this skill
            team = await self._find_team_by_skill(primary_skill)
            
            if not team:
                # If not found, request approval and wait
                await self._request_approval_and_wait(primary_skill, requirement)
                return {}

            team_id = team.agent_team_id
            print(f"[DEBUG] Assigned existing team {team_id} ({team.name}) for skill {primary_skill}")

            assignments[task_id] = {"team_id": team_id, "goal": requirement.get("description", self.goal)}
        return assignments

    async def _find_team_by_skill(self, skill: str) -> Optional[AgentTeam]:
        """Find a team that matches the skill (by name)."""
        try:
            async with get_scoped_session() as session:
                # Simple heuristic: look for team with skill in name (case-insensitive)
                # e.g. "Research" -> "Research Team"
                stmt = select(AgentTeam).where(
                    AgentTeam.tenant_id == self.tenant_id,
                    AgentTeam.is_active == True,
                    func.lower(AgentTeam.name).contains(skill.lower())
                )
                result = await session.execute(stmt)
                return result.scalars().first()
        except Exception as e:
            print(f"[ERROR] Failed to find team by skill {skill}: {e}")
            return None

    async def _request_approval_and_wait(self, skill: str, requirement: Dict[str, Any]):
        """Publish approval request and poll for team creation."""
        print(f"[INFO] Requesting approval for team creation: {skill}")

        try:
            async with get_scoped_session() as session:
                job = await session.get(Job, self.job_id)
                if job:
                    job.update_status(JobStatus.PENDING_APPROVAL)
                    session.add(job)
        except Exception:
            pass
        try:
            await publish_job_status(
                self.job_id,
                {
                    "job_id": self.job_id,
                    "status": JobStatus.PENDING_APPROVAL,
                    "current_step_description": f"Awaiting approval to create team for '{skill}'",
                },
            )
        except Exception:
            pass
        
        # Publish event
        try:
            await publish_execution_trace(self.job_id, {
                "type": "BLUEPRINT_APPROVAL_REQUIRED",
                "step_description": f"Approval required: Create team for '{skill}'",
                "skill": skill,
                "suggested_name": requirement.get("name", f"{skill.capitalize()} Team"),
                "suggested_description": requirement.get("description", f"Team for {skill}"),
                "suggested_spec": f"Create a team capable of: {skill}",
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            print(f"[ERROR] Failed to publish approval event: {e}")

        # Do not block the worker here; the approval flow is driven by the UI.
        return

    async def _execute_team_tasks(self, team_assignments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute assigned tasks using the appropriate Team Orchestrators.
        """
        task_results = {}
        tracker = CostTracker()
        prev_total_credits = 0
        # Guardrails in credits
        max_total = int(os.getenv("PLATFORM_MAX_TOTAL_CREDITS", "250")) or 250
        max_step = int(os.getenv("PLATFORM_MAX_STEP_CREDITS", "50")) or 50
        for task_id, assignment in team_assignments.items():
            team_id = assignment["team_id"]
            task_goal = assignment["goal"]

            if team_id not in self.team_orchestrators:
                self.team_orchestrators[team_id] = TeamOrchestrator(
                    team_id=team_id, tenant_id=self.tenant_id, user_id=self.user_id
                )

            team_orchestrator = self.team_orchestrators[team_id]
            # Team config would be loaded from DB in a real scenario
            mock_team_config = {"job_id": self.job_id}

            result = await team_orchestrator.execute_2n_plus_1_loop(goal=task_goal, team_config=mock_team_config)
            task_results[task_id] = result

            # Guardrail checks based on running cost totals
            try:
                # Publish live cost update for UI
                try:
                    await tracker.publish_cost_event(self.job_id, tenant_id=str(self.tenant_id))
                except Exception:
                    pass

                summary = await tracker.summarize(self.job_id, tenant_id=str(self.tenant_id))
                # Convert USD total to credits
                total_usd = float(summary.get("total_cost", 0.0) or 0.0)
                ratio = int(os.getenv("DOLLAR_TO_CREDITS_RATIO", "0") or 0)
                total_credits = int(total_usd * ratio) if ratio > 0 else 0
                step_delta = max(0, total_credits - prev_total_credits)
                prev_total_credits = total_credits
                if max_step > 0 and step_delta > max_step:
                    await publish_execution_trace(self.job_id, {
                        "type": "GUARDRAIL_ABORT",
                        "status": "ERROR",
                        "current_step_description": f"Step credits {step_delta} exceeded cap {max_step}. Aborting.",
                    })
                    try:
                        await log_security_event(
                            event_type="guardrail_abort",
                            user_id=self.user_id,
                            tenant_id=self.tenant_id,
                            details={"job_id": self.job_id, "reason": "step_cap", "step_delta_credits": step_delta, "max_step_credits": max_step},
                        )
                    except Exception:
                        pass
                    break
                if max_total > 0 and total_credits > max_total:
                    await publish_execution_trace(self.job_id, {
                        "type": "GUARDRAIL_ABORT",
                        "status": "ERROR",
                        "current_step_description": f"Total credits {total_credits} exceeded cap {max_total}. Aborting.",
                    })
                    try:
                        await log_security_event(
                            event_type="guardrail_abort",
                            user_id=self.user_id,
                            tenant_id=self.tenant_id,
                            details={"job_id": self.job_id, "reason": "total_cap", "total_credits": total_credits, "max_total_credits": max_total},
                        )
                    except Exception:
                        pass
                    break
            except Exception:
                pass
        return task_results

    def _synthesize_results(self, task_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize the results from all team tasks into a final response.
        """
        synthesis = "Final synthesis of all task results:\n"
        for task_id, result in task_results.items():
            synthesis += f"\n- Task {task_id}: {result.get('output', 'No output')}"

        return {"final_result": synthesis}


async def orchestrate_goal_task(
    job_id: str,
    goal_description: str,
    user_id: int,
    tenant_id: int,
) -> Dict[str, Any]:
    """
    Celery task entry for executing a goal orchestration job.
    """
    try:
        # Transition: QUEUED -> RUNNING (DB + PubSub)
        try:
            async with get_scoped_session() as session:
                res = await session.exec(select(Job).where(Job.job_id == job_id))
                job = res.first()
                if job:
                    job.update_status(JobStatus.RUNNING)
                    session.add(job)
            await publish_job_status(job_id, {
                "job_id": job_id,
                "status": "RUNNING",
                "current_step_description": "Goal orchestration started",
            })
        except Exception:
            # Do not fail the job if status update/publish fails
            pass

        orchestrator = GoalOrchestrator(
            goal=goal_description,
            user_id=user_id,
            tenant_id=tenant_id,
            job_id=job_id,
        )
        result = await orchestrator.execute()

        # Determine success/failure from orchestrator result
        is_failure = isinstance(result, dict) and result.get("success") is False

        if is_failure:
            err_msg = str(result.get("error") or "Execution failed")
            print(f"LOGIC FAILURE in orchestrate_goal_task for job {job_id}: {err_msg}")
            # Special-case cancellation to publish CANCELLED terminal state
            if err_msg.upper() == "CANCELLED":
                try:
                    async with get_scoped_session() as session:
                        res = await session.exec(select(Job).where(Job.job_id == job_id))
                        job = res.first()
                        if job:
                            job.update_status(JobStatus.CANCELLED)
                            session.add(job)
                    await publish_job_status(job_id, {
                        "job_id": job_id,
                        "status": "CANCELLED",
                        "message": "Stop acknowledged",
                    })
                except Exception:
                    pass
                return {"success": False, "error": err_msg, "job_id": job_id}

            # Special-case approval gating: this is not a failure; UI must drive next step.
            if err_msg.upper() == "PENDING_APPROVAL":
                try:
                    async with get_scoped_session() as session:
                        res = await session.exec(select(Job).where(Job.job_id == job_id))
                        job = res.first()
                        if job:
                            job.update_status(JobStatus.PENDING_APPROVAL)
                            session.add(job)
                    await publish_job_status(job_id, {
                        "job_id": job_id,
                        "status": "PENDING_APPROVAL",
                        "message": "Awaiting user approval",
                    })
                except Exception:
                    pass
                return {"success": False, "error": "PENDING_APPROVAL", "job_id": job_id}
            try:
                async with get_scoped_session() as session:
                    res = await session.exec(select(Job).where(Job.job_id == job_id))
                    job = res.first()
                    if job:
                        job.error_message = err_msg
                        job.update_status(JobStatus.FAILED)
                        session.add(job)
                await publish_job_status(job_id, {
                    "job_id": job_id,
                    "status": "FAILED",
                    "error_message": err_msg,
                })
            except Exception:
                pass
            return {"success": False, "error": err_msg, "job_id": job_id}

        # Success path: persist output summary and mark COMPLETED
        try:
            async with get_scoped_session() as session:
                res = await session.exec(select(Job).where(Job.job_id == job_id))
                job = res.first()
                if job:
                    # Persist a compact summary in output_data
                    try:
                        job.set_output_data(result if isinstance(result, dict) else {"result": result})
                    except Exception:
                        pass
                    job.update_status(JobStatus.COMPLETED)
                    session.add(job)
            await publish_job_status(job_id, {
                "job_id": job_id,
                "status": "COMPLETED",
                "message": "Goal orchestration completed",
            })
        except Exception:
            pass

        return {"success": True, "result": result, "job_id": job_id}
    except Exception as e:
        # Fatal error path: mark FAILED and publish
        print(f"FATAL ERROR in orchestrate_goal_task for job {job_id}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            async with get_scoped_session() as session:
                res = await session.exec(select(Job).where(Job.job_id == job_id))
                job = res.first()
                if job:
                    job.error_message = str(e)
                    job.update_status(JobStatus.FAILED)
                    session.add(job)
            await publish_job_status(job_id, {
                "job_id": job_id,
                "status": "FAILED",
                "error_message": str(e),
            })
        except Exception as inner_e:
            print(f"ERROR updating job status after failure: {type(inner_e).__name__}: {str(inner_e)}")
        logger.exception(f"Error in orchestrate_goal_task for job {job_id}")
        return {"success": False, "error": str(e), "job_id": job_id}


@celery_app.task(
    bind=True,
    name="goal_orchestrator.execute_goal",
    ignore_result=True,  # API doesn't wait for result; avoids result backend connection issues
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def execute_goal_celery_task(self, job_id: str, goal_description: str, user_id: int, tenant_id: int) -> Dict[str, Any]:
    """
    Celery task entry point for goal orchestration.
    
    This task is executed on the Celery worker (etherion-worker Cloud Run service),
    not in the API process. This ensures:
    - Reliable execution independent of API request lifecycle
    - Cloud Run scaling doesn't kill the orchestration mid-execution
    - Full async concurrency for platform/team/specialist orchestrators
    
    Args:
        job_id: The job ID to execute
        goal_description: The user's goal description
        user_id: Database user ID (not OAuth subject)
        tenant_id: Tenant ID for multi-tenancy
    
    Returns:
        Dict with execution result
    """
    import asyncio
    logger.info(f"[Celery Worker] Starting goal orchestration for job {job_id}")

    # Reuse a single event loop per worker process to avoid cross-loop asyncpg/Redis issues.
    global _CELERY_WORKER_LOOP
    try:
        _CELERY_WORKER_LOOP  # type: ignore[name-defined]
    except Exception:
        _CELERY_WORKER_LOOP = None  # type: ignore[assignment]

    loop = _CELERY_WORKER_LOOP
    if loop is None or getattr(loop, "is_closed", lambda: True)():
        loop = asyncio.new_event_loop()
        _CELERY_WORKER_LOOP = loop
    asyncio.set_event_loop(loop)
    try:
        try:
            loop.run_until_complete(
                publish_execution_trace(
                    job_id,
                    {
                        "type": "EXECUTION_START",
                        "step_description": "Worker accepted job for execution",
                    },
                )
            )
        except Exception:
            logger.warning("Failed to publish execution start trace for job %s", job_id)

        result = loop.run_until_complete(
            orchestrate_goal_task(
                job_id=job_id,
                goal_description=goal_description,
                user_id=user_id,
                tenant_id=tenant_id,
            )
        )
        logger.info(f"[Celery Worker] Completed goal orchestration for job {job_id}")
        return result
    except Exception as e:
        logger.error(f"[Celery Worker] Failed goal orchestration for job {job_id}: {e}")
        raise
    finally:
        # Do not close the shared worker loop.
        pass
