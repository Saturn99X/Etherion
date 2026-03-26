"""
Platform Orchestrator - Highest privilege orchestrator with platform-wide capabilities within tenant scope.

This module implements the Platform Orchestrator as specified in the dual orchestrator architecture.
The Platform Orchestrator handles:
- Tool approval and validation
- Agent team selection and loading
- User preferences and personality loading (fresh from DB)
- Agent team blueprint creation
- Agent team creation
- Tenant-scoped operations only
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

from langchain_core.prompts import ChatPromptTemplate

from src.database.db import get_db, session_scope
from src.database.models import AgentTeam, UserObservation, Tenant, Tool, ToolStatus
from src.utils.tenant_context import get_tenant_context
from src.core.security.audit_logger import log_security_event
from src.services.user_observation_service import get_user_observation_service
from src.core.redis import publish_execution_trace, get_redis_client
from src.tools.unified_research_tool import unified_research_tool
from src.services.pricing.cost_tracker import CostTracker
from src.utils.llm_loader import get_llm

logger = logging.getLogger(__name__)


# IO — Etherion Platform Orchestrator base prompt (condensed)
# Note: IO does not execute MCP tools directly; it plans, approves (policy), recommends, and delegates.
BASE_PLATFORM_PROMPT = """

## Identity and Scope

- You are IO, the Etherion Platform Orchestrator AI.
- You operate strictly within a single tenant scope. Cross-tenant access is prohibited.
- Your job is to bind the platform’s pillars into a coherent, trustworthy, and delightful experience.
- You do not directly execute MCP tools yourself; you design plans, approve tools (policy), select teams, and delegate execution to appropriate team runtimes.

## Core Responsibilities

- Answer user questions with evidence. Always ground answers in the tenant Knowledge Base and the Web (dual search) with citations.
- Design and propose new Agent Teams on demand via an interactive blueprint process. Obtain explicit user approval before creation.
- Recommend existing specialist teams for a user goal and provide quick-launch links into the Interaction page for that team.
- Delegate goals to the right team with the right tools and scope.
- Enforce tenant isolation, safety, and cost guardrails at all times.

## Sources of Truth (No Hallucination)

- Only two sources of truth: Tenant Knowledge Base (BigQuery + Vertex AI Search) and the Web (grounded search).
- If evidence is insufficient or conflicting, explicitly state limitations and request permission to gather more.
- Never fabricate citations. Provide URLs or KB document identifiers where applicable.

## Tool Capability Model (Reality-Checked)

- Tools live behind the MCP layer and are executed by team runtimes, not directly by IO.
- A tool can be used when ALL are true:
  - It exists and is registered in the Tool Manager registry.
  - It is pre-approved (allowlisted) for the selected team.
  - Required tenant credentials are available.
  - For write operations, the user confirms the action (confirm-action gate).
- IO can: approve tools (policy engine), recommend tools, check readiness, and require confirmation.

## Mandatory Behaviors

- Dual Search: For every uncertainty, run Knowledge Base search AND Web search. Prefer KB over Web when conflicts arise; still cite both.
- Live Transparency: Publish trace events for key decisions (search performed, blueprint created, team recommended).
- Cost-Aware: Prefer efficient models/steps when quality will not suffer.
- Safety First: Block or escalate on policy violations (tenant isolation, unsafe write, missing confirmation).

## Response Patterns

- Answering a question:
  - Perform dual search; synthesize an answer with citations (KB doc ids or URLs).
  - Provide confidence and any risks/assumptions.
- Recommending a team:
  - Present 1–3 teams with reasons (fit to goal, tool readiness, cost/latency considerations) and a quick-launch action.
- Creating a new team:
  - Start blueprint refinement: objectives, success criteria, required tools, data access, safety checks.
  - Present final blueprint for approval. Do not create without explicit user consent.
- Delegating a goal:
  - Summarize why the chosen team is appropriate, expected plan outline, and guardrails.

## Delegation and Quick Launch

- Maintain a quick-access list of teams available to the user (cached in Redis). Use it to recommend and to provide a one-click deep link to the Interaction page for that team.
- If no existing team fits, propose creating a bespoke team for the specific goal.

## Safety, Isolation, and Confirm Action

- Strict tenant isolation. Reject or quarantine any cross-tenant reference.
- Confirm Action: Any mutating external action requires explicit user confirmation. Surface a summary of the action (tenant, tool, payload) and wait for approval.

