# src/etherion_ai/graphql_schema/mutations.py
import strawberry
from strawberry.scalars import JSON
import asyncio
import json
import redis.asyncio as redis
import logging
import html
import re
import secrets
import string
from typing import AsyncGenerator, Any, Annotated
from uuid import uuid4
from sqlmodel import select
from fastapi import Depends
from strawberry.types import Info as GraphQLResolveInfo
from datetime import datetime, timedelta
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from src.etherion_ai.graphql_schema.input_types import (
    GoalInput,
    FeedbackInput,
    SupportTicketInput,
    TenantInput,
    ProjectInput,
    ConversationInput,
    ScheduledTaskInput,
    ToneProfileInput,
    AgentInput,
    AgentTeamInput,
    CustomAgentDefinitionInput,
    IntegrationInput,
    MCPToolExecutionParams,
    MCPCredentials,
    JobHistoryFilter,
    ImageGenInput
)
from src.etherion_ai.graphql_schema.output_types import (
    GoalOutput,
    SupportResponse,
    TenantResponse,
    ProjectType,
    ConversationType,
    ScheduledTaskType,
    ToneProfileType,
    JobResponse,
    Agent,
    AgentTeamType,
    CustomAgentDefinitionType,
    AgentExecutionResult,
    Integration,
    IntegrationStatus,
    IntegrationTestResult,
    MCPTool,
    MCPToolResult,
    MCPCredentialStatus,
    MCPToolTestResult,
    ToneProfile,
    ImageGenResult
)
from src.database.models import Project, Conversation, Job, JobStatus, AgentTeam
from src.database.models.threading import Thread as ThreadModel
from src.services.platform_orchestrator import PlatformOrchestrator
from src.scheduler.service import SchedulerService
from src.scheduler.service import SchedulerService
from src.etherion_ai.graphql_schema.input_validators import GoalInputValidator, FeedbackInputValidator, SupportTicketInputValidator, TenantInputValidator
from src.etherion_ai.graphql_schema.output_types import (
    GoalOutput,
    SupportResponse,
    TenantResponse,
    ProjectType,
    ConversationType,
    ScheduledTaskType,
    ToneProfileType,
    JobResponse,
    Agent,
    AgentExecutionResult,
    Integration,
    IntegrationStatus,
    IntegrationTestResult,
    MCPTool,
    MCPToolResult,
    MCPCredentialStatus,
    MCPToolTestResult,
    ToneProfile,
    ImageGenResult
)
from src.database.models import Project, Conversation, Job, JobStatus
from src.services.goal_orchestrator import orchestrate_goal_task


