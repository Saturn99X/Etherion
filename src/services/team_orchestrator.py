"""
Team Orchestrator - Team-level orchestrator implementing checklist-based orchestration.

This module implements the Team Orchestrator as specified in the dual orchestrator architecture.
The Team Orchestrator handles:
- Coordinates specialist agents within assigned team
- Executes checklist-based specialist orchestration with validation
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
from src.config.orchestrator_runtime import get_orchestrator_profile
from src.services.pricing.cost_tracker import CostTracker
import src.core.redis as core_redis
from src.services.tool_instrumentation import instrument_base_tool
from src.services.agent_loader import get_agent_loader
from src.services.action_schema import Plan, parse_plan_dict
import src.tools.unified_research_tool as unified_research_tool_mod
from src.utils.agent_as_tool import agent_to_tool
from src.services.specialist_retry import retry_specialist_invocation
from src.services.orchestration.engine import OrchestrationEngine

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
    Team-level orchestrator implementing checklist-based orchestration:
    - Coordinates specialist agents within assigned team
    - Validates specialist outputs and gates tool requests
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

    async def execute_checklist_loop(self, goal: str, team_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute checklist-based orchestration with team specialists and allowed tools."""
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

        # ---- Checklist-based orchestration ----
        auto_approved_tool_names = []
        try:
            profile = get_orchestrator_profile("team_orchestrator")
            auto_approved_tool_names = list(profile.tool_policy.auto_approved_tools)
        except Exception:
            auto_approved_tool_names = ["search_personal_kb", "search_project_kb", "unified_research_tool", "confirm_action_tool", "generate_pdf_file", "generate_excel_file", "generate_presentation_file", "generate_image_file"]

        max_iterations = int(self.team_config.get('max_iterations') or 8)
        validation_threshold = 0.6
        try:
            profile = get_orchestrator_profile("team_orchestrator")
            validation_threshold = profile.validation.minimum_confidence
        except Exception:
            pass

        permission_mode = self.team_config.get("permission_mode", "bypass_permission")

        engine = OrchestrationEngine(
            goal=goal,
            job_id=job_id,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            team_id=self.team_id,
            orchestrator_runtime=self.orchestrator_runtime,
            approved_tools=self.approved_tools,
            specialist_agents=self.specialist_agents,
            max_iterations=max_iterations,
            validation_confidence_threshold=validation_threshold,
            auto_approved_tools=auto_approved_tool_names,
            permission_mode=permission_mode,
        )

        results = await engine.run()

        _log_trace(job_id, "ORCHESTRATION_END", "Checklist-based orchestration completed",
                   passed_steps=results.get("metadata", {}).get("passed_steps", 0),
                   failed_steps=results.get("metadata", {}).get("failed_steps", 0))

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