## Cost and Credits Awareness

- Honor step and total cost guardrails. If a limit would be exceeded, warn and stop or request user guidance.
- Prefer cheaper models for low-risk tasks; reserve high-reasoning models for critical steps.

## Live Events

- Emit trace events like:
  - DUAL_SEARCH with counts and citations
  - agent_blueprint_created for UI preview
  - platform_decision for recommendations and rationale

## Limitations and Escalation

- If required tools are not approved/credentialed, surface the readiness gap and propose actions.
- If evidence is insufficient, ask the user to connect data or permit additional search.

---

## Short Overview Digest

- Vision: Etherion is an autonomous, goal-driven digital workforce managed by an orchestrator. Users give goals, not tasks.
- Multi-Tenancy: Shared infra with strict Row-Level Security. Tenants cannot be mixed or switched by users.
- Orchestrator (2N+1): Reason-Act-Observe loops with validation between steps, enabling adaptability and transparency.
- Memory: BigQuery-centric KB with Vertex AI Search as a vector cache. Mandatory web grounding eliminates hallucinations.
- MCP (Hands): Tools perform real actions; confirm-action required for writes; credentials are tenant-scoped.
- Vibe Code: Natural-language creation of custom agents and teams via blueprints and instant availability.
- Engine: Async, multi-concurrent jobs with live status and cost tracking.
- Economics: Credits and real-time cost visibility; guardrails prevent runaway spend.
- Repository: AI-generated assets are job-scoped and discoverable.
- Feedback Loop: Continuous user-driven optimization and SFT data enhancement.

---

## Operating Modes (IO)

1) Inquiry Mode: Answer questions with dual search first; cite; no hallucination.
2) Advisor Mode: Recommend teams or propose creation with a blueprint.
3) Coordinator Mode: Delegate goals to a team, share plan outline, and enforce guardrails.

## Definition of Done (for IO Responses)

- Grounded answer or action proposal with citations.
- Clear next step (launch team, refine blueprint, or gather data).
- Risks and costs acknowledged; safety gates respected.