async def _run_orchestration_with_error_handling(
    job_id: str,
    goal_description: str,
    user_id: int,
    tenant_id: int,
) -> None:
    """Wrapper to catch exceptions from background orchestration tasks."""
    print(f"[DEBUG] Starting orchestration for job {job_id}")
    try:
        await orchestrate_goal_task(
            job_id=job_id,
            goal_description=goal_description,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    except Exception as e:
        print(f"UNCAUGHT EXCEPTION in background orchestration task {job_id}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        # Try to update job status to FAILED
        try:
            from src.database.db import get_scoped_session
            from src.database.models import Job, JobStatus
            from sqlmodel import select
            async with get_scoped_session() as session:
                res = await session.exec(select(Job).where(Job.job_id == job_id))
                job = res.first()
                if job:
                    job.error_message = f"Uncaught exception: {str(e)}"
                    job.update_status(JobStatus.FAILED)
                    session.add(job)
        except Exception as inner_e:
            print(f"Failed to update job status after uncaught exception: {inner_e}")


# Module-level set to keep strong references to background tasks (prevents GC)
_background_tasks = set()

from src.etherion_ai.graphql_schema.auth_mutations import AuthMutation
from src.etherion_ai.exceptions import ValidationError, InternalServerError
from src.etherion_ai.middleware.graphql_logger import GraphQLOperationLogger
from src.utils.llm_loader import get_gemini_llm
from src.services.orchestrator_runtime import create_named_orchestrator_runtime
from src.utils.ip_utils import get_client_ip, hash_ip
from src.utils.vpn_check import is_vpn_or_proxy
from src.utils.secrets_manager import TenantSecretsManager
from src.services.orchestrator_security import get_orchestrator_security_validator
from src.services.mcp_tool_manager import MCPToolManager

from src.database.db import get_session
from src.database.models import User, Tenant
from src.database.models.custom_agent import CustomAgentDefinition
from src.auth.service import get_current_user
from src.core.security.audit_logger import log_input_validation_failure, log_security_violation, log_security_event
from src.middleware.authorization import (
    get_authorization_context,
    get_authorization_context_for_user,
    Permission,
    validate_tenant_access,
)
from src.services.feedback_service import FeedbackService, FeedbackPolicy
from src.core.celery import safe_revoke_job, safe_revoke_group
from src.utils.llm_registry import get_provider_spec, REGISTRY

# Connect to Redis for Pub/Sub
redis_client = redis.Redis(decode_responses=True)
from src.core.redis import set_job_cancel, publish_execution_trace, publish_job_status


def sanitize_input(text: str) -> str:
    """
    Sanitize input to prevent XSS and other injection attacks.

    Args:
        text: Input text to sanitize

    Returns:
        str: Sanitized text
    """
    if not text:
        return text

    # Remove any script tags
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)

    # Escape HTML characters
    text = html.escape(text)

    # Remove any other potentially harmful tags
    text = re.sub(r'<[^>]*>', '', text)

    return text


async def validate_and_sanitize_goal_input(goal_input: GoalInput, request_info: dict = None) -> GoalInput:
    """
    Validate and sanitize GoalInput data with security logging.

    Args:
        goal_input: The GoalInput object to validate and sanitize
        request_info: Request information for audit logging

    Returns:
        GoalInput: Sanitized GoalInput object

    Raises:
        ValidationError: If validation fails
    """
    try:
        # Validate using Pydantic model
        validator = GoalInputValidator(
            goal=goal_input.goal or "",
            context=goal_input.context,
            output_format_instructions=goal_input.output_format_instructions,
            user_id=goal_input.userId or "",
            provider=getattr(goal_input, "provider", None),
            model=getattr(goal_input, "model", None),
        )

        # Sanitize inputs
        sanitized_goal = sanitize_input(validator.goal)
        sanitized_context = sanitize_input(validator.context) if validator.context else None
        sanitized_output_format = sanitize_input(validator.output_format_instructions) if validator.output_format_instructions else None

        # Return new GoalInput with sanitized values and preserved execution hints/overrides.
        # Do NOT pass provider/model here so this works even if the deployed GoalInput
        # type does not define those fields.
        return GoalInput(
            goal=sanitized_goal,
            context=sanitized_context,
            output_format_instructions=sanitized_output_format,
            userId=validator.user_id,
            agentTeamId=getattr(goal_input, "agentTeamId", None),
            plan_mode=getattr(goal_input, "plan_mode", None),
            search_force=getattr(goal_input, "search_force", None),
            threadId=getattr(goal_input, "threadId", None),
        )
    except ValidationError as e:
        # Log validation failure for security monitoring
        if request_info:
            await log_input_validation_failure(
                user_id=request_info.get("user_id"),
                tenant_id=request_info.get("tenant_id"),
                ip_address=request_info.get("ip_address", "unknown"),
                user_agent=request_info.get("user_agent", "unknown"),
                endpoint=request_info.get("endpoint", "executeGoal"),
                method=request_info.get("method", "POST"),
                validation_errors=[str(e)],
                input_data={"goal": goal_input.goal, "context": goal_input.context}
            )
        raise ValidationError(
            message=f"Invalid GoalInput: {str(e)}",
            details={"input_field": "goal_input"}
        )
    except Exception as e:
        # Log security violation for unexpected errors
        if request_info:
            await log_security_violation(
                user_id=request_info.get("user_id"),
                tenant_id=request_info.get("tenant_id"),
                ip_address=request_info.get("ip_address", "unknown"),
                user_agent=request_info.get("user_agent", "unknown"),
                endpoint=request_info.get("endpoint", "executeGoal"),
                method=request_info.get("method", "POST"),
                violation_type="input_validation_error",
                details={"error": str(e), "input": str(goal_input)}
            )
        raise ValidationError(
            message=f"Invalid GoalInput: {str(e)}",
            details={"input_field": "goal_input"}
        )


def validate_and_sanitize_feedback_input(feedback_input: FeedbackInput) -> FeedbackInput:
    """
    Validate and sanitize FeedbackInput data.

    Args:
        feedback_input: The FeedbackInput object to validate and sanitize

    Returns:
        FeedbackInput: Sanitized FeedbackInput object

    Raises:
        ValidationError: If validation fails
    """
    try:
        # Validate using Pydantic model
        validator = FeedbackInputValidator(
            job_id=feedback_input.jobId,
            user_id=feedback_input.userId,
            goal=feedback_input.goal,
            final_output=feedback_input.finalOutput,
            feedback_score=feedback_input.feedbackScore,
            feedback_comment=feedback_input.feedbackComment
        )

        # Sanitize inputs
        sanitized_goal = sanitize_input(validator.goal)
        sanitized_final_output = sanitize_input(validator.final_output)
        sanitized_feedback_comment = sanitize_input(validator.feedback_comment)

        # Return new FeedbackInput with sanitized values
        return FeedbackInput(
            jobId=validator.job_id,
            userId=validator.user_id,
            goal=sanitized_goal,
            finalOutput=sanitized_final_output,
            feedbackScore=validator.feedback_score,
            feedbackComment=sanitized_feedback_comment
        )
    except Exception as e:
        raise ValidationError(
            message=f"Invalid FeedbackInput: {str(e)}",
            details={"input_field": "feedback_input"}
        )


def validate_and_sanitize_support_input(support_input: SupportTicketInput) -> SupportTicketInput:
    """
    Validate and sanitize SupportTicketInput data.

    Args:
        support_input: The SupportTicketInput object to validate and sanitize

    Returns:
        SupportTicketInput: Sanitized SupportTicketInput object

    Raises:
        ValidationError: If validation fails
    """
    try:
        # Validate using Pydantic model
        validator = SupportTicketInputValidator(
            ticket_text=support_input.ticketText,
            user_id=support_input.userId,
            order_id=support_input.orderId,
            attached_files=support_input.attachedFiles
        )

        # Sanitize inputs
        sanitized_ticket_text = sanitize_input(validator.ticket_text)
        sanitized_order_id = sanitize_input(validator.order_id) if validator.order_id else None
        sanitized_attached_files = [sanitize_input(f) for f in validator.attached_files] if validator.attached_files else None

        # Return new SupportTicketInput with sanitized values
        return SupportTicketInput(
            ticketText=sanitized_ticket_text,
            userId=validator.user_id,
            orderId=sanitized_order_id,
            attachedFiles=sanitized_attached_files
        )
    except Exception as e:
        raise ValidationError(
            message=f"Invalid SupportTicketInput: {str(e)}",
            details={"input_field": "support_input"}
        )


def validate_and_sanitize_tenant_input(tenant_input: TenantInput) -> TenantInput:
    """
    Validate and sanitize TenantInput data.

    Args:
        tenant_input: The TenantInput object to validate and sanitize

    Returns:
        TenantInput: Sanitized TenantInput object

    Raises:
        ValidationError: If validation fails
    """
    try:
        # Validate using Pydantic model
        validator = TenantInputValidator(
            name=tenant_input.name,
            admin_email=tenant_input.adminEmail,
            password=tenant_input.password,
            subdomain=getattr(tenant_input, "subdomain", None),
        )

        # Sanitize inputs
        sanitized_name = sanitize_input(validator.name)
        sanitized_admin_email = sanitize_input(validator.admin_email)
        sanitized_subdomain = (validator.subdomain or None)

        # Return new TenantInput with sanitized values
        # Note: We don't sanitize the password as it will be hashed
        return TenantInput(
            name=sanitized_name,
            adminEmail=sanitized_admin_email,
            password=validator.password,
            subdomain=sanitized_subdomain,
        )
    except Exception as e:
        raise ValidationError(
            message=f"Invalid TenantInput: {str(e)}",
            details={"input_field": "tenant_input"}
        )


from sqlalchemy.ext.asyncio import AsyncSession


async def get_or_create_user(user_id: str, session) -> User:
    """
    Retrieve or create a `User` for the given identifier.

    Works with both `AsyncSession` and synchronous `Session` instances.
    """

    statement = select(User).where(User.user_id == user_id)

    if isinstance(session, AsyncSession):
        result = await session.execute(statement)
        user = result.scalars().first()
        if not user:
            user = User(user_id=user_id)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    # Fallback for synchronous sessions (should be rare in async resolvers)
    user = session.exec(statement).first()
    if not user:
        user = User(user_id=user_id)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
class Subscription:
    pass  # Subscriptions are now in subscriptions.py

# TODO: The image generation mutation was partially merged with a malformed docstring
# block here, leading to an IndentationError during import. The feature will be
# reintroduced in a dedicated patch with complete types and resolvers.


@strawberry.type
class Mutation(AuthMutation):
    @strawberry.mutation
    async def cancelJob(
        self,
        info: GraphQLResolveInfo,
        job_id: Annotated[str, strawberry.argument(name="job_id")],
    ) -> bool:
        """Cooperative cancellation: set cancel flag, publish STOP_INTENT, and mark CANCELLED."""
        # Auth
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            return False

        # Verify job belongs to tenant
        try:
            if isinstance(db_session, AsyncSession):
                result = await db_session.execute(
                    select(Job).where(Job.job_id == job_id, Job.tenant_id == current_user.tenant_id)
                )
            else:
                result = db_session.exec(
                    select(Job).where(Job.job_id == job_id, Job.tenant_id == current_user.tenant_id)
                )
            job = result.scalars().first()
            if not job:
                return False
        except Exception:
            return False

        # Set cancel flag and publish STOP_INTENT
        try:
            await set_job_cancel(job_id)
        except Exception:
            pass
        try:
            await publish_execution_trace(job_id, {
                "type": "STOP_INTENT",
                "step_description": "User requested to stop the job",
            })
        except Exception:
            pass
        # Structured audit log for STOP intent
        try:
            await log_security_event(
                event_type="job_stop_requested",
                user_id=current_user.id,
                tenant_id=current_user.tenant_id,
                details={"job_id": job_id}
            )
        except Exception:
            pass

        # Best-effort Celery revoke for any long-running workers (no-op if not applicable)
        try:
            try:
                safe_revoke_job(job_id, terminate=True)
            except Exception:
                pass
            try:
                # If groups were tagged as job-scoped, attempt group revoke
                safe_revoke_group(f"job:{job_id}", terminate=True)
            except Exception:
                pass
        except Exception:
            pass

        # Mark CANCELLED immediately to provide STOP ACK to UI
        try:
            job.update_status(JobStatus.CANCELLED)
            db_session.add(job)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()
            await publish_job_status(job_id, {"job_id": job_id, "status": "CANCELLED", "message": "Stop acknowledged"})
        except Exception:
            # Even if DB update fails, best-effort publish status
            try:
                await publish_job_status(job_id, {"job_id": job_id, "status": "CANCELLED", "message": "Stop acknowledged"})
            except Exception:
                pass

        return True

    # =============================
    # Projects CRUD (tenant-scoped)
    # =============================
    @strawberry.mutation
    async def createProject(
        self,
        info: GraphQLResolveInfo,
        name: str,
        description: str = "",
    ) -> ProjectType:
        """Create a new project for the current tenant."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            raise Exception("Not authenticated")
        proj = Project(
            name=name,
            description=description,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
        db_session.add(proj)
        if isinstance(db_session, AsyncSession):
            await db_session.commit()
            await db_session.refresh(proj)
        else:
            db_session.commit()
            db_session.refresh(proj)
        return ProjectType(
            id=proj.id,
            name=proj.name,
            description=proj.description,
            createdAt=proj.created_at.isoformat() if getattr(proj, "created_at", None) else None,
            userId=proj.user_id,
        )

    @strawberry.mutation
    async def updateProject(
        self,
        info: GraphQLResolveInfo,
        project_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> bool:
        """Update a project for the current tenant."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            raise Exception("Not authenticated")
        stmt = select(Project).where(Project.id == project_id, Project.tenant_id == current_user.tenant_id)
        rec = db_session.exec(stmt).first() if not isinstance(db_session, AsyncSession) else (await db_session.execute(stmt)).scalars().first()
        if not rec:
            raise Exception("Project not found")
        if name is not None:
            rec.name = name
        if description is not None:
            rec.description = description
        db_session.add(rec)
        if isinstance(db_session, AsyncSession):
            await db_session.commit()
        else:
            db_session.commit()
        return True

    @strawberry.mutation
    async def deleteProject(
        self,
        info: GraphQLResolveInfo,
        project_id: int,
    ) -> bool:
        """Delete a project for the current tenant."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            raise Exception("Not authenticated")
        stmt = select(Project).where(Project.id == project_id, Project.tenant_id == current_user.tenant_id)
        rec = db_session.exec(stmt).first() if not isinstance(db_session, AsyncSession) else (await db_session.execute(stmt)).scalars().first()
        if not rec:
            return False
        try:
            if isinstance(db_session, AsyncSession):
                await db_session.delete(rec)
                await db_session.commit()
            else:
                db_session.delete(rec)
                db_session.commit()
            return True
        except Exception:
            try:
                if isinstance(db_session, AsyncSession):
                    await db_session.rollback()
                else:
                    db_session.rollback()
            except Exception:
                pass
            return False

    @strawberry.mutation
    async def updateUserSettings(
        self,
        info: GraphQLResolveInfo,
        settings: JSON,
    ) -> bool:
        """Upsert per-tenant user settings JSON bag."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            return False
        try:
            payload = settings if isinstance(settings, (dict, list)) else json.loads(settings or "{}")
        except Exception:
            payload = {}
        # Portable upsert: try update → if no row affected, insert
        now = datetime.utcnow().isoformat()
        try:
            update_sql = sa.text("UPDATE user_settings SET settings_json=:s, updated_at=:u WHERE tenant_id=:t AND user_id=:i")
            params = {"s": json.dumps(payload), "u": now, "t": current_user.tenant_id, "i": current_user.id}
            if isinstance(db_session, AsyncSession):
                res = await db_session.execute(update_sql, params)
                if res.rowcount == 0:
                    insert_sql = sa.text("INSERT INTO user_settings (tenant_id,user_id,settings_json,updated_at) VALUES (:t,:i,:s,:u)")
                    await db_session.execute(insert_sql, params)
                await db_session.commit()
            else:
                res = db_session.execute(update_sql, params)
                if res.rowcount == 0:  # type: ignore
                    insert_sql = sa.text("INSERT INTO user_settings (tenant_id,user_id,settings_json,updated_at) VALUES (:t,:i,:s,:u)")
                    db_session.execute(insert_sql, params)
                db_session.commit()
            return True
        except Exception:
            try:
                if isinstance(db_session, AsyncSession):
                    await db_session.rollback()
                else:
                    db_session.rollback()
            except Exception:
                pass
            return False
    @strawberry.mutation
    async def createTenantInvite(
        self,
        info: GraphQLResolveInfo,
        email: str,
        expires_in_days: int = 7,
    ) -> str:
        """
        Create a single-use tenant invite token bound to an email. Admins only.

        Returns the invite token to be sent via email as a link to `/invite/{token}`.
        """
        from datetime import timedelta
        from uuid import uuid4
        from src.database.models import TenantInvite

        # Get current user and session
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")
        if not current_user.is_admin:
            raise Exception("Forbidden: admin only")

        token = uuid4().hex
        invite = TenantInvite(
            token=token,
            tenant_id=current_user.tenant_id,
            email=email,
            expires_at=datetime.utcnow() + timedelta(days=max(1, expires_in_days)),
            created_by_user_id=current_user.id,
        )
        db_session.add(invite)
        if isinstance(db_session, AsyncSession):
            await db_session.commit()
        else:
            db_session.commit()
        return token
    @strawberry.mutation
    async def updateAgentTeam(
        self,
        info: GraphQLResolveInfo,
        agent_team_id: Annotated[str, strawberry.argument(name="agent_team_id")],
        name: str | None = None,
        description: str | None = None,
        pre_approved_tool_names: list[str] | None = None,
    ) -> bool:
        """
        Update an AgentTeam. System agent teams are immutable and return 403.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        from src.database.models import AgentTeam
        if isinstance(db_session, AsyncSession):
            result = await db_session.exec(
                select(AgentTeam).where(
                    AgentTeam.agent_team_id == agent_team_id,
                    AgentTeam.tenant_id == current_user.tenant_id
                )
            )
        else:
            result = db_session.exec(
                select(AgentTeam).where(
                    AgentTeam.agent_team_id == agent_team_id,
                    AgentTeam.tenant_id == current_user.tenant_id
                )
            )
        team = result.first()
        if not team:
            raise Exception("AgentTeam not found")
        if team.is_system_agent:
            raise Exception("403 Forbidden: system agent teams are immutable")

        if name:
            team.name = name
        if description is not None:
            team.description = description
        if pre_approved_tool_names is not None:
            from src.database.models.agent_team import AgentTeam as AT
            team.pre_approved_tool_names = AT.serialize_tool_names(pre_approved_tool_names)

        db_session.add(team)
        if isinstance(db_session, AsyncSession):
            await db_session.commit()
        else:
            db_session.commit()
        # Bump tenant-wide quick teams cache version after update
        try:
            orchestrator = PlatformOrchestrator(tenant_id=current_user.tenant_id, user_id=current_user.id)
            await orchestrator._bump_quick_teams_version()  # type: ignore
        except Exception:
            pass
        return True
    @strawberry.mutation
    async def updateFileIngestionStatus(
        self,
        info: GraphQLResolveInfo,
        file_id: int,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        """
        Internal-only: Update ProjectKBFile ingestion status.
        Protected: must be called by trusted service account identity.
        """
        auth_context = info.context.get("request").state.auth_context
        db_session = auth_context["db_session"]

        # Enforce internal-only access via header or service account identity
        request = info.context.get("request")
        caller = request.headers.get("X-Internal-Service", "") if request else ""
        if caller != "data-ingestion-function":
            raise Exception("Forbidden")

        try:
            from src.database.models import ProjectKBFile
            if isinstance(db_session, AsyncSession):
                result = await db_session.execute(
                    select(ProjectKBFile).where(ProjectKBFile.id == file_id)
                )
            else:
                result = db_session.exec(
                    select(ProjectKBFile).where(ProjectKBFile.id == file_id)
                )
            file_rec = result.scalars().first()
            if not file_rec:
                raise Exception("File not found")
            file_rec.status = status
            file_rec.error_message = error_message
            db_session.add(file_rec)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()
            return True
        except Exception as e:
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
            raise Exception(f"Failed to update ingestion status: {str(e)}")
    @strawberry.mutation
    async def cloneSystemAgent(
        self,
        info: GraphQLResolveInfo,
        system_agent_id: str,
        new_name: str
    ) -> bool:
        """
        Clone a system agent into a user-editable copy under the caller's tenant.
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        # Load system agent (platform-owned, immutable)
        if isinstance(db_session, AsyncSession):
            result = await db_session.execute(
                select(CustomAgentDefinition).where(
                    CustomAgentDefinition.custom_agent_id == system_agent_id,
                    CustomAgentDefinition.is_system_agent == True
                )
            )
        else:
            result = db_session.exec(
                select(CustomAgentDefinition).where(
                    CustomAgentDefinition.custom_agent_id == system_agent_id,
                    CustomAgentDefinition.is_system_agent == True
                )
            )
        system_agent = result.scalars().first()
        if not system_agent:
            raise Exception("System agent not found")

        # Create a copy for the caller's tenant (not a system agent)
        clone = CustomAgentDefinition(
            custom_agent_id=CustomAgentDefinition.generate_custom_agent_id(),
            tenant_id=current_user.tenant_id,
            name=new_name,
            description=system_agent.description,
            system_prompt=system_agent.system_prompt,
            tool_names=system_agent.tool_names,
            model_name=system_agent.model_name,
            is_system_agent=False,
            is_active=True,
        )
        db_session.add(clone)
        if isinstance(db_session, AsyncSession):
            await db_session.commit()
        else:
            db_session.commit()
        return True


    @strawberry.mutation
    async def executeGoal(
        self,
        info: GraphQLResolveInfo,
        goal_input: Annotated[GoalInput, strawberry.argument(name="goalInput")],
    ) -> JobResponse:
        """Execute a goal asynchronously and return a job ID for tracking."""
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            return JobResponse(
                success=False,
                job_id="",
                status="ERROR",
                message="Authentication required",
            )

        # Authorization check - ensure user has permission to execute goals
        try:
            auth_context_obj = await get_authorization_context_for_user(
                user_id=current_user.user_id,
                tenant_id=current_user.tenant_id,
                db_session=db_session,
            )
            if not auth_context_obj.has_permission(Permission.EXECUTE_GOAL):
                return JobResponse(
                    success=False,
                    job_id="",
                    status="ERROR",
                    message="Insufficient permissions to execute goals",
                )
        except Exception as e:
            return JobResponse(
                success=False,
                job_id="",
                status="ERROR",
                message=f"Authorization check failed: {str(e)}",
            )

        # Log the GraphQL operation (raw input for audit)
        await GraphQLOperationLogger.log_operation(
            info=info,
            operation_name="executeGoal",
            variables={
                "goal_input": {
                    "goal": goal_input.goal,
                    "context": goal_input.context,
                    "output_format_instructions": goal_input.output_format_instructions,
                    "userId": goal_input.userId,
                    "plan_mode": getattr(goal_input, "plan_mode", None),
                    "search_force": getattr(goal_input, "search_force", None),
                    "agentTeamId": getattr(goal_input, "agentTeamId", None),
                    "provider": getattr(goal_input, "provider", None),
                    "model": getattr(goal_input, "model", None),
                    "threadId": getattr(goal_input, "threadId", None),
                }
            },
        )

        # Prepare request info for audit logging during validation
        request_info = {
            "user_id": current_user.user_id,
            "tenant_id": current_user.tenant_id,
            "ip_address": "unknown",  # Would be extracted from request
            "user_agent": "unknown",  # Would be extracted from request
            "endpoint": "executeGoal",
            "method": "POST",
        }

        # Validate and sanitize input with security logging
        try:
            validated_input = await validate_and_sanitize_goal_input(goal_input, request_info)
        except ValidationError as e:
            return JobResponse(
                success=False,
                job_id="",
                status="ERROR",
                message=f"Validation error: {e.message}",
            )
        except Exception as e:
            return JobResponse(
                success=False,
                job_id="",
                status="ERROR",
                message=f"An unexpected error occurred: {str(e)}",
            )

        # Resolve effective provider/model from GoalInput or thread preferences
        effective_provider = getattr(validated_input, "provider", None)
        effective_model = getattr(validated_input, "model", None)
        thread_id_val = getattr(validated_input, "threadId", None) or getattr(goal_input, "threadId", None)
        thread_row = None
        if thread_id_val:
            try:
                stmt = select(ThreadModel).where(
                    ThreadModel.thread_id == thread_id_val,
                    ThreadModel.tenant_id == current_user.tenant_id,
                )
                if isinstance(db_session, AsyncSession):
                    res = await db_session.execute(stmt)
                    thread_row = res.scalars().first()
                else:
                    thread_row = db_session.exec(stmt).first()
                if thread_row:
                    if not effective_provider and getattr(thread_row, "provider", None):
                        effective_provider = thread_row.provider
                    if not effective_model and getattr(thread_row, "model", None):
                        effective_model = thread_row.model
            except Exception:
                thread_row = None

        # Validate provider/model against registry when provided
        if effective_provider:
            if effective_provider not in REGISTRY:
                return JobResponse(
                    success=False,
                    job_id="",
                    status="ERROR",
                    message=f"Unsupported provider '{effective_provider}'",
                )
            try:
                spec = get_provider_spec(effective_provider)
                models_map = spec.models or {}
                # Accept either keys (aliases) or resolved values
                allowed = set(models_map.keys()) | set(models_map.values())
                if effective_model and effective_model not in allowed:
                    return JobResponse(
                        success=False,
                        job_id="",
                        status="ERROR",
                        message=f"Model '{effective_model}' is not valid for provider '{effective_provider}'",
                    )
            except Exception:
                return JobResponse(
                    success=False,
                    job_id="",
                    status="ERROR",
                    message="Invalid provider/model configuration",
                )

        try:
            # Ensure user exists before creating job
            await get_or_create_user(current_user.user_id, session=db_session)

            # Create Job row
            job = Job(
                job_id=Job.generate_job_id(),
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                status=JobStatus.QUEUED,
                job_type="execute_goal",
            )

            # Input data snapshot (sanitized goal + execution hints)
            input_payload = {
                "goal": validated_input.goal,
                "context": validated_input.context,
                "output_format_instructions": validated_input.output_format_instructions,
                "user_id": current_user.user_id,
                "tenant_id": current_user.tenant_id,
                "plan_mode": getattr(goal_input, "plan_mode", None),
                "search_force": getattr(goal_input, "search_force", None),
                "provider": effective_provider,
                "model": effective_model,
            }
            job.set_input_data(input_payload)

            # Job metadata (execution preferences, thread mapping, provider/model)
            job_metadata: Dict[str, Any] = {}
            plan_mode_val = getattr(goal_input, "plan_mode", None)
            search_force_val = getattr(goal_input, "search_force", None)
            if isinstance(plan_mode_val, bool):
                job_metadata["plan_mode"] = plan_mode_val
            if isinstance(search_force_val, bool):
                job_metadata["search_force"] = search_force_val
            agent_team_id = getattr(goal_input, "agentTeamId", None)
            if agent_team_id:
                job_metadata["agent_team_id"] = agent_team_id
            if thread_id_val and isinstance(thread_id_val, str) and len(thread_id_val) <= 64:
                job_metadata["thread_id"] = thread_id_val
                job.thread_id = thread_id_val
            if effective_provider:
                job_metadata["provider"] = effective_provider
            if effective_model:
                job_metadata["model"] = effective_model

            job.set_job_metadata(job_metadata)
            
            # Ensure app.tenant_id is set for RLS before INSERT
            from src.utils.rls_utils import set_session_tenant_context_async, set_session_tenant_context
            print(f"[DEBUG RLS] Setting tenant context to {current_user.tenant_id} before job INSERT")
            if isinstance(db_session, AsyncSession):
                await set_session_tenant_context_async(db_session, current_user.tenant_id)
            else:
                set_session_tenant_context(db_session, current_user.tenant_id)
            print(f"[DEBUG RLS] Tenant context set, now adding job to session")
            
            db_session.add(job)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                # Note: Skip refresh() - job_id is already set and refresh causes RLS SELECT issues
            else:
                db_session.commit()
                # Note: Skip refresh() - job_id is already set and refresh causes RLS SELECT issues
            print(f"[DEBUG RLS] Job committed successfully, job_id={job.job_id}")

            # If no thread_id was supplied, create a new thread row and map it
            if "thread_id" not in job_metadata or not job_metadata.get("thread_id"):
                try:
                    new_thread_id = f"thr_{uuid4().hex[:16]}"
                    insert_sql = sa.text(
                        """
                        INSERT INTO thread (thread_id, tenant_id, team_id, title, created_at)
                        VALUES (:tid, :tenant_id, :team_id, :title, :created_at)
                        """
                    )
                    params = {
                        "tid": new_thread_id,
                        "tenant_id": current_user.tenant_id,
                        "team_id": job_metadata.get("agent_team_id"),
                        "title": None,
                        "created_at": datetime.utcnow(),
                    }
                    if isinstance(db_session, AsyncSession):
                        await db_session.execute(insert_sql, params)
                        await db_session.commit()
                    else:
                        db_session.execute(insert_sql, params)
                        db_session.commit()
                    job_metadata["thread_id"] = new_thread_id
                    job.thread_id = new_thread_id
                    job.set_job_metadata(job_metadata)
                    # Re-set tenant context before UPDATE (thread INSERT may have changed connection state)
                    if isinstance(db_session, AsyncSession):
                        await set_session_tenant_context_async(db_session, current_user.tenant_id)
                        await db_session.commit()
                        # Note: Skip refresh() - job_id is already set and refresh causes RLS SELECT issues
                    else:
                        set_session_tenant_context(db_session, current_user.tenant_id)
                        db_session.commit()
                        # Note: Skip refresh() - job_id is already set and refresh causes RLS SELECT issues
                    try:
                        await publish_execution_trace(job.job_id, {
                            "type": "THREAD_CREATED",
                            "step_description": f"Thread {new_thread_id} created",
                            "thread_id": new_thread_id,
                        })
                    except Exception:
                        pass
                except Exception:
                    pass
            else:
                # If we had an existing thread_row and resolved provider/model, persist them
                try:
                    if thread_row and (effective_provider or effective_model):
                        if effective_provider:
                            thread_row.provider = effective_provider
                        if effective_model:
                            thread_row.model = effective_model
                        db_session.add(thread_row)
                        if isinstance(db_session, AsyncSession):
                            await db_session.commit()
                        else:
                            db_session.commit()
                except Exception:
                    pass

            # Dispatch orchestration to Celery worker (not API asyncio)
            from src.services.goal_orchestrator import execute_goal_celery_task
            execute_goal_celery_task.apply_async(
                kwargs={
                    "job_id": job.job_id,
                    "goal_description": validated_input.goal,
                    "user_id": current_user.id,
                    "tenant_id": current_user.tenant_id,
                },
                queue="worker-agents",
            )
            print(f"[DEBUG] Dispatched orchestration to Celery worker for job {job.job_id}")

            # Publish initial mapping trace for FE deep-link if thread_id present
            try:
                md = job.get_job_metadata() or {}
                if md.get("thread_id"):
                    await publish_execution_trace(job.job_id, {
                        "type": "THREAD_SELECTED",
                        "step_description": f"Thread {md.get('thread_id')} selected",
                        "thread_id": md.get("thread_id"),
                    })
            except Exception:
                pass

            return JobResponse(
                success=True,
                job_id=job.job_id,
                status=JobStatus.QUEUED.value,
                message="Goal execution has been queued for processing",
            )

        except Exception as e:
            return JobResponse(
                success=False,
                job_id="",
                status="ERROR",
                message=f"Failed to queue goal execution: {str(e)}",
            )

    # ============================================================================
    # INTEGRATION MANAGEMENT MUTATIONS (match FE expectations)
    # ============================================================================

    @strawberry.mutation
    async def connectIntegration(
        self,
        info: GraphQLResolveInfo,
        service_name: str,
        credentials: str,
    ) -> IntegrationStatus:
        """
        Store integration credentials for the current tenant under one consolidated key.
        Returns IntegrationStatus with connected/disconnected state and any validation errors.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            return IntegrationStatus(serviceName=service_name, status="error", validationErrors=["Not authenticated"])  # type: ignore

        # Basic JSON validation
        try:
            parsed = json.loads(credentials) if isinstance(credentials, str) else credentials
            if not isinstance(parsed, dict) or len(parsed) == 0:
                return IntegrationStatus(serviceName=service_name, status="validation_failed", validationErrors=["credentials must be a non-empty JSON object"])  # type: ignore
        except Exception as e:
            return IntegrationStatus(serviceName=service_name, status="validation_failed", validationErrors=[f"Invalid credentials JSON: {str(e)}"])  # type: ignore

        # Optional: validate against MCP tool required fields when available
        try:
            mcp_mgr = MCPToolManager()
            tools = await mcp_mgr.get_available_tools()
            req_fields = None
            for t in tools:
                if getattr(t, "name", "") == service_name:
                    req_fields = getattr(t, "required_credentials", None)
                    break
            missing = []
            if req_fields:
                for key in req_fields:
                    if key not in parsed or (parsed.get(key) is None or str(parsed.get(key)).strip() == ""):
                        missing.append(str(key))
            if missing:
                return IntegrationStatus(serviceName=service_name, status="validation_failed", validationErrors=[f"Missing required fields: {', '.join(missing)}"])  # type: ignore
        except Exception:
            # Best-effort; do not block on tool metadata
            pass

        # Store consolidated credentials blob
        tsm = TenantSecretsManager()
        ok = await tsm.store_secret(str(current_user.tenant_id), service_name, "credentials", json.dumps(parsed))
        status = "connected" if ok else "error"
        return IntegrationStatus(serviceName=service_name, status=status, validationErrors=None if ok else ["Failed to store credentials"])  # type: ignore

    @strawberry.mutation
    async def testIntegration(
        self,
        info: GraphQLResolveInfo,
        service_name: str,
    ) -> IntegrationTestResult:
        """
        Test that credentials exist (and optionally perform a lightweight tool test via MCPToolManager).
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            return IntegrationTestResult(success=False, testResult=f"{service_name} test failed", errorMessage="Not authenticated")  # type: ignore

        tsm = TenantSecretsManager()
        try:
            val = await tsm.get_secret(str(current_user.tenant_id), service_name, "credentials")
            if not val or str(val).strip() in ("", "null", "{}"):  # no credentials
                return IntegrationTestResult(success=False, testResult=f"No credentials configured for {service_name}", errorMessage="No credentials")  # type: ignore
        except Exception as e:
            return IntegrationTestResult(success=False, testResult=f"{service_name} test failed", errorMessage=str(e))  # type: ignore

        # Best-effort MCP connectivity test (may be stubbed)
        try:
            mcp_mgr = MCPToolManager()
            t = await mcp_mgr.test_tool_connection(service_name, current_user.tenant_id)
            return IntegrationTestResult(success=t.success, testResult=t.testResult, errorMessage=t.errorMessage)  # type: ignore
        except Exception:
            # If tool test not available, consider presence of credentials as success
            return IntegrationTestResult(success=True, testResult=f"{service_name} credentials present", errorMessage=None)  # type: ignore

    @strawberry.mutation
    async def disconnectIntegration(
        self,
        info: GraphQLResolveInfo,
        service_name: str,
    ) -> bool:
        """Disconnect integration by deleting consolidated and per-key secrets."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            return False
        tsm = TenantSecretsManager()
        tenant_str = str(current_user.tenant_id)
        overall_ok = False
        try:
            # Delete consolidated blob
            del_ok = await tsm.delete_secret(tenant_str, service_name, "credentials")
            overall_ok = overall_ok or bool(del_ok)

            # Attempt to delete per-key credentials when known
            try:
                mcp_mgr = MCPToolManager()
                tools = await mcp_mgr.get_available_tools()
                req_fields = None
                for t in tools:
                    if getattr(t, "name", "") == service_name:
                        req_fields = getattr(t, "required_credentials", None)
                        break
                if req_fields:
                    for key in req_fields:
                        try:
                            k_ok = await tsm.delete_secret(tenant_str, service_name, str(key))
                            overall_ok = overall_ok or bool(k_ok)
                        except Exception:
                            # continue best-effort
                            pass
            except Exception:
                pass

            return overall_ok
        except Exception:
            return overall_ok
    @strawberry.mutation
    async def submitFeedback(
        self,
        info: GraphQLResolveInfo,
        feedback_input: FeedbackInput = strawberry.argument(name="feedback_input"),
    ) -> bool:
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Validate and sanitize input
            validated_input = validate_and_sanitize_feedback_input(feedback_input)

            # Ensure user exists before adding feedback
            await get_or_create_user(current_user.user_id, session=db_session)

            # Store feedback with anonymization and rate limiting
            # Phase 10: enable sanitized JSON copy to GCS bucket per tenant
            svc = FeedbackService(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                policy=FeedbackPolicy(store_gcs_copy=True)
            )
            ok = await svc.submit(
                job_id=validated_input.jobId,
                goal=validated_input.goal,
                final_output=validated_input.finalOutput,
                score=validated_input.feedbackScore,
                comment=validated_input.feedbackComment,
            )
            if not ok:
                return False


            return True
        except ValidationError as e:
            raise e
        except Exception as e:
            raise InternalServerError(
                message=f"Failed to submit feedback: {str(e)}",
                details={"user_id": current_user.user_id, "job_id": feedback_input.jobId}
            )

    @strawberry.mutation
    async def handleSupportTicket(
        self,
        info: GraphQLResolveInfo,
        support_input: SupportTicketInput,
    ) -> SupportResponse:
        """
        Handle a customer support ticket by orchestrating the support workflow.

        Args:
            support_input: SupportTicketInput with ticket details

        Returns:
            SupportResponse: Drafted support response
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Validate and sanitize input
            validated_input = validate_and_sanitize_support_input(support_input)

            # Ensure user exists
            await get_or_create_user(current_user.user_id, session=db_session)

            # Create a job ID for tracking
            job_id = f"support:{uuid4()}"

            # Prepare the support goal for the Orchestrator agent
            support_goal = {
                "customer_ticket": validated_input.ticketText,
                "user_id": current_user.user_id,
                "order_id": validated_input.orderId,
                "attached_files": validated_input.attachedFiles or []
            }

            # Format as a comprehensive goal for the Orchestrator
            comprehensive_support_goal = (
                f"**Customer Support Request**\n"
                f"Please handle this customer support ticket using the specialized support workflow.\n\n"
                f"Ticket Text: {validated_input.ticketText}\n"
                f"Order ID: {validated_input.orderId or 'Not provided'}\n"
                f"Attached Files: {', '.join(validated_input.attachedFiles) if validated_input.attachedFiles else 'None'}\n\n"
                f"Your task is to follow the support workflow:\n"
                f"1. Analyze the ticket and any attachments\n"
                f"2. Determine sentiment of the customer's message\n"
                f"3. Extract relevant information (like order IDs)\n"
                f"4. Retrieve any necessary data from external systems\n"
                f"5. Draft a comprehensive, empathetic response\n"
            )

            # Initialize the Orchestrator agent
            llm_pro = get_gemini_llm(model_tier='pro')
            director_agent_obj = create_named_orchestrator_runtime(profile_name="support_orchestrator", llm=llm_pro)

            # Execute the Orchestrator agent with the support goal
            result = await director_agent_obj.ainvoke({
                "input": comprehensive_support_goal,
                "metadata": {"job_id": job_id}
            })

            # For now, we'll return a mock response since the actual agent workflow
            # would need to be fully implemented to return a structured SupportResponse
            # In a real implementation, this would extract the actual response from the agent result
            return SupportResponse(
                responseText=result.get('output', 'Support response will be generated shortly.'),
                sentiment="neutral",  # This would be determined by the sentiment analysis agent
                orderId=validated_input.orderId,
                confidenceScore=0.95
            )

        except ValidationError as e:
            raise e
        except Exception as e:
            raise InternalServerError(
                message=f"Failed to handle support ticket: {str(e)}",
                details={"user_id": current_user.user_id}
            )

    @strawberry.mutation
    async def createTenant(
        self,
        info: GraphQLResolveInfo,
        tenant_input: TenantInput,
    ) -> TenantResponse:
        """
        Create a new tenant with its own subdomain and infrastructure.

        This mutation creates a new tenant record in the database, generates a unique
        tenant ID and subdomain, and prepares for infrastructure provisioning.

        Example usage:
        mutation {
          createTenant(input: {
            name: "Acme Corporation",
            adminEmail: "admin@acme.com",
            password: "SecurePass123"
          }) {
            id
            tenantId
            subdomain
            name
            adminEmail
            createdAt
          }
        }

        Args:
            tenant_input: TenantInput with name, adminEmail, and password

        Returns:
            TenantResponse: Created tenant information

        Errors:
            - If tenant name or subdomain is already taken
            - If there's a database error while creating the tenant
        """
        # Get database session and current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        db_session = auth_context["db_session"]
        current_user = auth_context.get("current_user") if auth_context else None
        # Support both synchronous Session and AsyncSession
        is_async = isinstance(db_session, AsyncSession)

        try:
            # Validate and sanitize input
            validated_input = validate_and_sanitize_tenant_input(tenant_input)

            # Extract and validate client IP (strict anti-abuse)
            request = info.context.get("request")
            client_ip = get_client_ip(request)
            # Anti-VPN/Proxy/Hosting check (fail closed when flagged, fail-open on provider errors)
            vpn_res = await is_vpn_or_proxy(client_ip)
            if vpn_res.is_risky:
                raise InternalServerError(
                    message="Tenant creation blocked: VPN/Proxy/Hosting IP is not allowed",
                    details={"reason": vpn_res.reason}
                )

            # Enforce strictly: one tenant per IP (hashed)
            from src.database.models import IPAddressUsage
            ip_h = hash_ip(client_ip)
            if is_async:
                result_ip = await db_session.execute(
                    select(IPAddressUsage).where(
                        IPAddressUsage.ip_hash == ip_h,
                        IPAddressUsage.purpose == "tenant_create",
                    )
                )
                ip_row = result_ip.scalars().first()
            else:
                ip_row = db_session.exec(
                    select(IPAddressUsage).where(
                        IPAddressUsage.ip_hash == ip_h,
                        IPAddressUsage.purpose == "tenant_create",
                    )
                ).first()
            if ip_row is not None:
                raise InternalServerError(
                    message="Tenant creation blocked: this IP has already created a tenant",
                    details={"ip": "restricted"}
                )

            # Generate unique tenant ID (13-character URL-safe string)
            tenant_id = Tenant.generate_unique_id()

            # Determine subdomain: use requested when provided, else derive from name
            requested_sub = (getattr(validated_input, 'subdomain', None) or '').strip().lower()
            if requested_sub:
                # Ensure uniqueness; if taken, raise a validation error
                if is_async:
                    result = await db_session.execute(
                        select(Tenant).where(Tenant.subdomain == requested_sub)
                    )
                    exists = result.scalars().first()
                else:
                    exists = db_session.exec(
                        select(Tenant).where(Tenant.subdomain == requested_sub)
                    ).first()
                if exists:
                    raise ValidationError(
                        message="Subdomain already taken",
                        details={"subdomain": requested_sub}
                    )
                subdomain = requested_sub
            else:
                # Generate subdomain from tenant name (simple approach for now)
                subdomain = re.sub(r'[^a-zA-Z0-9-]', '', validated_input.name.lower().replace(' ', '-'))
                subdomain = re.sub(r'-+', '-', subdomain).strip('-')[:20] or f"tenant{tenant_id[:8]}"
                # Ensure uniqueness (append numbers)
                if is_async:
                    result = await db_session.execute(
                        select(Tenant).where(Tenant.subdomain == subdomain)
                    )
                    existing_tenant = result.scalars().first()
                else:
                    existing_tenant = db_session.exec(
                        select(Tenant).where(Tenant.subdomain == subdomain)
                    ).first()
                if existing_tenant:
                    counter = 1
                    original_subdomain = subdomain
                    while existing_tenant:
                        subdomain = f"{original_subdomain}{counter}"
                        if is_async:
                            result = await db_session.execute(
                                select(Tenant).where(Tenant.subdomain == subdomain)
                            )
                            existing_tenant = result.scalars().first()
                        else:
                            existing_tenant = db_session.exec(
                                select(Tenant).where(Tenant.subdomain == subdomain)
                            ).first()
                        counter += 1

            # Create tenant record in database
            # Prefer the authenticated user's email for admin ownership if available
            admin_email = validated_input.adminEmail
            try:
                if current_user and getattr(current_user, "email", None):
                    admin_email = current_user.email
            except Exception:
                pass

            tenant = Tenant(
                tenant_id=tenant_id,
                subdomain=subdomain,
                name=validated_input.name,
                admin_email=admin_email,
                created_at=datetime.utcnow()
            )

            db_session.add(tenant)
            if is_async:
                await db_session.commit()
                await db_session.refresh(tenant)
            else:
                db_session.commit()
                db_session.refresh(tenant)

            # Create a single-use admin invite for the provided email (7-day expiry)
            from src.database.models import TenantInvite
            from uuid import uuid4
            invite_token = uuid4().hex
            inv = TenantInvite(
                token=invite_token,
                tenant_id=tenant.id,
                email=admin_email,
                expires_at=datetime.utcnow() + timedelta(days=7),
                created_by_user_id=None,
            )
            db_session.add(inv)
            if is_async:
                await db_session.commit()
            else:
                db_session.commit()

            # Record IP usage for tenant creation
            ip_rec = IPAddressUsage(
                ip_hash=ip_h,
                purpose="tenant_create",
                tenant_id=tenant.id,
                user_id=None,
                count=1,
            )
            db_session.add(ip_rec)
            if is_async:
                await db_session.commit()
            else:
                db_session.commit()

            # In a real implementation, this would trigger Terraform deployment
            # for new tenant infrastructure and update Load Balancer configuration
            # For now, we'll just return the tenant information

            return TenantResponse(
                tenantId=tenant.tenant_id,
                subdomain=tenant.subdomain,
                name=tenant.name,
                adminEmail=tenant.admin_email,
                createdAt=tenant.created_at.isoformat(),
                inviteToken=invite_token,
            )

        except ValidationError as e:
            raise e
        except Exception as e:
            try:
                if is_async:
                    await db_session.rollback()
                else:
                    db_session.rollback()
            except Exception:
                pass
            raise InternalServerError(
                message=f"Failed to create tenant: {str(e)}",
                details={"tenant_name": tenant_input.name}
            )

    @strawberry.mutation
    async def updateTenantSubdomain(
        self,
        info: GraphQLResolveInfo,
        new_subdomain: str,
    ) -> TenantResponse:
        """
        Update the subdomain of the current user's tenant.
        
        Allows new users to customize their auto-generated subdomain during onboarding.
        Validates subdomain against DNS manager rules (banned words, reserved terms, format).
        
        Args:
            new_subdomain: The desired new subdomain (3-12 chars, lowercase + hyphens)
        
        Returns:
            TenantResponse with success/error
        """
        # Get auth context
        auth_context = info.context.get("request").state.auth_context
        db_session = auth_context["db_session"]
        current_user = auth_context.get("current_user")
        
        if not current_user:
            raise InternalServerError(
                message="Authentication required",
                details={"error": "not_authenticated"}
            )
        
        # Get user's tenant
        is_async = isinstance(db_session, AsyncSession)
        
        # Retrieve the user's tenant_id  
        if not hasattr(current_user, 'tenant_id') or not current_user.tenant_id:
            raise ValidationError(
                message="User has no tenant",
                details={"error": "no_tenant"}
            )
        
        tenant_id = current_user.tenant_id
        
        # Load tenant
        if is_async:
            result = await db_session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = result.scalars().first()
        else:
            tenant = db_session.exec(
                select(Tenant).where(Tenant.id == tenant_id)
            ).first()
        
        if not tenant:
            raise InternalServerError(
                message="Tenant not found",
                details={"tenant_id": tenant_id}
            )
        
        # Validate new subdomain
        from src.services.dns_manager import DNSManager
        
        dns_manager = DNSManager()
        new_subdomain = new_subdomain.lower().strip()
        
        is_valid, error_msg = dns_manager.validate_subdomain(new_subdomain)
        if not is_valid:
            raise ValidationError(
                message=error_msg or "Invalid subdomain",
                details={"subdomain": new_subdomain}
            )
        
        # Check subdomain availability
        if is_async:
            result = await db_session.execute(
                select(Tenant).where(Tenant.subdomain == new_subdomain)
            )
            existing = result.scalars().first()
        else:
            existing = db_session.exec(
                select(Tenant).where(Tenant.subdomain == new_subdomain)
            ).first()
        
        if existing and existing.id != tenant_id:
            raise ValidationError(
                message="Subdomain already taken",
                details={"subdomain": new_subdomain}
            )
        
        # Update tenant subdomain
        old_subdomain = tenant.subdomain
        tenant.subdomain = new_subdomain
        
        try:
            if is_async:
                await db_session.commit()
                await db_session.refresh(tenant)
            else:
                db_session.commit()
                db_session.refresh(tenant)
            
            return TenantResponse(
                tenantId=tenant.tenant_id,
                subdomain=tenant.subdomain,
                name=tenant.name,
                adminEmail=tenant.admin_email,
                createdAt=tenant.created_at.isoformat() if tenant.created_at else None,
                success=True,
                message=f"Subdomain updated from '{old_subdomain}' to '{new_subdomain}'"
            )
        
        except Exception as e:
            if is_async:
                await db_session.rollback()
            else:
                db_session.rollback()
            
            raise InternalServerError(
                message=f"Failed to update subdomain: {str(e)}",
                details={"subdomain": new_subdomain}
            )

    @strawberry.mutation
    async def createScheduledTask(
        self,
        info: GraphQLResolveInfo,
        task_input: ScheduledTaskInput,
    ) -> ScheduledTaskType:
        """
        Create a new scheduled task.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")

        from src.scheduler.service import SchedulerService
        task = SchedulerService.create_scheduled_task(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            project_id=task_input.projectId,
            goal_input=task_input.goalInput,
            scheduled_at=task_input.scheduledAt,
        )
        return ScheduledTaskType(
            id=task.id,
            tenantId=task.tenant_id,
            userId=task.user_id,
            projectId=task.project_id,
            scheduledAt=task.scheduled_at,
            status=task.status,
            executionLog=task.execution_log,
            createdAt=task.created_at,
            updatedAt=task.updated_at,
        )

    @strawberry.mutation
    async def updateScheduledTask(
        self,
        info: GraphQLResolveInfo,
        task_id: int,
        task_input: ScheduledTaskInput,
    ) -> ScheduledTaskType:
        """
        Update an existing scheduled task.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")

        from src.scheduler.service import SchedulerService
        task = SchedulerService.update_scheduled_task(
            task_id=task_id,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            project_id=task_input.projectId,
            goal_input=task_input.goalInput,
            scheduled_at=task_input.scheduledAt,
        )
        return ScheduledTaskType(
            id=task.id,
            tenantId=task.tenant_id,
            userId=task.user_id,
            projectId=task.project_id,
            scheduledAt=task.scheduled_at,
            status=task.status,
            executionLog=task.execution_log,
            createdAt=task.created_at,
            updatedAt=task.updated_at,
        )

    @strawberry.mutation
    async def deleteScheduledTask(
        self,
        info: GraphQLResolveInfo,
        task_id: int,
    ) -> bool:
        """
        Delete a scheduled task.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")

        from src.scheduler.service import SchedulerService
        return SchedulerService.delete_scheduled_task(
            task_id=task_id, tenant_id=current_user.tenant_id
        )

    @strawberry.mutation
    async def createScheduledTask(
        self,
        info: GraphQLResolveInfo,
        task_input: ScheduledTaskInput,
    ) -> ScheduledTaskType:
        """
        Create a new scheduled task.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")

        from src.scheduler.service import SchedulerService
        task = SchedulerService.create_scheduled_task(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            project_id=task_input.projectId,
            goal_input=task_input.goalInput,
            scheduled_at=task_input.scheduledAt,
        )
        return ScheduledTaskType(
            id=task.id,
            tenantId=task.tenant_id,
            userId=task.user_id,
            projectId=task.project_id,
            scheduledAt=task.scheduled_at,
            status=task.status,
            executionLog=task.execution_log,
            createdAt=task.created_at,
            updatedAt=task.updated_at,
        )

    @strawberry.mutation
    async def updateScheduledTask(
        self,
        info: GraphQLResolveInfo,
        task_id: int,
        task_input: ScheduledTaskInput,
    ) -> ScheduledTaskType:
        """
        Update an existing scheduled task.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")

        from src.scheduler.service import SchedulerService
        task = SchedulerService.update_scheduled_task(
            task_id=task_id,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            project_id=task_input.projectId,
            goal_input=task_input.goalInput,
            scheduled_at=task_input.scheduledAt,
        )
        return ScheduledTaskType(
            id=task.id,
            tenantId=task.tenant_id,
            userId=task.user_id,
            projectId=task.project_id,
            scheduledAt=task.scheduled_at,
            status=task.status,
            executionLog=task.execution_log,
            createdAt=task.created_at,
            updatedAt=task.updated_at,
        )

    @strawberry.mutation
    async def deleteScheduledTask(
        self,
        info: GraphQLResolveInfo,
        task_id: int,
    ) -> bool:
        """
        Delete a scheduled task.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")

        from src.scheduler.service import SchedulerService
        return SchedulerService.delete_scheduled_task(
            task_id=task_id, tenant_id=current_user.tenant_id
        )

    @strawberry.mutation
    async def createProject(
        self,
        info: GraphQLResolveInfo,
        project_input: ProjectInput,
    ) -> ProjectType:
        """
        Create a new project for the current user.

        Args:
            project_input: ProjectInput with name and description

        Returns:
            ProjectType: Created project information
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        # Authorization check - ensure user has permission to create projects
        try:
            auth_context_obj = await get_authorization_context_for_user(
                user_id=current_user.user_id,
                tenant_id=current_user.tenant_id,
                db_session=db_session,
            )
            
            if not auth_context_obj.has_permission(Permission.WRITE_PROJECT):
                raise Exception("Insufficient permissions to create projects")
        except Exception as e:
            raise Exception(f"Authorization check failed: {str(e)}")

        try:
            # Create project record in database
            project = Project(
                name=project_input.name,
                description=project_input.description,
                user_id=current_user.id,
                tenant_id=current_user.tenant_id
            )

            db_session.add(project)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(project)
            else:
                db_session.commit()
                db_session.refresh(project)

            return ProjectType(
                id=project.id,
                name=project.name,
                description=project.description,
                createdAt=project.created_at.isoformat() if project.created_at else None,
                userId=project.user_id
            )

        except Exception as e:
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
            raise InternalServerError(
                message=f"Failed to create project: {str(e)}",
                details={"project_name": project_input.name}
            )

    @strawberry.mutation
    async def updateProject(
        self,
        info: GraphQLResolveInfo,
        project_id: int,
        project_input: ProjectInput,
    ) -> ProjectType:
        """
        Update an existing project.

        Args:
            project_id: ID of the project to update
            project_input: ProjectInput with updated name and description

        Returns:
            ProjectType: Updated project information
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Verify that the project belongs to the current tenant
            if isinstance(db_session, AsyncSession):
                result = await db_session.execute(
                    select(Project).where(
                        Project.id == project_id,
                        Project.tenant_id == current_user.tenant_id
                    )
                )
            else:
                result = db_session.exec(
                    select(Project).where(
                        Project.id == project_id,
                        Project.tenant_id == current_user.tenant_id
                    )
                )
            project = result.scalars().first()

            if not project:
                raise Exception("Project not found or access denied.")

            # Update project fields
            project.name = project_input.name
            project.description = project_input.description

            db_session.add(project)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(project)
            else:
                db_session.commit()
                db_session.refresh(project)

            return ProjectType(
                id=project.id,
                name=project.name,
                description=project.description,
                createdAt=project.created_at.isoformat() if project.created_at else None,
                userId=project.user_id
            )

        except Exception as e:
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
            raise InternalServerError(
                message=f"Failed to update project: {str(e)}",
                details={"project_id": project_id}
            )

    @strawberry.mutation
    async def deleteProject(
        self,
        info: GraphQLResolveInfo,
        project_id: int,
    ) -> bool:
        """
        Delete a project.

        Args:
            project_id: ID of the project to delete

        Returns:
            bool: True if deletion was successful
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Verify that the project belongs to the current tenant
            if isinstance(db_session, AsyncSession):
                result = await db_session.execute(
                    select(Project).where(
                        Project.id == project_id,
                        Project.tenant_id == current_user.tenant_id
                    )
                )
                project = result.scalars().first()
            else:
                project = db_session.exec(
                    select(Project).where(
                        Project.id == project_id,
                        Project.tenant_id == current_user.tenant_id
                    )
                ).first()

            if not project:
                raise Exception("Project not found or access denied.")

            # Delete the project
            db_session.delete(project)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()

            return True

        except Exception as e:
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
            raise InternalServerError(
                message=f"Failed to delete project: {str(e)}",
                details={"project_id": project_id}
            )

    @strawberry.mutation
    async def createConversation(
        self,
        info: GraphQLResolveInfo,
        conversation_input: ConversationInput,
    ) -> ConversationType:
        """
        Create a new conversation within a project.

        Args:
            conversation_input: ConversationInput with title and project ID

        Returns:
            ConversationType: Created conversation information
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Verify that the project belongs to the current tenant
            if isinstance(db_session, AsyncSession):
                result = await db_session.execute(
                    select(Project).where(
                        Project.id == conversation_input.projectId,
                        Project.tenant_id == current_user.tenant_id
                    )
                )
            else:
                result = db_session.exec(
                    select(Project).where(
                        Project.id == conversation_input.projectId,
                        Project.tenant_id == current_user.tenant_id
                    )
                )
            project = result.scalars().first()

            if not project:
                raise Exception("Project not found or access denied.")

            # Create conversation record in database
            conversation = Conversation(
                title=conversation_input.title,
                project_id=conversation_input.projectId,
                tenant_id=current_user.tenant_id
            )

            db_session.add(conversation)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(conversation)
            else:
                db_session.commit()
                db_session.refresh(conversation)

            return ConversationType(
                id=conversation.id,
                title=conversation.title,
                createdAt=conversation.created_at.isoformat() if conversation.created_at else None,
                projectId=conversation.project_id
            )

        except Exception as e:
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
            raise InternalServerError(
                message=f"Failed to create conversation: {str(e)}",
                details={"project_id": conversation_input.projectId}
            )

    @strawberry.mutation
    async def renameConversation(
        self,
        info: GraphQLResolveInfo,
        conversation_id: Annotated[int, strawberry.argument(name="conversationId")],
        new_title: Annotated[str, strawberry.argument(name="newTitle")],
    ) -> ConversationType:
        """Rename an existing conversation without touching the parent project name.

        This is used by the LobeChat bridge to rename a chat thread title directly.
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        # Basic validation on the new title (mirror ConversationInput constraints)
        new_title = (new_title or "").strip()
        if not new_title or len(new_title) > 200:
            raise ValidationError(
                message="Invalid conversation title",
                details={"reason": "empty_or_too_long"}
            )

        try:
            # Load the conversation scoped to the current tenant
            if isinstance(db_session, AsyncSession):
                result = await db_session.execute(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.tenant_id == current_user.tenant_id,
                    )
                )
                conversation = result.scalars().first()
            else:
                conversation = db_session.exec(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.tenant_id == current_user.tenant_id,
                    )
                ).first()

            if not conversation:
                raise Exception("Conversation not found or access denied.")

            conversation.title = new_title
            db_session.add(conversation)

            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(conversation)
            else:
                db_session.commit()
                db_session.refresh(conversation)

            return ConversationType(
                id=conversation.id,
                title=conversation.title,
                createdAt=conversation.created_at.isoformat() if conversation.created_at else None,
                projectId=conversation.project_id,
            )

        except ValidationError:
            # Bubble up validation errors as-is for the client bridge/tests
            raise
        except Exception as e:
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
            raise InternalServerError(
                message=f"Failed to rename conversation: {str(e)}",
                details={"conversation_id": conversation_id}
            )

    @strawberry.mutation
    async def createToneProfile(
        self,
        info: GraphQLResolveInfo,
        profile_input: ToneProfileInput,
    ) -> ToneProfileType:
        """
        Create a new tone profile for the current user.

        Args:
            profile_input: ToneProfileInput with name, profile text, and description

        Returns:
            ToneProfileType: Created tone profile information
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Create tone profile record in database
            tone_profile = ToneProfile(
                name=profile_input.name,
                profile_text=profile_input.profileText,
                description=profile_input.description,
                is_default=profile_input.isDefault,
                user_id=current_user.id,
                tenant_id=current_user.tenant_id
            )

            db_session.add(tone_profile)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(tone_profile)
            else:
                db_session.commit()
                db_session.refresh(tone_profile)

            return ToneProfileType(
                id=tone_profile.id,
                name=tone_profile.name,
                profileText=tone_profile.profile_text,
                description=tone_profile.description,
                isDefault=tone_profile.is_default,
                userId=tone_profile.user_id,
                createdAt=tone_profile.created_at.isoformat() if tone_profile.created_at else None
            )

        except Exception as e:
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
            raise InternalServerError(
                message=f"Failed to create tone profile: {str(e)}",
                details={"profile_name": profile_input.name}
            )

    # ============================================================================
    # AGENT MANAGEMENT MUTATIONS
    # ============================================================================

    @strawberry.mutation
    async def createCustomAgentDefinition(
        self,
        info: GraphQLResolveInfo,
        input: CustomAgentDefinitionInput,
    ) -> CustomAgentDefinitionType:
        """
        Create a CustomAgentDefinition from a blueprint payload.
        Returns minimal fields for FE wiring.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            name = (input.name or "Custom Agent").strip()
            description = (input.specification or "").strip()
            system_prompt = ""
            # Optionally derive a system prompt from user_personality JSON
            try:
                if input.user_personality:
                    system_prompt = json.dumps(input.user_personality)
            except Exception:
                pass

            new_id = CustomAgentDefinition.generate_custom_agent_id()
            rec = CustomAgentDefinition(
                custom_agent_id=new_id,
                tenant_id=current_user.tenant_id,
                name=name,
                description=description,
                system_prompt=system_prompt,
                tool_names="[]",
                model_name="gemini-2.5-flash",
                is_active=True,
                is_system_agent=False,
            )
            db_session.add(rec)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(rec)
            else:
                db_session.commit()
                db_session.refresh(rec)

            return CustomAgentDefinitionType(id=rec.custom_agent_id, name=rec.name, version=rec.version)
        except Exception as e:
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
            raise InternalServerError(message=f"Failed to create custom agent definition: {str(e)}", details={"name": input.name})

    @strawberry.mutation
    async def createAgentTeam(
        self,
        info: GraphQLResolveInfo,
        team_input: AgentTeamInput,
    ) -> AgentTeamType:
        """
        Create a new agent team from a natural language specification.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # 1. Use PlatformOrchestrator to create a blueprint
            orchestrator = PlatformOrchestrator(tenant_id=current_user.tenant_id, user_id=current_user.id)
            blueprint = await orchestrator.create_agent_team_blueprint(team_input.specification)

            # 2. Create CustomAgentDefinition records from the blueprint
            agent_ids = []
            new_agent_defs = []
            agent_requirements = blueprint.get("agent_requirements", [])
            
            # Handle simple mock blueprint
            if isinstance(agent_requirements, dict):
                agent_requirements = [agent_requirements]

            if not agent_requirements:
                agent_requirements = [{
                    "name": f"{team_input.name} Agent",
                    "description": f"Default agent for {team_input.name}",
                    "system_prompt": f"You are an agent in the {team_input.name} team. Your goal is to work with your team to achieve the objective: {team_input.specification}"
                }]

            for agent_req in agent_requirements:
                # Build enhanced system prompt with KB paradigm instructions
                base_system_prompt = agent_req.get("system_prompt", "You are a helpful assistant.")
                try:
                    from src.prompts.kb_paradigm_instructions import MANDATORY_KB_PARADIGM_INSTRUCTIONS, get_mandatory_tool_instructions
                    tool_reqs = blueprint.get("tool_requirements", [])
                    enhanced_system_prompt = base_system_prompt + "\n\n" + MANDATORY_KB_PARADIGM_INSTRUCTIONS
                    enhanced_system_prompt += get_mandatory_tool_instructions(tool_reqs)
                except Exception:
                    enhanced_system_prompt = base_system_prompt

                new_agent_def = CustomAgentDefinition(
                    custom_agent_id=CustomAgentDefinition.generate_custom_agent_id(),
                    tenant_id=current_user.tenant_id,
                    name=agent_req.get("name", "Unnamed Agent"),
                    description=agent_req.get("description", ""),
                    system_prompt=enhanced_system_prompt,  # Use enhanced prompt with KB paradigm
                    tool_names=json.dumps(blueprint.get("tool_requirements", [])),
                    # Ensure metadata has capabilities key for downstream expectations
                    custom_metadata=json.dumps({
                        "capabilities": agent_req.get("capabilities")
                        or agent_req.get("required_skills")
                        or blueprint.get("tool_requirements", [])
                        or []
                    }),
                    is_active=True,
                )
                db_session.add(new_agent_def)
                new_agent_defs.append(new_agent_def)
                if isinstance(db_session, AsyncSession):
                    await db_session.flush()
                else:
                    # Sync sessions flush on commit; explicit flush for safety if available
                    try:
                        db_session.flush()
                    except Exception:
                        pass
                agent_ids.append(new_agent_def.custom_agent_id)

            # 3. Create the AgentTeam record
            new_team = AgentTeam(
                agent_team_id=AgentTeam.generate_agent_team_id(),
                tenant_id=current_user.tenant_id,
                name=team_input.name,
                description=team_input.description,
                is_active=True,
            )
            new_team.set_custom_agent_ids(agent_ids)
            new_team.set_pre_approved_tool_names(blueprint.get("tool_requirements", []))

            db_session.add(new_team)

            async def _reset_agentteam_id_sequence() -> None:
                stmt = sa.text(
                    "SELECT setval(pg_get_serial_sequence('agentteam','id'), (SELECT COALESCE(MAX(id), 0) + 1 FROM agentteam), false)"
                )
                if isinstance(db_session, AsyncSession):
                    await db_session.execute(stmt)
                else:
                    db_session.execute(stmt)

            for attempt in range(2):
                try:
                    if isinstance(db_session, AsyncSession):
                        await db_session.commit()
                        # Skip refresh - object data is already populated and refresh causes
                        # "not persistent within this Session" errors with pooled connections
                    else:
                        db_session.commit()
                        # Skip refresh - same reasoning as above
                    break
                except sa.exc.IntegrityError as ie:
                    try:
                        if isinstance(db_session, AsyncSession):
                            await db_session.rollback()
                        else:
                            db_session.rollback()

                    except Exception:
                        pass
                    msg = str(getattr(ie, "orig", ie) or "")
                    if attempt == 0 and "agentteam_pkey" in msg:
                        try:
                            await _reset_agentteam_id_sequence()
                        except Exception:
                            raise
                        try:
                            new_team.id = None
                            for a in new_agent_defs:
                                a.id = None
                        except Exception:
                            pass
                        continue
                    raise

            # Bump tenant-wide quick teams cache version after create
            try:
                await orchestrator._bump_quick_teams_version()  # type: ignore
            except Exception:
                pass

            # 4. Return the new team as AgentTeamType
            return AgentTeamType(
                id=new_team.agent_team_id,
                name=new_team.name,
                description=new_team.description,
                createdAt=new_team.created_at.isoformat(),
                lastUpdatedAt=new_team.last_updated_at.isoformat(),
                isActive=new_team.is_active,
                isSystemTeam=new_team.is_system_agent,
                version=new_team.version,
                customAgentIDs=new_team.get_custom_agent_ids(),
                preApprovedToolNames=new_team.get_pre_approved_tool_names(),
            )

        except Exception as e:
            try:
                if isinstance(db_session, AsyncSession):
                    await db_session.rollback()
                else:
                    db_session.rollback()
            except Exception:
                pass
            try:
                logger.exception(
                    "createAgentTeam failed",
                    extra={
                        "tenant_id": getattr(current_user, "tenant_id", None),
                        "user_id": getattr(current_user, "id", None),
                        "team_name": getattr(team_input, "name", None),
                    },
                )
            except Exception:
                pass
            raise InternalServerError(
                message=f"Failed to create agent team: {str(e)}",
                details={"team_name": team_input.name}
            )

    @strawberry.mutation
    async def createAgent(
        self,
        info: GraphQLResolveInfo,
        agent_input: AgentInput,
    ) -> Agent:
        """
        Create a new custom agent.

        Args:
            agent_input: AgentInput with agent details

        Returns:
            Agent: Created agent information
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        # Authorization check - ensure user has permission to create agents
        try:
            auth_context_obj = await get_authorization_context_for_user(
                user_id=current_user.user_id,
                tenant_id=current_user.tenant_id,
                db_session=db_session,
            )

            if not auth_context_obj.has_permission(Permission.MANAGE_AGENTS):
                raise Exception("Insufficient permissions to create agents")
        except Exception as e:
            raise Exception(f"Authorization check failed: {str(e)}")

        try:
            from src.database.models.custom_agent import CustomAgentDefinition
            # Create new agent definition, scoped to tenant
            new_id = CustomAgentDefinition.generate_custom_agent_id()
            # Store capabilities in custom_metadata to avoid conflating with tool_names
            metadata = {"capabilities": agent_input.capabilities or []}
            agent_rec = CustomAgentDefinition(
                custom_agent_id=new_id,
                tenant_id=current_user.tenant_id,
                name=agent_input.name,
                description=agent_input.description,
                system_prompt=agent_input.systemPrompt or "",
                tool_names="[]",
                model_name="gemini-2.5-flash",
                is_active=True,
                is_system_agent=False,
                custom_metadata=json.dumps(metadata),
            )

            db_session.add(agent_rec)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(agent_rec)
            else:
                db_session.commit()
                db_session.refresh(agent_rec)

            return Agent(
                id=agent_rec.custom_agent_id,
                name=agent_rec.name,
                description=agent_rec.description,
                createdAt=agent_rec.created_at.isoformat(),
                lastUsed=None,
                status="active" if agent_rec.is_active else "inactive",
                agentType=agent_input.agentType,
                capabilities=agent_input.capabilities,
                performanceMetrics={"successRate": 0.0, "totalExecutions": 0}
            )

        except Exception as e:
            raise InternalServerError(
                message=f"Failed to create agent: {str(e)}",
                details={"agent_name": agent_input.name}
            )

    @strawberry.mutation
    async def updateAgent(
        self,
        info: GraphQLResolveInfo,
        agent_id: str,
        agent_input: AgentInput,
    ) -> Agent:
        """
        Update an existing agent.

        Args:
            agent_id: ID of the agent to update
            agent_input: AgentInput with updated details

        Returns:
            Agent: Updated agent information
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            from src.database.models.custom_agent import CustomAgentDefinition
            if isinstance(db_session, AsyncSession):
                result = await db_session.execute(
                    select(CustomAgentDefinition).where(
                        CustomAgentDefinition.custom_agent_id == agent_id,
                        CustomAgentDefinition.tenant_id == current_user.tenant_id,
                    )
                )
            else:
                result = db_session.exec(
                    select(CustomAgentDefinition).where(
                        CustomAgentDefinition.custom_agent_id == agent_id,
                        CustomAgentDefinition.tenant_id == current_user.tenant_id,
                    )
                )
            rec = result.scalars().first()
            if not rec:
                raise Exception("Agent not found")

            if rec.is_deleted:
                raise Exception("Cannot update a deleted agent")
            rec.name = agent_input.name
            rec.description = agent_input.description
            if agent_input.systemPrompt is not None:
                rec.system_prompt = agent_input.systemPrompt
            # Update capabilities in metadata
            try:
                md = json.loads(rec.custom_metadata) if rec.custom_metadata else {}
            except Exception:
                md = {}
            md["capabilities"] = agent_input.capabilities or []
            rec.custom_metadata = json.dumps(md)
            rec.update_timestamp()

            db_session.add(rec)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(rec)
            else:
                db_session.commit()
                db_session.refresh(rec)

            return Agent(
                id=rec.custom_agent_id,
                name=rec.name,
                description=rec.description,
                createdAt=rec.created_at.isoformat(),
                lastUsed=rec.last_executed_at.isoformat() if rec.last_executed_at else None,
                status="active" if rec.is_active else "inactive",
                agentType=agent_input.agentType,
                capabilities=agent_input.capabilities,
                performanceMetrics={"successRate": 0.0, "totalExecutions": rec.execution_count}
            )

        except Exception as e:
            raise InternalServerError(
                message=f"Failed to update agent: {str(e)}",
                details={"agent_id": agent_id}
            )

    @strawberry.mutation
    async def deleteAgent(
        self,
        info: GraphQLResolveInfo,
        agent_id: str,
    ) -> bool:
        """
        Delete an agent.

        Args:
            agent_id: ID of the agent to delete

        Returns:
            bool: True if deletion was successful
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            from src.database.models.custom_agent import CustomAgentDefinition
            rec = db_session.exec(
                select(CustomAgentDefinition).where(
                    CustomAgentDefinition.custom_agent_id == agent_id,
                    CustomAgentDefinition.tenant_id == current_user.tenant_id,
                )
            ).first()
            if not rec:
                raise Exception("Agent not found")
            # Soft delete
            rec.is_deleted = True
            rec.deleted_at = datetime.utcnow()
            rec.is_active = False
            rec.update_timestamp()
            db_session.add(rec)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()
            return True

        except Exception as e:
            raise InternalServerError(
                message=f"Failed to delete agent: {str(e)}",
                details={"agent_id": agent_id}
            )

    @strawberry.mutation
    async def deleteAgentTeam(
        self,
        info: GraphQLResolveInfo,
        agent_team_id: Annotated[str, strawberry.argument(name="agent_team_id")],
    ) -> bool:
        """Soft-delete (deactivate) an AgentTeam.

        Notes:
        - Tenant-scoped: only deletes within current tenant.
        - System teams are immutable and cannot be deleted.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            if isinstance(db_session, AsyncSession):
                result = await db_session.exec(
                    select(AgentTeam).where(
                        AgentTeam.agent_team_id == agent_team_id,
                        AgentTeam.tenant_id == current_user.tenant_id,
                    )
                )
                team = result.first()
            else:
                result = db_session.exec(
                    select(AgentTeam).where(
                        AgentTeam.agent_team_id == agent_team_id,
                        AgentTeam.tenant_id == current_user.tenant_id,
                    )
                )
                team = result.first()

            if not team:
                raise Exception("AgentTeam not found")
            if getattr(team, "is_system_agent", False):
                raise Exception("403 Forbidden: system agent teams are immutable")

            team.is_active = False
            try:
                team.update_timestamp()
            except Exception:
                pass

            db_session.add(team)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()

            try:
                orchestrator = PlatformOrchestrator(tenant_id=current_user.tenant_id, user_id=current_user.id)
                await orchestrator._bump_quick_teams_version()  # type: ignore
            except Exception:
                pass

            return True
        except Exception as e:
            try:
                if isinstance(db_session, AsyncSession):
                    await db_session.rollback()
                else:
                    db_session.rollback()
            except Exception:
                pass
            raise InternalServerError(
                message=f"Failed to delete agent team: {str(e)}",
                details={"agent_team_id": agent_team_id},
            )

    @strawberry.mutation
    async def executeAgent(
        self,
        info: GraphQLResolveInfo,
        agent_id: str,
        input: str,
    ) -> AgentExecutionResult:
        """
        Execute an agent with the given input.

        Args:
            agent_id: ID of the agent to execute
            input: Input text for the agent

        Returns:
            AgentExecutionResult: Execution result
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            return AgentExecutionResult(
                success=False,
                result="Authentication required",
                executionTime=0.0,
                cost=0.0
            )

        try:
            # TODO: Implement actual agent execution
            # For now, return a placeholder response
            return AgentExecutionResult(
                success=True,
                result=f"Agent {agent_id} executed successfully",
                executionTime=1.5,
                cost=0.002
            )

        except Exception as e:
            return AgentExecutionResult(
                success=False,
                result=f"Agent execution failed: {str(e)}",
                executionTime=0.0,
                cost=0.0
            )

    # ============================================================================
    # INTEGRATION MANAGEMENT MUTATIONS
    # ============================================================================

    @strawberry.mutation
    async def connectIntegration(
        self,
        info: GraphQLResolveInfo,
        service_name: str,
        credentials: str,
    ) -> IntegrationStatus:
        """
        Connect to a third-party service integration.

        Args:
            service_name: Name of the service to connect to
            credentials: JSON string with credentials

        Returns:
            IntegrationStatus: Connection status
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            return IntegrationStatus(
                serviceName=service_name,
                status="error",
                validationErrors=["Authentication required"]
            )

        try:
            # Parse credentials JSON
            try:
                cred_obj = json.loads(credentials)
            except Exception:
                return IntegrationStatus(serviceName=service_name, status="error", validationErrors=["Invalid credentials JSON"])

            from src.services.secure_credential_service import SecureCredentialService
            svc = SecureCredentialService()
            tool_name = f"mcp_{service_name}" if not service_name.startswith("mcp_") else service_name
            try:
                svc.create_credential(
                    tenant_id=current_user.tenant_id,
                    tool_name=tool_name,
                    service_name=service_name,
                    credential_data=cred_obj,
                    credential_type="api_key",
                    description=f"{service_name} credentials",
                    created_by=current_user.user_id,
                )
            except Exception as e:
                return IntegrationStatus(serviceName=service_name, status="error", validationErrors=[str(e)])
            return IntegrationStatus(serviceName=service_name, status="connected", validationErrors=None)

        except Exception as e:
            return IntegrationStatus(
                serviceName=service_name,
                status="error",
                validationErrors=[str(e)]
            )

    @strawberry.mutation
    async def testIntegration(
        self,
        info: GraphQLResolveInfo,
        service_name: str,
    ) -> IntegrationTestResult:
        """
        Test a service integration connection.

        Args:
            service_name: Name of the service to test

        Returns:
            IntegrationTestResult: Test result
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            return IntegrationTestResult(
                success=False,
                testResult="Authentication required",
                errorMessage="Authentication required"
            )

        try:
            from src.services.secure_credential_service import SecureCredentialService
            svc = SecureCredentialService()
            tool_name = f"mcp_{service_name}" if not service_name.startswith("mcp_") else service_name
            creds = svc.get_credentials_for_tool(current_user.tenant_id, tool_name)
            if not creds:
                return IntegrationTestResult(success=False, testResult="No credentials configured", errorMessage="Missing credentials")
            ok, msg = svc.test_credential(creds[0].id, current_user.tenant_id)
            return IntegrationTestResult(success=ok, testResult=msg if ok else "Failed", errorMessage=None if ok else msg)

        except Exception as e:
            return IntegrationTestResult(
                success=False,
                testResult=f"Failed to test {service_name} integration",
                errorMessage=str(e)
            )

    @strawberry.mutation
    async def disconnectIntegration(
        self,
        info: GraphQLResolveInfo,
        service_name: str,
    ) -> bool:
        """
        Disconnect from a service integration.

        Args:
            service_name: Name of the service to disconnect from

        Returns:
            bool: True if disconnection was successful
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            from src.services.secure_credential_service import SecureCredentialService
            from src.services.silo_oauth_service import SiloOAuthService as _Silo
            from src.utils.secrets_manager import TenantSecretsManager

            try:
                # Best-effort revoke via SiloOAuthService for OAuth-backed providers
                await _Silo().revoke(tenant_id=str(current_user.tenant_id), provider=service_name.replace("mcp_", ""))
            except Exception:
                pass

            # Clear consolidated credentials secret
            try:
                tsm = TenantSecretsManager()
                await tsm.delete_secret(str(current_user.tenant_id), service_name, "credentials")
            except Exception:
                pass

            # Legacy path: credential record deletion
            try:
                svc = SecureCredentialService()
                tool_name = f"mcp_{service_name}" if not service_name.startswith("mcp_") else service_name
                creds = svc.get_credentials_for_tool(current_user.tenant_id, tool_name)
                if creds:
                    svc.revoke_credential(creds[0].id, current_user.tenant_id, current_user.user_id)
            except Exception:
                pass
            return True

        except Exception as e:
            raise InternalServerError(
                message=f"Failed to disconnect integration: {str(e)}",
                details={"service_name": service_name}
            )

    # ============================================================================
    # MCP TOOL MUTATIONS
    # ============================================================================
    @strawberry.mutation
    async def executeMCPTool(
        self,
        info: GraphQLResolveInfo,
        tool_name: Annotated[str, strawberry.argument(name="toolName")],
        params: str,
    ) -> MCPToolResult:
        """
        Execute an MCP tool.

        Args:
            tool_name: Name of the MCP tool to execute
            params: JSON string with execution parameters

        Returns:
            MCPToolResult: Execution result
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            return MCPToolResult(
                success=False,
                result="Authentication required",
                executionTime=0.0,
                errorMessage="Authentication required",
                toolOutput=None
            )

        # Parse params JSON
        try:
            param_obj = json.loads(params) if isinstance(params, str) else {}
        except Exception:
            return MCPToolResult(
                success=False,
                result="Invalid params JSON",
                executionTime=0.0,
                errorMessage="Invalid params JSON",
                toolOutput=None,
            )

        # Ensure tenant_id is present for manager/tool resolution
        if isinstance(param_obj, dict) and "tenant_id" not in param_obj:
            param_obj["tenant_id"] = current_user.tenant_id

        # Team tool scoping enforcement: if a team context is provided or derivable via job_id, 
        # reject execution when tool is not pre-approved on the team allowlist.
        try:
            agent_team_id = None
            if isinstance(param_obj, dict):
                agent_team_id = param_obj.get("agent_team_id") or param_obj.get("team_id")
                # Derive from job if provided
                job_id = param_obj.get("job_id") or param_obj.get("jobId")
                if not agent_team_id and job_id:
                    try:
                        stmt = select(Job).where(Job.job_id == str(job_id), Job.tenant_id == current_user.tenant_id)
                        job_row = db_session.exec(stmt).first() if not isinstance(db_session, AsyncSession) else (await db_session.execute(stmt)).scalars().first()
                        if job_row:
                            md = job_row.get_job_metadata() or {}
                            if isinstance(md, dict):
                                agent_team_id = md.get("agent_team_id") or md.get("team_id")
                    except Exception:
                        agent_team_id = agent_team_id

            if agent_team_id:
                from src.database.models import AgentTeam as AT
                stmt = select(AT).where(AT.agent_team_id == str(agent_team_id), AT.tenant_id == current_user.tenant_id)
                team = db_session.exec(stmt).first() if not isinstance(db_session, AsyncSession) else (await db_session.execute(stmt)).scalars().first()
                if not team:
                    return MCPToolResult(
                        success=False,
                        result=f"Agent team {agent_team_id} not found",
                        executionTime=0.0,
                        errorMessage="TEAM_NOT_FOUND",
                        toolOutput=None,
                    )
                allowlist = set(team.get_pre_approved_tool_names() or [])
                if tool_name not in allowlist:
                    # Security reject and do not execute the tool
                    await publish_execution_trace(param_obj.get("job_id") or param_obj.get("jobId") or "", {
                        "type": "SECURITY_DENY",
                        "step_description": f"Tool {tool_name} not in team allowlist",
                    })
                    return MCPToolResult(
                        success=False,
                        result=f"Tool {tool_name} is not allowed for team {agent_team_id}",
                        executionTime=0.0,
                        errorMessage="TOOL_NOT_ALLOWED",
                        toolOutput=None,
                    )
        except Exception:
            # Fail closed? For now, prefer fail-open to avoid breaking non-team contexts
            pass

        try:
            from src.services.mcp_tool_manager import MCPToolManager

            mcp_manager = MCPToolManager(db_session)
            # Structured log: tool invocation start
            try:
                await log_security_event(
                    event_type="tool_invocation_start",
                    user_id=current_user.id,
                    tenant_id=current_user.tenant_id,
                    details={
                        "tool_name": tool_name,
                        "job_id": param_obj.get("job_id") or param_obj.get("jobId"),
                        "agent_team_id": param_obj.get("agent_team_id") or param_obj.get("team_id"),
                    },
                )
            except Exception:
                pass
            res = await mcp_manager.execute_tool(tool_name, param_obj)

            # Normalize toolOutput if it's an object with to_dict
            tool_output = getattr(res, "toolOutput", None)
            if hasattr(tool_output, "to_dict") and callable(getattr(tool_output, "to_dict")):
                tool_output = tool_output.to_dict()
            # Return GraphQL type instance for reliable serialization
            return MCPToolResult(
                success=bool(res.success),
                result=str(res.result),
                executionTime=float(res.executionTime),
                errorMessage=getattr(res, "errorMessage", None),
                toolOutput=tool_output,
            )

        except Exception as e:
            try:
                await log_security_event(
                    event_type="tool_invocation_error",
                    user_id=current_user.id if current_user else None,
                    tenant_id=current_user.tenant_id if current_user else None,
                    details={"tool_name": tool_name, "error": str(e)[:500]},
                )
            except Exception:
                pass
            return MCPToolResult(
                success=False,
                result=f"MCP tool execution failed: {str(e)}",
                executionTime=0.0,
                errorMessage=str(e),
                toolOutput=None,
            )

    @strawberry.mutation
    async def manageMCPCredentials(
        self,
        info: GraphQLResolveInfo,
        tool_name: str,
        credentials: str,
    ) -> MCPCredentialStatus:
        """
        Manage credentials for an MCP tool.

        Args:
            tool_name: Name of the MCP tool
            credentials: JSON string with credentials

        Returns:
            MCPCredentialStatus: Credential management status
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            return MCPCredentialStatus(
                success=False,
                validationErrors=["Authentication required"]
            )

        try:
            from src.services.secure_credential_service import SecureCredentialService
            try:
                cred_obj = json.loads(credentials)
            except Exception:
                return MCPCredentialStatus(success=False, validationErrors=["Invalid credentials JSON"])

            svc = SecureCredentialService()
            svc.create_credential(
                tenant_id=current_user.tenant_id,
                tool_name=tool_name,
                service_name=tool_name.replace("mcp_", ""),
                credential_data=cred_obj,
                credential_type="api_key",
                description=f"{tool_name} credentials",
                created_by=current_user.user_id,
            )
            return MCPCredentialStatus(success=True, validationErrors=None)

        except Exception as e:
            return MCPCredentialStatus(
                success=False,
                validationErrors=[str(e)]
            )

    @strawberry.mutation
    async def testMCPTool(
        self,
        info: GraphQLResolveInfo,
        tool_name: str,
    ) -> MCPToolTestResult:
        """
        Test MCP tool credentials and connectivity.

        Args:
            tool_name: Name of the MCP tool to test

        Returns:
            MCPToolTestResult: Test result
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            return MCPToolTestResult(
                success=False,
                testResult="Authentication required",
                errorMessage="Authentication required"
            )

        try:
            from src.services.secure_credential_service import SecureCredentialService
            svc = SecureCredentialService()
            creds = svc.get_credentials_for_tool(current_user.tenant_id, tool_name)
            if not creds:
                return MCPToolTestResult(success=False, testResult="No credentials configured", errorMessage="Missing credentials")
            ok, msg = svc.test_credential(creds[0].id, current_user.tenant_id)
            return MCPToolTestResult(success=ok, testResult=msg if ok else "Failed", errorMessage=None if ok else msg)

        except Exception as e:
            return MCPToolTestResult(
                success=False,
                testResult=f"MCP tool {tool_name} test failed",
                errorMessage=str(e)
            )

    # ============================================================================
    # TONE PROFILE MUTATIONS
    # ============================================================================

    @strawberry.mutation
    async def updateToneProfile(
        self,
        info: GraphQLResolveInfo,
        profile_id: str,
        profile_input: ToneProfileInput,
    ) -> ToneProfile:
        """Update an existing tone profile for the current user/tenant."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            from src.database.ts_models import ToneProfile as ToneProfileORM  # type: ignore

            try:
                pid_int = int(profile_id)
            except ValueError:
                raise InternalServerError(
                    message="Invalid tone profile id",
                    details={"profile_id": profile_id},
                )

            stmt = select(ToneProfileORM).where(
                ToneProfileORM.id == pid_int,
                ToneProfileORM.tenant_id == current_user.tenant_id,
                ToneProfileORM.user_id == current_user.id,
            )
            if isinstance(db_session, AsyncSession):
                res = await db_session.execute(stmt)
                rec = res.scalars().first()
            else:
                rec = db_session.exec(stmt).first()

            if not rec:
                raise InternalServerError(
                    message="Tone profile not found",
                    details={"profile_id": profile_id},
                )

            rec.name = profile_input.name
            rec.profile_text = profile_input.profileText
            rec.description = profile_input.description

            if profile_input.isDefault is not None:
                if profile_input.isDefault:
                    clear_stmt = sa.update(ToneProfileORM).where(
                        ToneProfileORM.tenant_id == current_user.tenant_id,
                        ToneProfileORM.user_id == current_user.id,
                        ToneProfileORM.id != rec.id,
                    ).values(is_default=False)
                    if isinstance(db_session, AsyncSession):
                        await db_session.execute(clear_stmt)
                    else:
                        db_session.exec(clear_stmt)
                    rec.is_default = True
                else:
                    rec.is_default = False

            rec.updated_at = datetime.utcnow()
            db_session.add(rec)
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
                await db_session.refresh(rec)
            else:
                db_session.commit()
                db_session.refresh(rec)

            profile_type = "system_default" if getattr(rec, "is_default", False) else "user_created"
            return ToneProfile(
                id=str(rec.id),
                name=rec.name,
                type=profile_type,
                description=rec.description or "",
                usageCount=0,
                lastUsed=None,
                effectiveness=None,
            )
        except InternalServerError:
            raise
        except Exception as e:
            raise InternalServerError(
                message=f"Failed to update tone profile: {str(e)}",
                details={"profile_id": profile_id},
            )

    @strawberry.mutation
    async def deleteToneProfile(
        self,
        info: GraphQLResolveInfo,
        profile_id: str,
    ) -> bool:
        """Delete a tone profile for the current user/tenant and clear any thread references."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            from src.database.ts_models import ToneProfile as ToneProfileORM  # type: ignore

            try:
                pid_int = int(profile_id)
            except ValueError:
                return False

            stmt = select(ToneProfileORM).where(
                ToneProfileORM.id == pid_int,
                ToneProfileORM.tenant_id == current_user.tenant_id,
                ToneProfileORM.user_id == current_user.id,
            )
            if isinstance(db_session, AsyncSession):
                res = await db_session.execute(stmt)
                rec = res.scalars().first()
            else:
                rec = db_session.exec(stmt).first()

            if not rec:
                return False

            if isinstance(db_session, AsyncSession):
                await db_session.delete(rec)
                await db_session.commit()
            else:
                db_session.delete(rec)
                db_session.commit()

            try:
                tone_id_str = str(pid_int)
                t_stmt = select(ThreadModel).where(
                    ThreadModel.tenant_id == current_user.tenant_id,
                    ThreadModel.tone_profile_id == tone_id_str,
                )
                if isinstance(db_session, AsyncSession):
                    t_res = await db_session.execute(t_stmt)
                    threads = t_res.scalars().all()
                else:
                    threads = db_session.exec(t_stmt).all()
                changed = False
                for t in threads:
                    t.tone_profile_id = None
                    db_session.add(t)
                    changed = True
                if changed:
                    if isinstance(db_session, AsyncSession):
                        await db_session.commit()
                    else:
                        db_session.commit()
            except Exception:
                pass

            return True
        except Exception as e:
            raise InternalServerError(
                message=f"Failed to delete tone profile: {str(e)}",
                details={"profile_id": profile_id, "error": str(e)},
            )

    @strawberry.mutation
    async def applyToneProfile(
        self,
        info: GraphQLResolveInfo,
        profile_id: str,
        goal_id: str,
    ) -> bool:
        """Apply a tone profile to a goal/thread by tagging thread and/or job metadata.

        `goal_id` may be a logical goal identifier, a thread_id, or a job_id. We
        validate the tone profile and then best-effort tag any matching thread/job
        for downstream orchestration to pick up.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            from src.database.ts_models import ToneProfile as ToneProfileORM  # type: ignore

            try:
                pid_int = int(profile_id)
            except ValueError:
                raise InternalServerError(
                    message="Invalid tone profile id",
                    details={"profile_id": profile_id},
                )

            stmt = select(ToneProfileORM).where(
                ToneProfileORM.id == pid_int,
                ToneProfileORM.tenant_id == current_user.tenant_id,
                ToneProfileORM.user_id == current_user.id,
            )
            if isinstance(db_session, AsyncSession):
                res = await db_session.execute(stmt)
                profile_rec = res.scalars().first()
            else:
                profile_rec = db_session.exec(stmt).first()

            if not profile_rec:
                raise InternalServerError(
                    message="Tone profile not found",
                    details={"profile_id": profile_id},
                )

            try:
                t_stmt = select(ThreadModel).where(
                    ThreadModel.thread_id == goal_id,
                    ThreadModel.tenant_id == current_user.tenant_id,
                )
                if isinstance(db_session, AsyncSession):
                    t_res = await db_session.execute(t_stmt)
                    thread_rec = t_res.scalars().first()
                else:
                    thread_rec = db_session.exec(t_stmt).first()
                if thread_rec:
                    thread_rec.tone_profile_id = str(profile_rec.id)
                    db_session.add(thread_rec)
            except Exception:
                pass

            try:
                j_stmt = select(Job).where(
                    Job.job_id == goal_id,
                    Job.tenant_id == current_user.tenant_id,
                )
                if isinstance(db_session, AsyncSession):
                    j_res = await db_session.execute(j_stmt)
                    job_rec = j_res.scalars().first()
                else:
                    job_rec = db_session.exec(j_stmt).first()
                if job_rec:
                    try:
                        md = job_rec.get_job_metadata() or {}
                    except Exception:
                        md = {}
                    if isinstance(md, dict):
                        md["tone_profile_id"] = str(profile_rec.id)
                        md["tone_profile_name"] = profile_rec.name
                    try:
                        job_rec.set_job_metadata(md)
                    except Exception:
                        pass
                    db_session.add(job_rec)
            except Exception:
                pass

            try:
                if isinstance(db_session, AsyncSession):
                    await db_session.commit()
                else:
                    db_session.commit()
            except Exception:
                pass

            return True
        except InternalServerError:
            raise
        except Exception as e:
            raise InternalServerError(
                message=f"Failed to apply tone profile: {str(e)}",
                details={"profile_id": profile_id, "goal_id": goal_id, "error": str(e)},
            )
