"""
Runtime configuration profiles for the Platform and Team orchestrators.

This module does **not** define any agents. Instead it centralizes the
immutable runtime parameters (system prompts, guardrails, isolation
policies, etc.) that the database-driven orchestrators must load before
executing. The goal is to eliminate ad-hoc constants, ensuring that every
orchestrator instance pulls production-grade values from a single
source of truth.

All limits, guardrails, and policy texts were derived from the project
vision defined in Z/Overview.md and the directives in
Plan/PHASE_1_DUAL_ORCHESTRATOR_ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CostGuardrails:
    max_total_cost_usd: float
    max_step_cost_usd: float
    warn_at_usd: float


@dataclass(frozen=True)
class ValidationThresholds:
    minimum_confidence: float
    minimum_output_chars: int
    max_consecutive_failures: int
    replan_trigger: str  # free-text policy identifier


@dataclass(frozen=True)
class AnalyticsPolicy:
    emit_execution_trace: bool
    emit_cost_events: bool
    emit_tool_approval_decisions: bool
    required_log_fields: List[str]


@dataclass(frozen=True)
class ToolApprovalPolicy:
    auto_approved_tools: List[str]
    manual_review_states: List[str]
    required_reviewers: List[str]
    confirmation_prompt_text: str
    fallback_behavior: str


@dataclass(frozen=True)
class TenantIsolationPolicy:
    required_session_fields: List[str]
    mandatory_sql_filter: str
    redis_channel_prefix: str
    cross_tenant_guard_description: str


@dataclass(frozen=True)
class ObservationPolicy:
    prompt_fields: List[str]
    freshness_requirement_seconds: int
    cache_ttl_seconds: int
    cache_scope: str
    fallback_behavior: str


@dataclass(frozen=True)
class LoopParameters:
    max_specialists_per_plan: int
    max_iterations: int
    per_step_timeout_seconds: int
    retry_limit: int
    replan_on_validation_failure: bool
    plan_weight: float
    execution_weight: float


@dataclass(frozen=True)
class OrchestratorProfile:
    name: str
    description: str
    system_prompt: str
    model_tier: str
    allow_models: List[str]
    loop: LoopParameters
    cost_guardrails: CostGuardrails
    validation: ValidationThresholds
    analytics: AnalyticsPolicy
    observation: ObservationPolicy
    tenant_isolation: TenantIsolationPolicy
    tool_policy: ToolApprovalPolicy
    max_concurrent_specialists: int
    max_execution_seconds: int


PLATFORM_ORCHESTRATOR_PROFILE = OrchestratorProfile(
    name="platform_orchestrator",
    description="Tenant-scoped master orchestrator responsible for goal decomposition, "
    "tool approval decisions, and strategic coordination across agent teams.",
    system_prompt=(
        "You are \"IO\", the Etherion Platform Orchestrator AI, operating strictly within a single tenant. "
        "Your role is to ground answers and plans in evidence, recommend or create the right agent teams, and "
        "delegate execution safely and efficiently.\n\n"
        "Mandates:\n"
        "- Dual search for every uncertainty: (a) tenant Knowledge Base (BigQuery + Vertex AI Search) and (b) grounded Web search. Provide citations; prefer KB over Web on conflicts.\n"
        "- Do not execute MCP tools directly. Tool actions run in team runtimes and must be registered, allowlisted, credentialed, and (for writes) explicitly confirmed by the user.\n"
        "- Enforce tenant isolation, cost guardrails, and publish transparent trace decisions.\n"
        "- Never hallucinate. If evidence is insufficient, say so and propose how to obtain it.\n\n"
        "Behavior:\n"
        "- Recommend existing specialist teams with rationale and quick-launch deep links, or initiate an interactive blueprint flow and wait for explicit approval before creation.\n"
        "- Delegate to the selected team with clear scope, success criteria, and validation steps.\n"
        "- Summarize risks, assumptions, and expected costs for each decision."
    ),
    model_tier="gemini-3-pro-preview",
    allow_models=["gemini-3-pro-preview", "gemini-3-flash-preview"],
    loop=LoopParameters(
        max_specialists_per_plan=6,
        max_iterations=12,
        per_step_timeout_seconds=240,
        retry_limit=2,
        replan_on_validation_failure=True,
        plan_weight=0.6,
        execution_weight=0.4,
    ),
    cost_guardrails=CostGuardrails(
        max_total_cost_usd=25.0,
        max_step_cost_usd=4.0,
        warn_at_usd=18.0,
    ),
    validation=ValidationThresholds(
        minimum_confidence=0.7,
        minimum_output_chars=80,
        max_consecutive_failures=2,
        replan_trigger="two-step-misalignment",
    ),
    analytics=AnalyticsPolicy(
        emit_execution_trace=True,
        emit_cost_events=True,
        emit_tool_approval_decisions=True,
        required_log_fields=[
            "tenant_id",
            "job_id",
            "plan_step",
            "tool_decision",
            "cost_estimate",
            "observation_summary",
        ],
    ),
    observation=ObservationPolicy(
        prompt_fields=[
            "preferred_tone",
            "response_length_preference",
            "risk_tolerance",
            "successful_tools",
            "failed_approaches",
        ],
        freshness_requirement_seconds=900,
        cache_ttl_seconds=300,
        cache_scope="tenant_user",
        fallback_behavior="use_platform_defaults_with_warning",
    ),
    tenant_isolation=TenantIsolationPolicy(
        required_session_fields=["tenant_id", "user_id", "job_id"],
        mandatory_sql_filter="tenant_id = :tenant_id",
        redis_channel_prefix="audit:tenant",
        cross_tenant_guard_description=(
            "Every orchestrator call must assert tenant_id on the session and reject any "
            "observations, tools, or agents whose tenant_id does not match."
        ),
    ),
    tool_policy=ToolApprovalPolicy(
        auto_approved_tools=[
            "search_personal_kb",
            "search_project_kb",
            "unified_research_tool",
            "confirm_action_tool",
        ],
        manual_review_states=["submitted", "security_review", "approved", "rejected"],
        required_reviewers=["platform_security", "tenant_admin"],
        confirmation_prompt_text=(
            "The system is about to execute an irreversible action:\n"
            "- Tenant: {tenant_id}\n"
            "- Tool: {tool_name}\n"
            "- Payload Summary: {payload_summary}\n"
            "Please confirm to proceed."
        ),
        fallback_behavior="queue_for_manual_review",
    ),
    max_concurrent_specialists=4,
    max_execution_seconds=1800,
)

TEAM_ORCHESTRATOR_PROFILE = OrchestratorProfile(
    name="team_orchestrator",
    description="Execution orchestrator that coordinates specialists within a single tenant team "
    "following the 2N+1 loop mandated by Etherion.",
    system_prompt=(
        "You are the Team Orchestrator. You receive a structured plan from the Platform "
        "Orchestrator and must execute it through the team's specialist agents. For every step:\n"
        "1. Restate your understanding of the step and confirm alignment with the overall goal.\n"
        "2. Select the appropriate specialist and craft an instruction that includes context, "
        "success criteria, and expected format.\n"
        "3. Validate the specialist output against the success criteria. If validation fails, "
        "diagnose the issue, decide whether to retry, request clarifications, or trigger a replan.\n"
        "4. Log confidence, cost, and any risks discovered. Never skip validation.\n"
        "If two validation failures occur consecutively, halt and return a replan request."
    ),
    model_tier="gemini-3-flash-preview",
    allow_models=["gemini-3-flash-preview", "gemini-3-pro-preview", "gemini-3-flash-preview"],
    loop=LoopParameters(
        max_specialists_per_plan=4,
        max_iterations=8,
        per_step_timeout_seconds=210,
        retry_limit=1,
        replan_on_validation_failure=True,
        plan_weight=0.4,
        execution_weight=0.6,
    ),
    cost_guardrails=CostGuardrails(
        max_total_cost_usd=12.0,
        max_step_cost_usd=2.5,
        warn_at_usd=9.0,
    ),
    validation=ValidationThresholds(
        minimum_confidence=0.6,
        minimum_output_chars=40,
        max_consecutive_failures=2,
        replan_trigger="validation-confidence-below-threshold",
    ),
    analytics=AnalyticsPolicy(
        emit_execution_trace=True,
        emit_cost_events=True,
        emit_tool_approval_decisions=False,
        required_log_fields=[
            "tenant_id",
            "job_id",
            "step_number",
            "agent_id",
            "confidence_score",
            "validation_status",
        ],
    ),
    observation=ObservationPolicy(
        prompt_fields=[
            "preferred_tone",
            "detail_orientation",
            "response_time_expectations",
        ],
        freshness_requirement_seconds=600,
        cache_ttl_seconds=300,
        cache_scope="tenant_user",
        fallback_behavior="escalate_to_platform_defaults",
    ),
    tenant_isolation=TenantIsolationPolicy(
        required_session_fields=["tenant_id", "job_id"],
        mandatory_sql_filter="tenant_id = :tenant_id",
        redis_channel_prefix="jobs:tenant",
        cross_tenant_guard_description=(
            "Team orchestrator must only load specialists and tools whose tenant scope "
            "matches the running job. Reject any mismatched configuration immediately."
        ),
    ),
    tool_policy=ToolApprovalPolicy(
        auto_approved_tools=[
            "search_personal_kb",
            "search_project_kb",
            "confirm_action_tool",
        ],
        manual_review_states=["submitted", "pending_platform_orchestrator"],
        required_reviewers=["platform_orchestrator"],
        confirmation_prompt_text=(
            "The team orchestrator requires approval to use {tool_name}. "
            "Provide justification: {justification}"
        ),
        fallback_behavior="escalate_to_platform",
    ),
    max_concurrent_specialists=3,
    max_execution_seconds=1200,
)


ORCHESTRATOR_PROFILES: Dict[str, OrchestratorProfile] = {
    PLATFORM_ORCHESTRATOR_PROFILE.name: PLATFORM_ORCHESTRATOR_PROFILE,
    TEAM_ORCHESTRATOR_PROFILE.name: TEAM_ORCHESTRATOR_PROFILE,
}


def get_orchestrator_profile(name: str) -> OrchestratorProfile:
    """Fetch a typed profile by orchestrator name."""
    try:
        return ORCHESTRATOR_PROFILES[name]
    except KeyError as exc:
        raise KeyError(f"No orchestrator profile registered for '{name}'") from exc
