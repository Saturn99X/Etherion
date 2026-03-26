"""
Team Orchestrator - Team-level orchestrator implementing 2N+1 reasoning loop.

This module implements the Team Orchestrator as specified in the dual orchestrator architecture.
The Team Orchestrator handles:
- Coordinates specialist agents within assigned team
- Executes 2N+1 reasoning (N specialist steps + 1 synthesis)
- Limited to pre-approved tools and agents
- User personality-aware execution
- Team-scoped operations
"""

import logging
import inspect
import asyncio as _asyncio
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import time
import sys

from src.database.db import get_db, session_scope
from sqlalchemy import text, or_
from src.database.models import AgentTeam, UserObservation, Tenant, StepType
from src.utils.tenant_context import get_tenant_context
from src.core.security.audit_logger import log_security_event
from src.services.user_observation_service import get_user_observation_service
from src.services.orchestrator_runtime import build_runtime_from_config
from src.services.pricing.cost_tracker import CostTracker
import src.core.redis as core_redis
from src.services.tool_instrumentation import instrument_base_tool
from src.services.agent_loader import get_agent_loader
from src.services.action_schema import Plan, parse_plan_dict
import src.tools.unified_research_tool as unified_research_tool_mod
from src.utils.agent_as_tool import agent_to_tool
from src.services.specialist_retry import retry_specialist_invocation

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

def _get_replay_service_safe():
    try:
        from src.services.replay_service import get_replay_service
        return get_replay_service()
    except Exception:
        return None