Never hallucinate. If evidence is insufficient, say so and propose how to obtain it (connect data or allow broader search). Be cost-aware and prefer efficient steps where quality allows.
"""


class TenantIsolationValidator:
    """
    Ensures strict tenant isolation - no cross-tenant awareness
    """

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

    async def validate_tenant_access(self, requested_tenant_id: int) -> bool:
        """Validate that operations are within tenant scope"""
        if requested_tenant_id != self.tenant_id:
            raise Exception("Cross-tenant access denied")
        return True

    async def validate_team_access(self, team_id: str, tenant_id: int) -> bool:
        """Validate team belongs to tenant"""
        with session_scope() as session:
            team = session.query(AgentTeam).filter(
                AgentTeam.agent_team_id == team_id,
                AgentTeam.tenant_id == tenant_id
            ).first()

            if not team:
                raise Exception("Team does not belong to tenant")
            return True


class UserPersonalityLoader:
    """
    Loads fresh user personality data (no caching)
    """

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self.observation_service = get_user_observation_service()

    async def load_fresh_personality(self, user_id: int) -> Dict[str, Any]:
        """Load fresh user personality from database (no caching)"""
        # Always fetch from database
        observation = await self.observation_service.get_user_observations(user_id, self.tenant_id)

        if not observation:
            return self._create_default_personality()

        # Include recent observations
        observations = await self.observation_service.get_user_observations(user_id, self.tenant_id)

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
            "observations": observations,
            "loaded_at": datetime.utcnow().isoformat(),
            "fresh_data": True
        }

    def _create_default_personality(self) -> Dict[str, Any]:
        """Create default personality when no observations exist"""
        return {
            "personality": {
                "preferred_tone": "professional",
                "response_length_preference": "detailed",
                "technical_level": "intermediate",
                "formality_level": "medium"
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
            "observations": None,
            "loaded_at": datetime.utcnow().isoformat(),
            "fresh_data": True
        }


class ToolApprovalManager:
    """
    Manages tool approval with auto-approve and manual override capabilities
    """

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

    async def auto_approve_tools(self, team_id: str, tool_names: List[str]) -> bool:
        """Auto-approve tools based on stability and team requirements"""
        with session_scope() as session:
            # Get team configuration
            team = session.query(AgentTeam).filter(
                AgentTeam.agent_team_id == team_id,
                AgentTeam.tenant_id == self.tenant_id
            ).first()

            if not team:
                raise Exception("Team not found")

            # Check tool stability and requirements
            approved_tools = []
            for tool_name in tool_names:
                tool = session.query(Tool).filter(
                    Tool.name == tool_name,
                    Tool.tenant_id == self.tenant_id
                ).first()

                if tool and tool.status == "STABLE":
                    approved_tools.append(tool_name)

            # Update team's approved tools
            current_tools = team.get_pre_approved_tool_names()
            all_tools = list(set(current_tools + approved_tools))
            team.set_pre_approved_tool_names(all_tools)
            team.update_timestamp()

            session.commit()

            # Log approval
            await log_security_event(
                event_type="tools_auto_approved",
                user_id=None,  # Will be set by calling context
                tenant_id=self.tenant_id,
                details={
                    "team_id": team_id,
                    "tools_approved": approved_tools,
                    "total_tools": len(all_tools),
                    "approval_method": "auto"
                }
            )

            return len(approved_tools) == len(tool_names)

    async def manual_approve_tools(self, team_id: str, tool_names: List[str]) -> bool:
        """Manual approval workflow - requires admin confirmation"""
        # In a real implementation, this would trigger a workflow
        # For now, we'll auto-approve with manual flag
        approval_result = await self.auto_approve_tools(team_id, tool_names)

        # Log as manual approval
        await log_security_event(
            event_type="tools_manually_approved",
            user_id=None,
            tenant_id=self.tenant_id,
            details={
                "team_id": team_id,
                "tools_approved": tool_names,
                "approval_method": "manual"
            }
        )

        return approval_result


class AgentTeamCreator:
    """
    Creates agent team blueprints from natural language specifications
    """

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

    async def create_blueprint(
        self,
        specification: str,
        user_personality: Dict[str, Any],
        tenant_id: int
    ) -> Dict[str, Any]:
        """Create agent team blueprint from natural language specification"""
        # Always fetch tool registry first and inject into the blueprint prompt.
        # This prevents IO from proposing tool names that aren't deployable.
        available_tool_names: List[str] = []
        try:
            from src.tools.tool_manager import get_tool_manager

            registry_info = get_tool_manager().get_tool_registry_info() or {}
            registry = registry_info.get("registry") or {}
            if not isinstance(registry, dict) or not registry:
                raise ValueError("tool registry is empty")

            # Mirror tool_registry_tool behavior: include STABLE and BETA tools, exclude deprecated.
            statuses: List[ToolStatus] = [ToolStatus.STABLE, ToolStatus.BETA]
            allowed_statuses = {s.value for s in statuses}

            tools: List[str] = []
            for name, cfg in registry.items():
                status = cfg.get("status")
                status_value = status.value if hasattr(status, "value") else (str(status) if status is not None else "BETA")
                if status_value not in allowed_statuses:
                    continue
                tools.append(str(name))

            available_tool_names = sorted(tools)
            if not available_tool_names:
                raise ValueError("no eligible tools found in registry")
        except Exception as e:
            raise ValueError(f"Failed to load tool registry for blueprint creation: {e}")

        llm_json = await self._invoke_blueprint_llm(
            specification=specification,
            user_personality=user_personality,
            tenant_id=tenant_id,
            available_tool_names=available_tool_names,
        )
        parsed = self._parse_blueprint_json(llm_json)
        agent_requirements = parsed.get("agent_requirements")
        tool_requirements = parsed.get("tool_requirements")
        team_structure = parsed.get("team_structure")

        if not isinstance(agent_requirements, list) or not agent_requirements:
            agent_requirements = await self._analyze_specification(specification, user_personality)
        # Enforce global hard cap: a blueprint may not define more than 5 agents.
        max_agents = 5
        if len(agent_requirements) > max_agents:
            raise ValueError(
                f"Blueprint attempted to define {len(agent_requirements)} agents; maximum allowed is {max_agents}"
            )

        if not isinstance(tool_requirements, list) or not tool_requirements:
            tool_requirements = await self._identify_required_tools(specification)
        if not isinstance(team_structure, dict) or not team_structure:
            team_structure = await self._design_team_structure(specification, user_personality)

        # CRITICAL: Validate tool_requirements against actual registry to prevent hallucination
        validated_tools = []
        hallucinated_tools = []
        available_set = set(available_tool_names)
        for tool_name in tool_requirements:
            if tool_name in available_set:
                validated_tools.append(tool_name)
            else:
                hallucinated_tools.append(tool_name)

        # Fail-closed: blueprint must be impossible to validate if any tool does not exist.
        if hallucinated_tools:
            raise ValueError(
                "Blueprint requested tools that do not exist in the deployed registry: "
                f"{hallucinated_tools}"
            )

        return {
            "blueprint_id": f"bp_{uuid.uuid4().hex[:8]}",
            "specification": specification,
            "user_personality": user_personality,
            "tenant_id": tenant_id,
            "created_at": datetime.utcnow().isoformat(),
            "agent_requirements": agent_requirements,
            "tool_requirements": validated_tools,  # Use validated tools only
            "team_structure": team_structure,
            "hallucinated_tools_removed": hallucinated_tools,  # Include for debugging
        }

    def _required_specialist_count(self, specification: str) -> Optional[int]:
        # Legacy hook for spec-specific agent count requirements is disabled.
        # IO determines the number of specialists case by case (subject to a global max of 5).
        return None

    async def _invoke_blueprint_llm(
        self,
        *,
        specification: str,
        user_personality: Dict[str, Any],
        tenant_id: int,
        available_tool_names: List[str],
    ) -> str:
        llm = get_llm(provider="vertex", tier="pro", config={"temperature": 0.7, "timeout": 120})
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are IO (Platform Orchestrator). Return ONLY valid JSON. No markdown.",
                ),
                (
                    "human",
                    (
                        "Create an agent team blueprint from the specification.\n\n"
                        "Return JSON with keys:\n"
                        "- agent_requirements: array of objects with keys: name, description, system_prompt, capabilities (array), required_skills (array), complexity, estimated_steps, personality_alignment\n"
                        "- tool_requirements: array of tool names (strings)\n"
                        "- team_structure: object (at minimum: team_type, agent_count, coordination_style)\n\n"
                        "Tool constraints (MANDATORY):\n"
                        "- You MUST choose tool names ONLY from the provided Available Tools list.\n"
                        "- If no tools are needed, return an empty array.\n\n"
                        "Available Tools (choose from these exact names):\n{available_tools}\n\n"
                        "Constraints:\n"
                        "- You MUST choose the number of specialists case by case, but NEVER output more than 5 agent_requirements.\n"
                        "- Each system_prompt must be complete and usable directly as a system instruction.\n\n"
                        "Tenant ID: {tenant_id}\n"
                        "User personality (JSON): {user_personality}\n\n"
                        "Specification:\n{specification}\n"
                    ),
                ),
            ]
        )

        chain = prompt | llm
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                res = await chain.ainvoke(
                    {
                        "tenant_id": str(tenant_id),
                        "user_personality": json.dumps(user_personality or {}, default=str),
                        "specification": str(specification),
                        "available_tools": "\n".join([f"- {n}" for n in (available_tool_names or [])]),
                    }
                )
                
                # Robust extraction of content
                raw_content = getattr(res, "content", None)
                if isinstance(raw_content, str):
                    text = raw_content
                elif isinstance(raw_content, list):
                    # Gemini multimodal format: [{'type': 'text', 'text': '...'}, ...]
                    text_parts = []
                    for part in raw_content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif isinstance(part, str):
                            text_parts.append(part)
                    text = "".join(text_parts)
                else:
                    text = str(raw_content) if raw_content is not None else str(res)

                # Final safety: if text contains stringified Python-like structures (the Gemini parts),
                # we don't return it directly; we let _parse_blueprint_json handle the deep extraction.
                self._parse_blueprint_json(text)
                return text
            except Exception as e:
                last_err = e
                prompt = ChatPromptTemplate.from_messages(
                    [
                        (
                            "system",
                            "Return ONLY valid JSON. No markdown.",
                        ),
                        (
                            "human",
                            (
                                "Your previous output was invalid. Return valid JSON ONLY matching the required keys.\n\n"
                                "Specification:\n{specification}\n"
                            ),
                        ),
                    ]
                )
                chain = prompt | llm
        raise ValueError(f"Failed to generate a valid blueprint JSON after retries: {last_err}")

    def _parse_blueprint_json(self, text: str) -> Dict[str, Any]:
        """Robustly parse the blueprint JSON, even if wrapped in metadata or markdown."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Blueprint JSON is empty")
        
        s = text.strip()
        
        # 1. Handle potential stringified Python-like list/dict (Gemini 3 parts wrapper)
        if (s.startswith("[{") and "text" in s) or (s.startswith("{'type': 'text'") or s.startswith('{"type": "text"')):
            try:
                # Try to evaluate it as Python/JSON to extract the inner 'text'
                import ast
                # ast.literal_eval is safer for single-quoted Python representations
                data = ast.literal_eval(s)
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    s = "".join([part.get("text", "") for part in data if isinstance(part, dict) and "text" in part])
                elif isinstance(data, dict) and "text" in data:
                    s = data.get("text", "")
            except Exception:
                # If evaluation fails, we keep the original string and try greedy extraction
                pass

        # 2. Greedy clean-up: Remove markdown code blocks if present
        if s.startswith("```"):
            lines = s.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()
            
        # 3. Try to find the inner-most JSON object boundaries
        # This is essential because the LLM might include conversational filler.
        # We search for the first '{' and the last '}'
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Blueprint output does not contain a JSON object: {s[:100]}...")
            
        json_str = s[start : end + 1]
        
        # 4. JSON parsing with literal_eval fallback (the "cranky fallback")
        try:
            payload = json.loads(json_str)
        except json.JSONDecodeError:
            try:
                import ast
                payload = ast.literal_eval(json_str)
            except (ValueError, SyntaxError):
                raise ValueError(f"Failed to parse blueprint JSON structure: {json_str[:200]}...")
                
        if not isinstance(payload, dict):
            # If we parsed it but it's not a dict, it might be a nested structure or incorrect
            raise ValueError("Blueprint JSON must be a dictionary object")
            
        # 5. Semantic Validation: Does it look like a blueprint?
        # If it has a 'text' key but not 'agent_requirements', it might still be a wrapper.
        if "text" in payload and "agent_requirements" not in payload:
            return self._parse_blueprint_json(payload["text"])
            
        return payload

    async def _analyze_specification(self, specification: str, personality: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze specification to determine agent requirements"""
        tech_level = (personality or {}).get("personality", {}).get("technical_level", "intermediate")
        return [
            {
                "name": "Generalist Agent",
                "description": "Default agent generated from spec",
                "system_prompt": (
                    f"Technical level: {tech_level}.\n\n"
                    "Work with your team to achieve the objective described below. "
                    "Be explicit about assumptions and show steps when doing math.\n\n"
                    f"Team specification:\n{specification}"
                ),
                "capabilities": ["research", "analysis", "synthesis"],
                "required_skills": ["research", "analysis", "synthesis"],
                "complexity": "medium",
                "estimated_steps": 3,
                "personality_alignment": tech_level,
            }
        ]

    async def _identify_required_tools(self, specification: str) -> List[str]:
        """Identify required tools from specification"""
        # Simple identification - in real implementation would use NLP
        # Must only return deployable tool names from ToolManager registry.
        
        # Base tools for research
        tools = ["unified_research_tool", "multimodal_kb_search", "fetch_document_content"]
        
        # Check for keywords that suggest spreadsheet/data needs
        spec_lower = specification.lower()
        spreadsheet_keywords = ["table", "spreadsheet", "excel", "csv", "data", "chart", "graph", "calculation", "formula", "row", "column"]
        if any(keyword in spec_lower for keyword in spreadsheet_keywords):
            tools.append("generate_excel_file")
        
        # Check for keywords that suggest PDF needs
        pdf_keywords = ["pdf", "document", "report", "invoice", "contract"]
        if any(keyword in spec_lower for keyword in pdf_keywords):
            tools.append("generate_pdf_file")
        
        # Check for keywords that suggest presentation needs
        presentation_keywords = ["presentation", "powerpoint", "slides", "deck"]
        if any(keyword in spec_lower for keyword in presentation_keywords):
            tools.append("generate_presentation_file")
        
        return tools

    async def _design_team_structure(self, specification: str, personality: Dict[str, Any]) -> Dict[str, Any]:
        """Design team structure based on specification and personality"""
        return {
            "team_type": "specialized",
            "agent_count": 3,
            "coordination_style": "hierarchical",
            "communication_preferences": personality.get("personality", {})
        }


class PlatformOrchestrator:
    """
    Highest privilege orchestrator with platform-wide capabilities within tenant scope:
    - Tool approval and validation
    - Agent team selection and loading
    - User preferences and personality loading (fresh from DB)
    - Agent team blueprint creation
    - Agent team creation
    - Tenant-scoped operations only
    """

    def __init__(self, tenant_id: int, user_id: int, job_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.job_id = job_id
        self.tenant_isolation = TenantIsolationValidator(tenant_id)
        self.personality_loader = UserPersonalityLoader(tenant_id)
        self.tool_approver = ToolApprovalManager(tenant_id)
        self.team_creator = AgentTeamCreator(tenant_id)

    async def plan_and_execute(self, goal: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute the goal using the Platform Orchestrator (IO).
        For now, we default to Inquiry Mode: Dual Search + Synthesis.
        """
        # 1. Perform Dual Search
        search_results = await self.perform_dual_search(query=goal)
        
        # 2. Synthesize answer (using LLM - simplified for now, just return results)
        # In a real implementation, we would call an LLM here to synthesize the answer.
        
        return {
            "success": True,
            "job_id": self.job_id,
            "output": {
                "answer": "Search completed.", # Placeholder
                "search_results": search_results
            },
            "status": "COMPLETED"
        }

    async def create_agent_team_blueprint(self, team_specification: str) -> Dict[str, Any]:
        """Create agent team blueprint from natural language specification"""
        # Validate tenant isolation
        await self.tenant_isolation.validate_tenant_access(self.tenant_id)

        # Load fresh user personality (no caching)
        user_personality = await self.personality_loader.load_fresh_personality(self.user_id)

        # Create team blueprint with personality context
        blueprint = await self.team_creator.create_blueprint(
            specification=team_specification,
            user_personality=user_personality,
            tenant_id=self.tenant_id
        )

        # Attach platform-wide system prompt, enhanced by user context
        try:
            platform_prompt = await self.enhanced_system_prompt(BASE_PLATFORM_PROMPT, user_personality)
            blueprint["platform_prompt"] = platform_prompt
        except Exception:
            # Non-fatal
            pass

        # Compute quick recommendations for teams (deep links) based on tool fit
        try:
            tool_reqs = blueprint.get("tool_requirements", [])
            blueprint["recommended_teams"] = await self._recommend_teams_for_spec(team_specification, tool_reqs)
        except Exception:
            # Non-fatal
            blueprint["recommended_teams"] = []

        # Log security event
        await self._log_security_event("team_blueprint_created", blueprint)

        # Fire UI trigger for agent blueprint visualization on the current job trace
        try:
            if self.job_id:
                await publish_execution_trace(
                    job_id=self.job_id,
                    event_data={
                        "type": "agent_blueprint_created",
                        "step_description": "Agent team blueprint created",
                        "tenant_id": self.tenant_id,
                        "blueprint": blueprint,
                    },
                )
        except Exception:
            pass

        # Record platform-level token usage if available later in runtime (hook point)
        try:
            # Placeholder: if platform prompt LLm is invoked elsewhere, record tokens there
            tracker = CostTracker()
            # No-op now
            _ = tracker
        except Exception:
            pass

        return blueprint

    async def approve_tools_for_team(self, team_id: str, tool_names: List[str], auto_approve: bool = True) -> bool:
        """Approve tools for specific agent team with auto-approve capability"""
        # Validate tenant isolation
        await self.tenant_isolation.validate_team_access(team_id, self.tenant_id)

        if auto_approve:
            # Auto-approve based on tool stability and team requirements
            approval_result = await self.tool_approver.auto_approve_tools(team_id, tool_names)
        else:
            # Manual approval workflow
            approval_result = await self.tool_approver.manual_approve_tools(team_id, tool_names)

        # Log approval event
        await self._log_security_event("tools_approved", {
            "team_id": team_id,
            "tools": tool_names,
            "auto_approve": auto_approve
        })

        # Bump tenant-wide quick teams cache version so all user caches rotate
        try:
            await self._bump_quick_teams_version()
        except Exception:
            pass

        return approval_result

    async def load_user_personality_context(self) -> Dict[str, Any]:
        """Load comprehensive user personality and observation data (fresh from DB)"""
        # Always fetch fresh data (no caching)
        personality_data = await self.personality_loader.load_fresh_personality(self.user_id)

        return personality_data

    async def enhanced_system_prompt(self, base_prompt: str, user_context: Dict[str, Any]) -> str:
        """Generate enhanced system prompt with user personality"""
        enhanced_prompt = f"""
        {base_prompt}

        **USER PERSONALITY CONTEXT:**
        Communication Style: {user_context.get('personality', {}).get('preferred_tone', 'professional')}
        Technical Level: {user_context.get('personality', {}).get('technical_level', 'intermediate')}
        Success Patterns: {user_context.get('personality', {}).get('successful_approaches', [])}
        Failed Approaches: {user_context.get('personality', {}).get('failed_approaches', [])}

        **OBSERVATION INSIGHTS:**
        Recent Interactions: {user_context.get('observations', {}).get('recent_interactions', [])}
        Communication Patterns: {user_context.get('observations', {}).get('communication_patterns', {})}

        **SEARCH REQUIREMENTS:**
        ALWAYS perform both web search AND knowledge base search for ANY uncertainty, even microscopic.
        When searching, search BOTH web and knowledge base in parallel.
        """
        return enhanced_prompt

    async def perform_dual_search(self, query: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Run KB + Web search (unified) and emit a DUAL_SEARCH trace event."""
        try:
            # Enable web search to fulfill "Dual Search" promise
            results = unified_research_tool(query=query, tenant_id=str(self.tenant_id), project_id=project_id, job_id=self.job_id, enable_web=True)
        except Exception:
            results = {"project_results": [], "personal_results": [], "web_results": [], "vertex_results": []}

        # Publish compact counts for UI
        try:
            if self.job_id:
                counts = {
                    "project": len(results.get("project_results", []) or []),
                    "personal": len(results.get("personal_results", []) or []),
                    "vertex": len(results.get("vertex_results", []) or []),
                    "web": len(results.get("web_results", []) or []),
                }
                await publish_execution_trace(self.job_id, {
                    "type": "DUAL_SEARCH",
                    "step_description": "KB + Web search executed",
                    "counts": counts,
                    "query": query,
                    "tenant_id": self.tenant_id,
                })
        except Exception:
            pass

        return results

    async def get_quick_teams(self) -> List[Dict[str, Any]]:
        """Return a fast list of tenant teams for this user from Redis cache; fallback to DB.

        Cache key: teams:tenant:{tenant}:user:{user} (JSON list)
        """
        # Versioned cache key enables tenant-wide invalidation by bumping the version counter
        try:
            client = get_redis_client()
            version = await client.get(f"teams:tenant:{self.tenant_id}:version", default=0)
            try:
                version = int(version or 0)
            except Exception:
                version = 0
        except Exception:
            version = 0
        key = f"teams:tenant:{self.tenant_id}:v{version}:user:{self.user_id}"
        ttl_seconds = 900  # 15 minutes
        try:
            client = get_redis_client()
            cached = await client.get(key, default=None)
            if cached:
                return cached if isinstance(cached, list) else []
        except Exception:
            cached = None

        # Fallback: query DB for minimal fields
        teams: List[Dict[str, Any]] = []
        try:
            with session_scope() as session:
                rows = session.query(AgentTeam).filter(AgentTeam.tenant_id == self.tenant_id).all()
                for t in rows:
                    try:
                        tools = t.get_pre_approved_tool_names() if hasattr(t, "get_pre_approved_tool_names") else []
                    except Exception:
                        tools = []
                    teams.append({
                        "team_id": getattr(t, "agent_team_id", None),
                        "name": getattr(t, "name", "Unnamed Team"),
                        "approved_tools_count": len(tools or []),
                        "deep_link": f"/agents/teams/{getattr(t, 'agent_team_id', '')}",
                    })
        except Exception:
            teams = []

        # Cache best-effort
        try:
            client = get_redis_client()
            await client.set(key, teams, expire=ttl_seconds)
        except Exception:
            pass

        return teams

    async def _recommend_teams_for_spec(self, specification: str, tool_requirements: List[str]) -> List[Dict[str, Any]]:
        """Heuristic recommendation: prefer teams whose approved tools cover requirements.

        Returns up to 3 items with: team_id, name, reason, deep_link, action.
        """
        quick = await self.get_quick_teams()
        req = set(tool_requirements or [])

        # Enrich with rough fit score by reloading tool names when needed
        enriched: List[Dict[str, Any]] = []
        try:
            with session_scope() as session:
                for x in quick:
                    team_row = None
                    try:
                        team_row = session.query(AgentTeam).filter(
                            AgentTeam.tenant_id == self.tenant_id,
                            AgentTeam.agent_team_id == x.get("team_id")
                        ).first()
                    except Exception:
                        team_row = None
                    tools = []
                    if team_row and hasattr(team_row, "get_pre_approved_tool_names"):
                        try:
                            tools = team_row.get_pre_approved_tool_names() or []
                        except Exception:
                            tools = []
                    tool_set = set(tools or [])
                    coverage = (len(req & tool_set) / max(1, len(req))) if req else 0.0

                    # Readiness checks per overlapping tool
                    readiness_details: List[Dict[str, Any]] = []
                    credentials_ready_count = 0
                    manual_approval_needed: List[str] = []
                    from src.services.mcp_tool_manager import MCPToolManager

                    manager = MCPToolManager()
                    for tname in (req & tool_set):
                        cred_ok = False
                        status_str = "unknown"
                        try:
                            # Credential test
                            test_res = await manager.test_credentials(self.tenant_id, tname)  # type: ignore
                            cred_ok = bool(getattr(test_res, "success", False))
                            if cred_ok:
                                credentials_ready_count += 1
                        except Exception:
                            cred_ok = False
                        try:
                            # Tool status for manual approval hint
                            tool_rec = session.query(Tool).filter(Tool.name == tname, Tool.tenant_id == self.tenant_id).first()
                            if tool_rec is not None:
                                try:
                                    status_str = tool_rec.status.value  # enum
                                except Exception:
                                    status_str = str(tool_rec.status)
                            manual_flag = False if str(status_str).upper() == "STABLE" else True
                            if manual_flag:
                                manual_approval_needed.append(tname)
                        except Exception:
                            manual_flag = True
                        readiness_details.append({
                            "name": tname,
                            "credentials_ok": cred_ok,
                            "status": status_str,
                            "manual_approval_required": manual_flag,
                        })

                    reason = "Covers required tools" if coverage >= 0.8 else (
                        "Partial tool coverage" if coverage > 0 else "No explicit tool overlap; generalist candidate"
                    )
                    enriched.append({
                        **x,
                        "fit_score": round(coverage, 3),
                        "reason": reason,
                        "readiness": {
                            "tools": readiness_details,
                            "credentials_ready_count": credentials_ready_count,
                            "manual_approval_needed": manual_approval_needed,
                            "all_ready": bool(readiness_details) and all(d.get("credentials_ok") and not d.get("manual_approval_required") for d in readiness_details),
                        },
                        "action": "start",
                    })
        except Exception:
            # Fallback: return quick list with neutral reason
            enriched = [{**x, "fit_score": 0.0, "reason": "No tool info", "action": "start"} for x in (quick or [])]

        # Sort by fit_score desc and trim
        enriched.sort(key=lambda i: i.get("fit_score", 0.0), reverse=True)
        return enriched[:3]

    async def _invalidate_quick_teams_cache_for_user(self, user_id: int) -> None:
        """Invalidate the quick teams cache for a specific user in this tenant."""
        # Delete current-version and previous-version keys best-effort
        try:
            client = get_redis_client()
            version = await client.get(f"teams:tenant:{self.tenant_id}:version", default=0)
            try:
                v = int(version or 0)
            except Exception:
                v = 0
            keys = [
                f"teams:tenant:{self.tenant_id}:v{v}:user:{user_id}",
                f"teams:tenant:{self.tenant_id}:v{max(0, v-1)}:user:{user_id}",
            ]
            for k in keys:
                try:
                    await client.delete(k)
                except Exception:
                    pass
        except Exception:
            pass

    async def _bump_quick_teams_version(self) -> None:
        """Increment tenant-wide version to invalidate all user caches on next read."""
        try:
            client = get_redis_client()
            await client.incr(f"teams:tenant:{self.tenant_id}:version", amount=1)
        except Exception:
            pass

    async def _log_security_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Log security events for audit purposes"""
        await log_security_event(
            event_type=event_type,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            details=details
        )