class TeamOrchestrator:
    """
    Team-level orchestrator implementing 2N+1 reasoning loop:
    - Coordinates specialist agents within assigned team
    - Executes 2N+1 reasoning (N specialist steps + 1 synthesis)
    - Limited to pre-approved tools and agents
    - User personality-aware execution
    """

    def __init__(self, team_id: str, tenant_id: int, user_id: int):
        self.team_id = team_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.team_config = None
        self.approved_tools = []
        self.specialist_agents = []
        self.orchestrator_runtime = None

    async def execute_2n_plus_1_loop(self, goal: str, team_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute 2N+1 reasoning with team specialists and allowed tools."""
        # Load team configuration
        self.team_config = await self._load_team_config(team_config)

        # Try to enrich from DB (fail-open)
        try:
            loader = get_agent_loader()
            loaded = await loader.load_agent_team(
                agent_team_id=self.team_id,
                tenant_id=self.tenant_id,
                job_id=str(team_config.get('job_id', f"job_{uuid.uuid4().hex[:8]}")),
                user_id=self.user_id,
            )
            if loaded:
                self.team_config['specialist_agents'] = loaded.get('custom_agents', [])
                self.team_config['approved_tools'] = loaded.get('pre_approved_tools', [])
        except Exception:
            pass

        self.approved_tools = self.team_config.get('approved_tools', [])
        self.specialist_agents = self.team_config.get('specialist_agents', [])

        # Wrap specialists as tools to unify invocation path
        try:
            loader = get_agent_loader()
            wrapped_tools = []
            for sa in (self.specialist_agents or []):
                try:
                    exec_inst = loader.create_agent_executor(sa, tenant_id=self.tenant_id, job_id=str(team_config.get('job_id')))
                    if not exec_inst:
                        continue

                    class _ExecAdapter:
                        def __init__(self, underlying):
                            self._u = underlying

                        async def ainvoke(self, payload: dict) -> dict:
                            instr = payload.get("input")
                            try:
                                si = getattr(instr, "specific_instruction", None) or (
                                    instr.get("specific_instruction") if isinstance(instr, dict) else None
                                )
                            except Exception:
                                si = None
                            instruction = si or (instr if isinstance(instr, str) else str(instr))
                            if hasattr(self._u, 'execute'):
                                if _asyncio.iscoroutinefunction(self._u.execute):
                                    res = await self._u.execute(instruction=instruction)
                                else:
                                    res = self._u.execute(instruction=instruction)
                            else:
                                res = {"output": "unsupported specialist executor"}
                            return {"output": (res.get("output") if isinstance(res, dict) else str(res))}

                    adapter = _ExecAdapter(exec_inst)
                    tool = agent_to_tool(adapter, name=sa.get('name') or sa.get('agent_id'), description=sa.get('description') or 'Specialist agent')
                    wrapped_tools.append({
                        'name': sa.get('name') or sa.get('agent_id'),
                        'instance': tool,
                        'type': 'specialist_tool',
                        'specialist_agent_id': sa.get('agent_id'),
                    })
                except Exception:
                    continue
            if wrapped_tools:
                self.approved_tools.extend(wrapped_tools)
        except Exception:
            pass

        # Load user personality context (support sync/async monkeypatches)
        _maybe_ctx = self._load_user_personality_context()
        user_context = await _maybe_ctx if inspect.isawaitable(_maybe_ctx) else _maybe_ctx

        # Load mandatory KB paradigm instructions
        kb_paradigm_supplement = ""
        try:
            from src.prompts.kb_paradigm_instructions import MANDATORY_KB_PARADIGM_INSTRUCTIONS, get_mandatory_tool_instructions
            kb_paradigm_supplement = MANDATORY_KB_PARADIGM_INSTRUCTIONS
            # Add tool usage instructions with approved tool names
            tool_names = [t.get('name') for t in (self.approved_tools or []) if t.get('name')]
            kb_paradigm_supplement += get_mandatory_tool_instructions(tool_names)
        except Exception:
            pass

        # Create runtime
        orchestrator_config = {
            'runtime_profile_name': 'team_orchestrator',
            'execution_context': {
                'user_id': self.user_id,
                'tenant_id': self.tenant_id,
                'team_id': self.team_id,
                'job_id': str(team_config.get('job_id', f"job_{uuid.uuid4().hex[:8]}")),
                'approved_tools': self.approved_tools,
                'specialist_agents': self.specialist_agents,
                'kb_paradigm_supplement': kb_paradigm_supplement,  # Mandatory KB instructions
            },
            'observation_context': user_context,
        }

        # Inject LLM hints from job metadata (provider/model) so runtime can route deterministically.
        try:
            job_id_hint = str(orchestrator_config['execution_context'].get('job_id') or "")
            if job_id_hint:
                from sqlmodel import select
                from src.database.db import session_scope
                from src.database.models import Job
                with session_scope() as session:
                    job = session.query(Job).filter(Job.job_id == job_id_hint).first()
                    if job:
                        md = job.get_job_metadata() or {}
                        if isinstance(md, dict):
                            provider = md.get("provider")
                            model = md.get("model")
                            if isinstance(provider, str) and provider.strip():
                                orchestrator_config['execution_context']['llm_provider'] = provider
                            if isinstance(model, str) and model.strip():
                                orchestrator_config['execution_context']['llm_model'] = model
        except Exception:
            pass

        self.orchestrator_runtime = build_runtime_from_config(orchestrator_config)
        job_id = str(orchestrator_config['execution_context']['job_id'])
        replay_svc = _get_replay_service_safe()

        # Log execution start
        try:
            await log_security_event(
                event_type="team_orchestration_started",
                user_id=str(self.user_id),
                tenant_id=str(self.tenant_id),
                details={"team_id": self.team_id, "job_id": job_id},
            )
        except Exception:
            pass

        # Execution trace start
        try:
            await core_redis.publish_execution_trace(
                job_id=job_id,
                event_data={
                    "type": "execution_trace_start",
                    "step_description": f"Team {self.team_id} started orchestration",
                    "tenant_id": self.tenant_id,
                },
            )
        except Exception:
            pass

        # TEAM_LOAD summary
        # Separate actual tools from specialist tool wrappers for accurate telemetry
        try:
            actual_tools = []
            specialist_tool_wrappers = []
            for t in (self.approved_tools or []):
                t_name = t.get('name') if isinstance(t, dict) else None
                t_type = t.get('type') if isinstance(t, dict) else None
                if t_type == 'specialist_tool':
                    specialist_tool_wrappers.append(t_name)
                elif t_name:
                    actual_tools.append(t_name)

            # LOG: Team configuration loaded
            specialist_names = [sa.get('name') for sa in (self.specialist_agents or [])]
            _log_trace(job_id, "TEAM_LOAD", "Team configuration loaded",
                       team_id=self.team_id,
                       specialist_count=len(self.specialist_agents or []),
                       tool_count=len(actual_tools),
                       specialists=str(specialist_names),
                       tools=str(actual_tools))

            if replay_svc:
                await replay_svc.record_step(
                    job_id=job_id,
                    tenant_id=self.tenant_id,
                    actor="system",
                    event_type="status",
                    step_type=StepType.OBSERVATION,
                    thought="Team configuration loaded",
                    raw_data={
                        "specialist_count": len(self.specialist_agents or []),
                        "tool_count": len(actual_tools),
                        "specialists": [sa.get('name') for sa in (self.specialist_agents or [])],
                        "tools": actual_tools,
                        "specialist_tool_wrappers": specialist_tool_wrappers,
                    }
                )

            await core_redis.publish_execution_trace(
                job_id=job_id,
                event_data={
                    "type": "TEAM_LOAD",
                    "step_description": "Team configuration loaded",
                    "specialist_count": len(self.specialist_agents or []),
                    "tool_count": len(actual_tools),
                    "specialists": [sa.get('name') for sa in (self.specialist_agents or [])],
                    "tools": actual_tools,
                    "specialist_tool_wrappers": specialist_tool_wrappers,
                },
            )
        except Exception:
            pass

        observations: List[Dict[str, Any]] = []
        allowed_tool_names = {t.get('name') for t in (self.approved_tools or [])}
        allowed_specialist_ids = {sa.get('agent_id') for sa in (self.specialist_agents or [])}
        max_steps = int(self.team_config.get('max_iterations') or 5)
        finished = False
        think_text = ""

        for step in range(max_steps):
            # STOP before new step
            try:
                if await core_redis.is_job_cancelled(job_id):
                    await core_redis.publish_execution_trace(job_id, {"type": "STOP_ACK", "step_description": "Team stop acknowledged", "step": step})
                    break
            except Exception:
                pass

            # THINK
            _log_trace(job_id, "THINK_START", f"Starting THINK phase", step=step, observations_count=len(observations))
            try:
                think_cfg = {
                    **orchestrator_config,
                    'execution_context': {**orchestrator_config['execution_context'], 'llm_mode': 'THINK', 'observations': observations, 'step': step},
                }
                self.orchestrator_runtime = build_runtime_from_config(think_cfg)
                think_res = await self.orchestrator_runtime.ainvoke({
                    "input": goal,
                    "metadata": {"job_id": job_id}
                })
                think_text = think_res.get("output", "")
                
                # LOG: THINK completed
                _log_trace(job_id, "THINK_END", f"THINK phase completed",
                           step=step,
                           thought_preview=str(think_text)[:200] if think_text else "(empty)")

                # Phase A: Record THINK turn for replay
                try:
                    if replay_svc:
                        await replay_svc.record_step(
                            job_id=job_id,
                            tenant_id=self.tenant_id,
                            actor="orchestrator",
                            event_type="think",
                            step_type=StepType.THOUGHT,
                            thought=think_text,
                            raw_data=think_res.get("analytics", {}),
                        )
                except Exception:
                    pass
            except Exception as e:
                _log_trace(job_id, "THINK_ERROR", f"THINK phase failed: {e}", step=step)
                think_text = ""

            # ACT
            _log_trace(job_id, "ACT_START", f"Starting ACT phase", step=step)
            try:
                act_cfg = {
                    **orchestrator_config,
                    'execution_context': {**orchestrator_config['execution_context'], 'llm_mode': 'ACT', 'observations': observations, 'step': step},
                }
                self.orchestrator_runtime = build_runtime_from_config(act_cfg)
                act_prompt = "Propose the next minimal set of actions as a JSON Plan."
                act_res = await self.orchestrator_runtime.ainvoke({
                    "input": act_prompt,
                    "metadata": {"job_id": job_id}
                })
                act_text = act_res.get("output", "{}")
                
                # LOG: ACT completed
                _log_trace(job_id, "ACT_END", f"ACT phase completed",
                           step=step,
                           plan_preview=str(act_text)[:300] if act_text else "(empty)")

                # Phase A: Record ACT turn (Plan) for replay
                try:
                    if replay_svc:
                        await replay_svc.record_step(
                            job_id=job_id,
                            tenant_id=self.tenant_id,
                            actor="orchestrator",
                            event_type="plan",
                            step_type=StepType.THOUGHT,
                            thought="Action plan proposed",
                            raw_data={"plan": act_text, "analytics": act_res.get("analytics", {})},
                        )
                except Exception:
                    pass

                try:
                    plan_obj = parse_plan_dict(json.loads(act_text))
                except Exception:
                    plan_obj = Plan(actions=[])
                    _log_trace(job_id, "PLAN_INVALID", "ACT output was not valid JSON; falling back to deterministic specialist sequence",
                               step=step, plan_preview=str(act_text)[:200])
                    try:
                        await core_redis.publish_execution_trace(
                            job_id,
                            {
                                "type": "PLAN_INVALID",
                                "step_description": "ACT output was not valid JSON; falling back to deterministic specialist sequence",
                                "step": step,
                                "plan_preview": str(act_text)[:500],
                            },
                        )
                    except Exception:
                        pass

                if not getattr(plan_obj, "actions", None):
                    _log_trace(job_id, "PLAN_EMPTY", "Plan parse produced 0 actions; falling back to deterministic specialist sequence",
                               step=step)
                    try:
                        await core_redis.publish_execution_trace(
                            job_id,
                            {
                                "type": "PLAN_EMPTY",
                                "step_description": "Plan parse produced 0 actions; falling back to deterministic specialist sequence",
                                "step": step,
                                "plan_preview": str(act_text)[:500],
                            },
                        )
                    except Exception:
                        pass

                    try:
                        fallback_actions = []
                        for _sa in (self.specialist_agents or []):
                            _sid = _sa.get("agent_id")
                            if _sid:
                                fallback_actions.append(
                                    {
                                        "type": "specialist",
                                        "target_specialist_id": _sid,
                                        "input": {
                                            "instruction": (
                                                f"Goal: {goal}\n"
                                                "Provide your specialist contribution. Be concise and correct."
                                            )
                                        },
                                    }
                                )

                        fallback_actions.append({"type": "finish"})

                        plan_obj = parse_plan_dict({"actions": fallback_actions})
                        _log_trace(job_id, "PLAN_FALLBACK", f"Using fallback plan with {len(fallback_actions)} actions", step=step)
                    except Exception:
                        plan_obj = Plan(actions=[])
                # Emit JSON plan trace so UI and tests can validate action_schema-shaped output
                try:
                    actions_payload = []
                    for _a in getattr(plan_obj, 'actions', []) or []:
                        try:
                            actions_payload.append(
                                {
                                    "type": getattr(_a, "type", None),
                                    "name": getattr(_a, "name", None),
                                    "input": getattr(_a, "input", None),
                                    "target_specialist_id": getattr(_a, "target_specialist_id", None),
                                    "idempotency_key": getattr(_a, "idempotency_key", None),
                                    "timeout_seconds": getattr(_a, "timeout_seconds", None),
                                }
                            )
                        except Exception:
                            continue
                    if actions_payload:
                        # LOG: Plan proposed
                        action_types = [a.get("type") for a in actions_payload]
                        action_names = [a.get("name") or a.get("target_specialist_id") for a in actions_payload]
                        _log_trace(job_id, "PLAN", f"Plan proposed with {len(actions_payload)} actions",
                                   step=step,
                                   action_types=str(action_types),
                                   action_names=str(action_names))
                        
                        await core_redis.publish_execution_trace(
                            job_id,
                            {
                                "type": "PLAN",
                                "step_description": "JSON tool plan proposed",
                                "actions": actions_payload,
                                "step": step,
                            },
                        )
                except Exception:
                    pass
            except Exception as e:
                _log_trace(job_id, "ACT_ERROR", f"ACT phase failed: {e}", step=step)
                plan_obj = Plan(actions=[])

            # Pre-append deny notices for disallowed tools/specialists (ensures visibility even if plan short-circuits)
            try:
                for _a in getattr(plan_obj, 'actions', []) or []:
                    if getattr(_a, 'type', None) == 'tool':
                        _nm = (getattr(_a, 'name', None) or "")
                        if _nm and _nm not in allowed_tool_names:
                            _log_trace(job_id, "TOOL_DENIED", f"Tool '{_nm}' not in allowed list", step=step)
                            observations.append({"type": "error", "message": f"Tool '{_nm}' not allowed"})
                    if getattr(_a, 'type', None) == 'specialist':
                        _sid = (getattr(_a, 'target_specialist_id', None) or "")
                        if _sid and _sid not in allowed_specialist_ids:
                            _log_trace(job_id, "SPECIALIST_DENIED", f"Specialist '{_sid}' not in allowed list", step=step)
                            observations.append({"type": "error", "message": f"Specialist '{_sid}' not allowed"})
            except Exception:
                pass

            # Dispatch actions
            _log_trace(job_id, "DISPATCH_START", f"Dispatching {len(plan_obj.actions)} actions", step=step)
            for idx, action in enumerate(plan_obj.actions):

                # Model-initiated cancel request
                if action.type == 'request_stop':
                    _log_trace(job_id, "STOP_REQUEST", "Model requested stop", step=step, index=idx)
                    try:
                        await core_redis.publish_execution_trace(job_id, {"type": "STOP_INTENT", "index": idx, "step": step})
                        try:
                            await core_redis.set_job_cancel(job_id)
                        except Exception:
                            pass
                        await core_redis.publish_execution_trace(job_id, {"type": "STOP_ACK", "step_description": "Model requested stop", "index": idx, "step": step})
                    except Exception:
                        pass
                    observations.append({"type": "stop_requested", "message": "Model requested cancellation"})
                    finished = True
                    break

                if action.type == 'finish':
                    _log_trace(job_id, "FINISH", "Received finish signal", step=step, index=idx)
                    observations.append({"type": "finish", "message": "Received finish signal"})
                    try:
                        await core_redis.publish_execution_trace(job_id, {"type": "OBS_RECEIVED", "index": idx, "step": step})
                    except Exception:
                        pass
                    finished = True
                    break

                if action.type == 'tool':
                    name = action.name or ""
                    if name not in allowed_tool_names:
                        _log_trace(job_id, "TOOL_DENIED", f"Tool '{name}' not in allowed list", step=step, index=idx)
                        observations.append({"type": "error", "message": f"Tool '{name}' not allowed"})
                        try:
                            await core_redis.publish_execution_trace(job_id, {"type": "OBS_RECEIVED", "index": idx, "step": step})
                        except Exception:
                            pass
                        continue

                    # LOG: Tool start
                    tool_input_preview = dict(action.input or {})
                    if "content" in tool_input_preview:
                        tool_input_preview["content"] = str(tool_input_preview.get("content"))[:200]
                    _log_trace(job_id, "TOOL_START", f"Tool {name} starting",
                               step=step, index=idx, input_preview=str(tool_input_preview)[:300])
                    
                    # Emit tool start telemetry for hard evidence in trace stream.
                    try:
                        await core_redis.publish_execution_trace(
                            job_id,
                            {
                                "type": "TOOL_START",
                                "step_description": f"Tool {name} starting",
                                "tool": name,
                                "index": idx,
                                "step": step,
                                "input_preview": tool_input_preview,
                            },
                        )
                    except Exception:
                        pass
                    
                    # Phase A: Record tool start for replay
                    try:
                        if replay_svc:
                            await replay_svc.record_tool_call(
                                job_id=job_id,
                                tenant_id=self.tenant_id,
                                tool_name=name,
                                input_payload=action.input or {},
                            )
                    except Exception:
                        pass

                    # Known safe tool(s)
                    if name == 'unified_research_tool':
                        _t_start = time.monotonic()
                        try:
                            q = (action.input or {}).get('query')
                            enable_web = bool((action.input or {}).get('enable_web', False))
                            _log_trace(job_id, "TOOL_EXEC", f"Executing unified_research_tool",
                                       step=step, index=idx, query=str(q)[:100] if q else "(goal)", enable_web=enable_web)
                            result = await _asyncio.to_thread(
                                unified_research_tool_mod.unified_research_tool,
                                query=q or goal, 
                                tenant_id=str(self.tenant_id), 
                                job_id=job_id, 
                                enable_web=enable_web
                            )
                            duration_ms = int((time.monotonic() - _t_start) * 1000)
                            counts = {
                                "project": len(result.get("project_results", []) or []),
                                "personal": len(result.get("personal_results", []) or []),
                                "vector": len(result.get("vector_results", []) or []),
                                "web": len(result.get("web_results", []) or []),
                            }
                            observations.append({"type": "tool_result", "tool": name, "result": {"counts": counts}})
                            
                            # LOG: Tool end
                            _log_trace(job_id, "TOOL_END", f"Tool {name} completed",
                                       step=step, index=idx, duration_ms=duration_ms, success=True, counts=str(counts))
                            
                            # Phase A: Record tool end for replay
                            try:
                                if replay_svc:
                                    await replay_svc.record_tool_call(
                                        job_id=job_id,
                                        tenant_id=self.tenant_id,
                                        tool_name=name,
                                        input_payload=action.input or {},
                                        output_payload=result,
                                        duration_ms=int((time.monotonic() - _t_start) * 1000),
                                    )
                            except Exception:
                                pass

                            try:
                                await core_redis.publish_execution_trace(
                                    job_id,
                                    {
                                        "type": "TOOL_END",
                                        "step_description": f"Tool {name} completed",
                                        "tool": name,
                                        "index": idx,
                                        "step": step,
                                        "success": True,
                                        "duration_ms": int((time.monotonic() - _t_start) * 1000),
                                        "output_preview": {
                                            "counts": {
                                                "project": len(result.get("project_results", []) or []),
                                                "personal": len(result.get("personal_results", []) or []),
                                                "vector": len(result.get("vector_results", []) or []),
                                                "web": len(result.get("web_results", []) or []),
                                            }
                                        },
                                    },
                                )
                            except Exception:
                                pass

                            try:
                                await core_redis.publish_execution_trace(job_id, {"type": "ACTION_EXECUTED", "tool": name, "index": idx, "step": step})
                            except Exception:
                                pass
                        except Exception as e:
                            observations.append({"type": "error", "message": f"Tool '{name}' failed: {e}"})
                            # Phase A: Record tool error for replay
                            try:
                                if replay_svc:
                                    await replay_svc.record_tool_call(
                                        job_id=job_id,
                                        tenant_id=self.tenant_id,
                                        tool_name=name,
                                        input_payload=action.input or {},
                                        error=str(e),
                                        duration_ms=int((time.monotonic() - _t_start) * 1000),
                                    )
                            except Exception:
                                pass

                            try:
                                await core_redis.publish_execution_trace(
                                    job_id,
                                    {
                                        "type": "TOOL_END",
                                        "step_description": f"Tool {name} failed",
                                        "tool": name,
                                        "index": idx,
                                        "step": step,
                                        "success": False,
                                        "error": str(e),
                                        "duration_ms": int((time.monotonic() - _t_start) * 1000),
                                    },
                                )
                            except Exception:
                                pass

                        try:
                            await core_redis.publish_execution_trace(job_id, {"type": "OBS_RECEIVED", "index": idx, "step": step})
                        except Exception:
                            pass
                    else:
                        # Generic execution via pre-approved tool instances
                        _t_start = time.monotonic()
                        try:
                            tool_entry = next((t for t in (self.approved_tools or []) if t.get('name') == name), None)
                            inst = tool_entry.get('instance') if isinstance(tool_entry, dict) else None
                            if inst is None:
                                observations.append({"type": "error", "message": f"Tool '{name}' instance not available"})
                                # Emit TOOL_END failure telemetry for missing tool instance
                                try:
                                    await core_redis.publish_execution_trace(
                                        job_id,
                                        {
                                            "type": "TOOL_END",
                                            "step_description": f"Tool {name} failed - instance not available",
                                            "tool": name,
                                            "index": idx,
                                            "step": step,
                                            "success": False,
                                            "error": f"Tool '{name}' instance not available in approved_tools",
                                            "duration_ms": int((time.monotonic() - _t_start) * 1000),
                                        },
                                    )
                                except Exception:
                                    pass
                            elif hasattr(inst, 'execute') and callable(getattr(inst, 'execute')):
                                # EnhancedMCPTool pathway
                                op = (action.input or {}).get('operation')
                                if not op:
                                    observations.append({"type": "error", "message": f"Tool '{name}' requires 'operation' in input"})
                                else:
                                    params = {k: v for k, v in (action.input or {}).items() if k != 'operation'}
                                    params['job_id'] = job_id
                                    res = await inst.execute(tenant_id=str(self.tenant_id), operation=op, params=params)
                                    res_dict = res.to_dict() if hasattr(res, 'to_dict') else (res if isinstance(res, dict) else {"success": True, "data": res})
                                    observations.append({"type": "tool_result", "tool": name, "result": res_dict})
                                    
                                    # Phase A: Record tool end for replay
                                    try:
                                        if replay_svc:
                                            await replay_svc.record_tool_call(
                                                job_id=job_id,
                                                tenant_id=self.tenant_id,
                                                tool_name=name,
                                                input_payload=action.input or {},
                                                output_payload=res_dict,
                                                duration_ms=int((time.monotonic() - _t_start) * 1000),
                                                invocation_id=res_dict.get("invocation_id") if isinstance(res_dict, dict) else None
                                            )
                                    except Exception:
                                        pass

                                    try:
                                        await core_redis.publish_execution_trace(job_id, {"type": "ACTION_EXECUTED", "tool": name, "operation": op, "index": idx, "step": step})
                                    except Exception:
                                        pass
                            else:
                                # Function-based or LangChain Tool instance handling
                                params = dict(action.input or {})

                                # Only inject tenant_id/job_id if the tool schema supports it.
                                # This avoids breaking tools like fetch_document_content which do not accept tenant_id/job_id.
                                try:
                                    allowed_keys = None
                                    schema = getattr(inst, "args_schema", None)
                                    if schema is not None:
                                        try:
                                            # Pydantic v2
                                            allowed_keys = set(getattr(schema, "model_fields", {}).keys())
                                        except Exception:
                                            allowed_keys = None
                                        if not allowed_keys:
                                            try:
                                                # Pydantic v1
                                                allowed_keys = set(getattr(schema, "__fields__", {}).keys())
                                            except Exception:
                                                allowed_keys = None
                                    if allowed_keys is None and callable(inst):
                                        try:
                                            sig = inspect.signature(inst)
                                            allowed_keys = set(sig.parameters.keys())
                                        except Exception:
                                            allowed_keys = None
                                    if allowed_keys is None:
                                        # Unknown tool signature; do not inject.
                                        allowed_keys = set()

                                    if "tenant_id" in allowed_keys:
                                        params.setdefault("tenant_id", str(self.tenant_id))
                                    if "job_id" in allowed_keys:
                                        params.setdefault("job_id", job_id)
                                except Exception:
                                    pass

                                # File fetch telemetry (matches KB paradigm docs).
                                if name == "fetch_document_content":
                                    try:
                                        await core_redis.publish_execution_trace(
                                            job_id,
                                            {
                                                "type": "FILE_FETCH_START",
                                                "step_description": "Fetching full document content from GCS",
                                                "tool": name,
                                                "gcs_uri": (params.get("gcs_uri") if isinstance(params, dict) else None),
                                                "filename": (params.get("filename") if isinstance(params, dict) else None),
                                                "index": idx,
                                                "step": step,
                                            },
                                        )
                                    except Exception:
                                        pass
                                
                                if hasattr(inst, 'ainvoke') and callable(getattr(inst, 'ainvoke')):
                                    tool_type = tool_entry.get('type') if isinstance(tool_entry, dict) else None
                                    if tool_type == 'specialist_tool' and hasattr(inst, 'coroutine') and callable(getattr(inst, 'coroutine')):
                                        specialist_payload = {
                                            "original_user_goal": goal,
                                            "orchestrator_plan": "",
                                            "research_findings": {},
                                            "specific_instruction": params.get('instruction') or goal,
                                            "pitfalls_to_avoid": None,
                                            "context": {"step": step},
                                        }
                                        res = await inst.coroutine(json.dumps(specialist_payload), job_id=job_id)
                                    else:
                                        res = await inst.ainvoke(params)
                                    observations.append({"type": "tool_result", "tool": name, "result": res})
                                    
                                    # Phase A: Record tool end for replay
                                    try:
                                        if replay_svc:
                                            await replay_svc.record_tool_call(
                                                job_id=job_id,
                                                tenant_id=self.tenant_id,
                                                tool_name=name,
                                                input_payload=action.input or {},
                                                output_payload=res,
                                                duration_ms=int((time.monotonic() - _t_start) * 1000),
                                            )
                                    except Exception:
                                        pass

                                    try:
                                        await core_redis.publish_execution_trace(job_id, {"type": "ACTION_EXECUTED", "tool": name, "index": idx, "step": step})
                                    except Exception:
                                        pass

                                    # Tool end telemetry (truncated output preview).
                                    try:
                                        out_preview = res
                                        if isinstance(out_preview, dict):
                                            if "content" in out_preview:
                                                out_preview = {**out_preview, "content": str(out_preview.get("content"))[:500]}
                                        else:
                                            out_preview = str(out_preview)[:500]
                                        await core_redis.publish_execution_trace(
                                            job_id,
                                            {
                                                "type": "TOOL_END",
                                                "step_description": f"Tool {name} completed",
                                                "tool": name,
                                                "index": idx,
                                                "step": step,
                                                "success": True,
                                                "duration_ms": int((time.monotonic() - _t_start) * 1000),
                                                "output_preview": out_preview,
                                            },
                                        )
                                    except Exception:
                                        pass

                                    if name == "fetch_document_content":
                                        try:
                                            await core_redis.publish_execution_trace(
                                                job_id,
                                                {
                                                    "type": "FILE_FETCH_END",
                                                    "step_description": "Fetched full document content from GCS",
                                                    "tool": name,
                                                    "gcs_uri": (params.get("gcs_uri") if isinstance(params, dict) else None),
                                                    "filename": (params.get("filename") if isinstance(params, dict) else None),
                                                    "index": idx,
                                                    "step": step,
                                                    "success": True,
                                                },
                                            )
                                        except Exception:
                                            pass
                                elif hasattr(inst, 'invoke') and callable(getattr(inst, 'invoke')):
                                    res = inst.invoke(params)
                                    observations.append({"type": "tool_result", "tool": name, "result": res})
                                    
                                    # Phase A: Record tool end for replay
                                    try:
                                        if replay_svc:
                                            await replay_svc.record_tool_call(
                                                job_id=job_id,
                                                tenant_id=self.tenant_id,
                                                tool_name=name,
                                                input_payload=action.input or {},
                                                output_payload=res,
                                                duration_ms=int((time.monotonic() - _t_start) * 1000),
                                            )
                                    except Exception:
                                        pass

                                    try:
                                        await core_redis.publish_execution_trace(job_id, {"type": "ACTION_EXECUTED", "tool": name, "index": idx, "step": step})
                                    except Exception:
                                        pass
                                elif callable(inst):
                                    if _asyncio.iscoroutinefunction(inst):
                                        res = await inst(**params)
                                    else:
                                        res = inst(**params)
                                    observations.append({"type": "tool_result", "tool": name, "result": res})
                                    
                                    # Phase A: Record tool end for replay
                                    try:
                                        if replay_svc:
                                            await replay_svc.record_tool_call(
                                                job_id=job_id,
                                                tenant_id=self.tenant_id,
                                                tool_name=name,
                                                input_payload=action.input or {},
                                                output_payload=res,
                                                duration_ms=int((time.monotonic() - _t_start) * 1000),
                                            )
                                    except Exception:
                                        pass

                                    try:
                                        await core_redis.publish_execution_trace(job_id, {"type": "ACTION_EXECUTED", "tool": name, "index": idx, "step": step})
                                    except Exception:
                                        pass
                                else:
                                    observations.append({"type": "skip", "message": f"Tool '{name}' instance is not executable by dispatcher"})
                        except Exception as e:
                            observations.append({"type": "error", "message": f"Tool '{name}' dispatch error: {e}"})
                            # Phase A: Record tool error for replay
                            try:
                                if replay_svc:
                                    await replay_svc.record_tool_call(
                                        job_id=job_id,
                                        tenant_id=self.tenant_id,
                                        tool_name=name,
                                        input_payload=action.input or {},
                                        error=str(e),
                                        duration_ms=int((time.monotonic() - _t_start) * 1000),
                                    )
                            except Exception:
                                pass

                        try:
                            await core_redis.publish_execution_trace(job_id, {"type": "OBS_RECEIVED", "index": idx, "step": step})
                        except Exception:
                            pass
                    # STOP after action (before next one)
                    try:
                        if await core_redis.is_job_cancelled(job_id):
                            await core_redis.publish_execution_trace(job_id, {"type": "STOP_ACK", "step_description": "Team stop acknowledged", "step": step})
                            finished = True
                            break
                    except Exception:
                        pass
                    continue

                if action.type == 'specialist':
                    target_id = action.target_specialist_id or ""
                    if target_id not in allowed_specialist_ids:
                        _log_trace(job_id, "SPECIALIST_DENIED", f"Specialist '{target_id}' not in allowed list", step=step, index=idx)
                        observations.append({"type": "error", "message": f"Specialist '{target_id}' not allowed"})
                        try:
                            await core_redis.publish_execution_trace(job_id, {"type": "OBS_RECEIVED", "index": idx, "step": step})
                        except Exception:
                            pass
                        continue

                    # LOG: Specialist request
                    instr_preview = str((action.input or {}).get("instruction") or "")[:200]
                    _log_trace(job_id, "SPECIALIST_REQUEST", f"Dispatching specialist {target_id}",
                               step=step, index=idx, instruction_preview=instr_preview)
                    
                    # Explicit specialist telemetry for hard confirmation.
                    try:
                        await core_redis.publish_execution_trace(
                            job_id,
                            {
                                "type": "SPECIALIST_REQUEST",
                                "step_description": "Dispatching specialist",
                                "specialist_id": target_id,
                                "index": idx,
                                "step": step,
                                "instruction_preview": instr_preview,
                            },
                        )
                    except Exception:
                        pass
                    
                    # Phase A: Record specialist request for replay
                    try:
                        if replay_svc:
                            await replay_svc.record_specialist_call(
                                job_id=job_id,
                                tenant_id=self.tenant_id,
                                specialist_id=target_id,
                                specialist_name=target_id, # Fallback name
                                input_payload=action.input or {},
                            )
                    except Exception:
                        pass

                    # Execute specialist via AgentLoader executor with retry wrapper
                    try:
                        spec_cfg = next((s for s in (self.specialist_agents or []) if s.get('agent_id') == target_id), None)
                        if not spec_cfg:
                            _log_trace(job_id, "SPECIALIST_ERROR", f"Specialist '{target_id}' config not found", step=step, index=idx)
                            observations.append({"type": "error", "message": f"Specialist '{target_id}' config not found"})
                        else:
                            loader = get_agent_loader()
                            executor = loader.create_agent_executor(spec_cfg, tenant_id=self.tenant_id, job_id=job_id)
                            if executor and hasattr(executor, 'execute'):
                                instruction = (action.input or {}).get('instruction') or goal
                                _t_start = time.monotonic()
                                _log_trace(job_id, "SPECIALIST_EXEC", f"Executing specialist {target_id}",
                                           step=step, index=idx, specialist_name=str(spec_cfg.get('name') or target_id))
                                
                                # Wrap specialist execution with retry logic
                                async def _execute_specialist():
                                    return await executor.execute(instruction=instruction)
                                
                                out = await retry_specialist_invocation(
                                    _execute_specialist,
                                    max_retries=3,
                                    min_output_length=10
                                )
                                duration_ms = int((time.monotonic() - _t_start) * 1000)
                                
                                # LOG: Specialist response
                                out_preview_log = str(out)[:300] if out else "(empty)"
                                _log_trace(job_id, "SPECIALIST_RESPONSE", f"Specialist {target_id} responded",
                                           step=step, index=idx, duration_ms=duration_ms, success=True,
                                           specialist_name=str(spec_cfg.get('name') or target_id),
                                           output_preview=out_preview_log)
                                
                                observations.append({"type": "specialist_result", "specialist": target_id, "result": out})
                                
                                # Phase A: Record specialist response for replay
                                try:
                                    if replay_svc:
                                        await replay_svc.record_specialist_call(
                                            job_id=job_id,
                                            tenant_id=self.tenant_id,
                                            specialist_id=target_id,
                                            specialist_name=str(spec_cfg.get('name') or target_id),
                                            input_payload=action.input or {},
                                            output_payload=out,
                                            duration_ms=duration_ms,
                                        )
                                except Exception:
                                    pass

                                try:
                                    await core_redis.publish_execution_trace(job_id, {"type": "ACTION_EXECUTED", "specialist": target_id, "index": idx, "step": step, "duration_ms": duration_ms, "success": True})
                                except Exception:
                                    pass

                                try:
                                    out_preview = out
                                    if isinstance(out_preview, dict):
                                        if "output" in out_preview:
                                            out_preview = {**out_preview, "output": str(out_preview.get("output"))[:500]}
                                    else:
                                        out_preview = str(out_preview)[:500]
                                    await core_redis.publish_execution_trace(
                                        job_id,
                                        {
                                            "type": "SPECIALIST_RESPONSE",
                                            "step_description": "Specialist responded",
                                            "specialist_id": target_id,
                                            "specialist_name": str(spec_cfg.get("name") or target_id),
                                            "index": idx,
                                            "step": step,
                                            "success": True,
                                            "duration_ms": duration_ms,
                                            "output_preview": out_preview,
                                        },
                                    )
                                except Exception:
                                    pass
                            else:
                                _log_trace(job_id, "SPECIALIST_ERROR", f"Specialist '{target_id}' executor unavailable", step=step, index=idx)
                                observations.append({"type": "error", "message": f"Specialist '{target_id}' executor unavailable"})
                    except Exception as e:
                        _log_trace(job_id, "SPECIALIST_ERROR", f"Specialist '{target_id}' dispatch error: {e}", step=step, index=idx)
                        observations.append({"type": "error", "message": f"Specialist '{target_id}' dispatch error: {e}"})
                        # Phase A: Record specialist error for replay
                        try:
                            if replay_svc:
                                await replay_svc.record_specialist_call(
                                    job_id=job_id,
                                    tenant_id=self.tenant_id,
                                    specialist_id=target_id,
                                    specialist_name=target_id,
                                    input_payload=action.input or {},
                                    error=str(e),
                                )
                        except Exception:
                            pass

                    try:
                        await core_redis.publish_execution_trace(job_id, {"type": "OBS_RECEIVED", "index": idx, "step": step})
                    except Exception:
                        pass
                    # STOP after specialist action
                    try:
                        if await core_redis.is_job_cancelled(job_id):
                            await core_redis.publish_execution_trace(job_id, {"type": "STOP_ACK", "step_description": "Team stop acknowledged", "step": step})
                            finished = True
                            break
                    except Exception:
                        pass
                    continue

            if finished:
                break

        # Synthesis of final result
        try:
            current_think_text = think_text if 'think_text' in locals() else ""
        except NameError:
            current_think_text = ""

        synthesis = "\n".join([
            part for part in [current_think_text.strip(), "Observations:", json.dumps(observations) if observations else "(none)"] if part
        ])
        results = {"output": synthesis, "observations": observations, "metadata": {"job_id": job_id}}

        # Record token usage if available
        try:
            token_usage = results.get("analytics", {}).get("token_usage")
            if token_usage:
                tracker = CostTracker()
                await tracker.record_tokens(
                    job_id=job_id,
                    input_tokens=int(token_usage.get("input_tokens", 0)),
                    output_tokens=int(token_usage.get("output_tokens", 0)),
                )
        except Exception:
            pass

        # Execution trace end
        try:
            await core_redis.publish_execution_trace(
                job_id=job_id,
                event_data={
                    "type": "execution_trace_end",
                    "step_description": "Orchestration completed",
                    "tenant_id": self.tenant_id,
                },
            )
        except Exception:
            pass

        return results

    async def _load_team_config(self, team_config: Dict[str, Any]) -> Dict[str, Any]:
        """Load and validate team configuration. Returns fallback config if team not found."""
        with session_scope() as session:
            # Get team from database
            team = session.query(AgentTeam).filter(
                AgentTeam.agent_team_id == self.team_id,
                or_(
                    AgentTeam.tenant_id == self.tenant_id,
                    AgentTeam.is_system_agent == True
                ),
                AgentTeam.is_active == True
            ).first()

            if not team:
                # Graceful fallback: return minimal default config for missing teams
                # This allows new tenants to execute goals without pre-seeded teams
                logger.warning(f"Team {self.team_id} not found for tenant {self.tenant_id}, using fallback config")
                return {
                    'name': self.team_id,
                    'description': f'Dynamic team: {self.team_id}',
                    'approved_tools': [],  # Will be populated by agent_loader if available
                    'specialist_agents': [],
                    'max_iterations': 5,
                    **team_config
                }

            # Merge database config with provided config
            db_config = team.to_execution_config()
            merged_config = {**db_config, **team_config}

            return merged_config

    async def _load_user_personality_context(self) -> Dict[str, Any]:
        """Load user personality context for team execution"""
        observation_service = get_user_observation_service()
        observation = await observation_service.get_user_observations(self.user_id, self.tenant_id)

        if not observation:
            return self._create_default_context()

        return {
            "personality": {
                "preferred_tone": observation.preferred_tone,
                "response_length_preference": observation.response_length_preference,
                "technical_level": observation.technical_level,
                "formality_level": observation.formality_level,
                "patience_level": observation.patience_level,
                "detail_orientation": observation.detail_orientation,
                "risk_tolerance": observation.risk_tolerance,
                "decision_making_style": observation.decision_making_style,
                "learning_style": observation.learning_style
            },
            "success_patterns": {
                "successful_tools": observation.get_successful_tools(),
                "successful_approaches": observation.get_successful_approaches(),
                "failed_approaches": observation.get_failed_approaches()
            },
            "behavioral_patterns": {
                "peak_activity_hours": observation.get_peak_activity_hours(),
                "response_time_expectations": observation.response_time_expectations,
                "follow_up_frequency": observation.follow_up_frequency
            },
            "content_preferences": {
                "complexity_level": observation.complexity_level,
                "example_requirements": observation.example_requirements,
                "visual_vs_text": observation.visual_vs_text
            },
            "metadata": {
                "observation_count": observation.observation_count,
                "confidence_score": observation.confidence_score,
                "last_observation": observation.last_observation_at.isoformat() if observation.last_observation_at else None
            }
        }

    def _create_default_context(self) -> Dict[str, Any]:
        """Create default user context when no observations exist"""
        return {
            "personality": {
                "preferred_tone": "professional",
                "response_length_preference": "detailed",
                "technical_level": "intermediate",
                "formality_level": "medium",
                "patience_level": "medium",
                "detail_orientation": "medium",
                "risk_tolerance": "balanced",
                "decision_making_style": "analytical",
                "learning_style": "theoretical"
            },
            "success_patterns": {
                "successful_tools": [],
                "successful_approaches": [],
                "failed_approaches": []
            },
            "behavioral_patterns": {
                "peak_activity_hours": {},
                "response_time_expectations": "same-day",
                "follow_up_frequency": "occasional"
            },
            "content_preferences": {
                "complexity_level": "moderate",
                "example_requirements": "some",
                "visual_vs_text": "balanced"
            },
            "metadata": {
                "observation_count": 0,
                "confidence_score": 0.0,
                "last_observation": None
            }
        }

    async def validate_team_execution(self) -> Dict[str, Any]:
        """Validate team can execute with current configuration"""
        with session_scope() as session:
            team = session.query(AgentTeam).filter(
                AgentTeam.agent_team_id == self.team_id,
                or_(
                    AgentTeam.tenant_id == self.tenant_id,
                    AgentTeam.is_system_agent == True
                ),
                AgentTeam.is_active == True
            ).first()

            if not team:
                return {
                    "valid": False,
                    "error": f"Team {self.team_id} not found or inactive"
                }

            # Check if team is executable
            if not team.is_executable():
                return {
                    "valid": False,
                    "error": "Team is not in executable state"
                }

            # Check tool approvals
            approved_tools = team.get_pre_approved_tool_names()
            if not approved_tools:
                return {
                    "valid": False,
                    "error": "No tools approved for team"
                }

            # Check custom agents
            custom_agents = team.get_custom_agent_ids()
            if not custom_agents:
                return {
                    "valid": False,
                    "error": "No custom agents configured for team"
                }

            # Check execution limits
            current_executions = await self._get_current_executions()
            max_concurrent = team.max_concurrent_executions or 5

            if current_executions >= max_concurrent:
                return {
                    "valid": False,
                    "error": f"Maximum concurrent executions ({max_concurrent}) reached"
                }

            return {
                "valid": True,
                "team_info": {
                    "name": team.name,
                    "description": team.description,
                    "approved_tools": len(approved_tools),
                    "custom_agents": len(custom_agents),
                    "current_executions": current_executions,
                    "max_concurrent": max_concurrent
                }
            }

    async def _get_current_executions(self) -> int:
        """Get current number of executions for this team"""
        # This would query active executions for the team
        # For now, return a mock value
        return 1

    async def get_team_status(self) -> Dict[str, Any]:
        """Get comprehensive team status and configuration"""
        with session_scope() as session:
            team = session.query(AgentTeam).filter(
                AgentTeam.agent_team_id == self.team_id,
                or_(
                    AgentTeam.tenant_id == self.tenant_id,
                    AgentTeam.is_system_agent == True
                )
            ).first()

            if not team:
                return {"error": f"Team {self.team_id} not found"}

            validation = await self.validate_team_execution()

            return {
                "team_id": self.team_id,
                "tenant_id": self.tenant_id,
                "name": team.name,
                "description": team.description,
                "is_active": team.is_active,
                "version": team.version,
                "execution_count": team.execution_count,
                "last_executed": team.last_executed_at.isoformat() if team.last_executed_at else None,
                "configuration": team.to_execution_config(),
                "validation": validation,
                "created_at": team.created_at.isoformat(),
                "updated_at": team.last_updated_at.isoformat()
            }

    async def update_team_execution_stats(self, execution_time: float, success: bool) -> None:
        """Update team execution statistics"""
        with session_scope() as session:
            team = session.query(AgentTeam).filter(
                AgentTeam.agent_team_id == self.team_id,
                or_(
                    AgentTeam.tenant_id == self.tenant_id,
                    AgentTeam.is_system_agent == True
                )
            ).first()

            if team:
                team.increment_execution_count()
                session.commit()

                # Log execution completion
                await log_security_event(
                    event_type="team_execution_completed",
                    user_id=str(self.user_id),
                    tenant_id=str(self.tenant_id),
                    details={
                        "team_id": self.team_id,
                        "execution_time": execution_time,
                        "success": success,
                        "total_executions": team.execution_count
                    }
                )
