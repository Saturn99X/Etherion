# src/etherion_ai/graphql_schema/queries.py
import strawberry
from typing import List, Optional, Annotated
import json
from strawberry.types import Info
import sqlalchemy as sa
from src.database.db import get_session
from src.database.models import Job
from sqlmodel import select
from src.database.models.threading import Thread as ThreadModel, ThreadMessage as MessageModel

from src.etherion_ai.graphql_schema.output_types import (
    ProjectType,
    ConversationType,
    Agent,
    AgentTeamType,
    Integration,
    MCPTool,
    ToneProfile,
    JobHistory,
    JobHistoryItem,
    JobHistoryPageInfo
)
from src.database.models import Project, Conversation, Job
from src.database.tenant_utils import get_tenant_aware_records, get_tenant_aware_record_by_id
from src.services.mcp_tool_manager import MCPToolManager
from src.middleware.authorization import (
    get_authorization_context,
    get_authorization_context_for_user,
    Permission,
)
from src.etherion_ai.graphql_schema.output_types import JobDetails, ThreadType, MessageType
from strawberry.scalars import JSON
# Avoid importing threading ORM models to prevent duplicate 'message' table definitions.
from src.services.content_repository_service import ContentRepositoryService
from typing import Optional
from src.core.redis import get_redis_client
from src.utils.secrets_manager import TenantSecretsManager
from sqlalchemy.ext.asyncio import AsyncSession
from src.etherion_ai.graphql_schema.auth_mutations import CurrentUserResponse

@strawberry.type
class RepositoryAssetType:
    assetId: str
    jobId: Optional[str]
    filename: str
    mimeType: str
    sizeBytes: int
    createdAt: str
    downloadUrl: Optional[str] = None
    previewBase64: Optional[str] = None

@strawberry.type
class Query:
    @strawberry.field
    def health_check(self) -> str:
        return "GraphQL server is operational."

    @strawberry.field
    def getCurrentUser(self, info: Info) -> CurrentUserResponse:
        """Get current authenticated user information."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")
        return CurrentUserResponse(
            id=current_user.id,
            user_id=current_user.user_id,
            created_at=current_user.created_at.isoformat()
        )

    @strawberry.field
    async def getToneProfiles(self, info: Info, user_id: int) -> List[ToneProfile]:
        """Return tone profiles for the current user in the current tenant."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        # For now, enforce that callers can only read their own profiles
        target_user_id = current_user.id

        try:
            from src.database.ts_models import ToneProfile as ToneProfileORM  # local import to avoid cycles

            stmt = select(ToneProfileORM).where(
                ToneProfileORM.tenant_id == current_user.tenant_id,
                ToneProfileORM.user_id == target_user_id,
            )
            if isinstance(db_session, AsyncSession):
                res = await db_session.execute(stmt)
                rows = res.scalars().all()
            else:
                rows = db_session.exec(stmt).all()

            out: List[ToneProfile] = []
            for rec in rows:
                profile_type = "system_default" if getattr(rec, "is_default", False) else "user_created"
                out.append(
                    ToneProfile(
                        id=str(rec.id),
                        name=rec.name,
                        type=profile_type,
                        description=rec.description or "",
                        usageCount=0,
                        lastUsed=None,
                        effectiveness=None,
                    )
                )
            return out
        except Exception as e:
            raise Exception(f"Failed to retrieve tone profiles: {str(e)}")

    @strawberry.field
    async def getUserSettings(self, info: Info) -> Optional[JSON]:
        """Return per-tenant user settings JSON bag; empty object when none."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            raise Exception("Not authenticated")
        try:
            # Raw SQL to avoid ORM model for a simple key/value bag
            query = "SELECT settings_json FROM user_settings WHERE tenant_id = :t AND user_id = :u LIMIT 1"
            params = {"t": current_user.tenant_id, "u": current_user.id}
            if isinstance(db_session, AsyncSession):
                result = await db_session.execute(sa.text(query), params)  # type: ignore
                row = result.first()
            else:
                result = db_session.execute(sa.text(query), params)  # type: ignore
                row = result.first()
            if not row or not row[0]:
                return {}
            try:
                return json.loads(row[0])
            except Exception:
                return {}
        except Exception:
            return {}
        
    @strawberry.field
    async def getArchivedTraceSummary(self, info: Info, job_id: str) -> Optional[str]:
        """
        Retrieve archived trace summary for a job (final output + final thought) from DB.
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")

        # Use the async db_session from auth_context (already scoped to tenant)
        db_session = auth_context["db_session"]
        # SECURITY: filter by BOTH tenant_id AND user_id for user-level isolation
        stmt = select(Job).where(
            Job.job_id == job_id,
            Job.tenant_id == current_user.tenant_id,
            Job.user_id == current_user.id  # CRITICAL: user-level isolation
        )
        if isinstance(db_session, AsyncSession):
            result = await db_session.execute(stmt)
            job = result.scalars().first()
        else:
            job = db_session.exec(stmt).first()
        if not job:
            return None
        try:
            data = job.get_output_data() or {}
            final_output = data.get("final_output")
            final_thought = data.get("final_thought")
            if final_output or final_thought:
                return (final_output or "") + ("\n\nFinal Thought: " + final_thought if final_thought else "")
        except Exception:
            pass
        return None

    @strawberry.field
    async def getProjectsByTenant(self, info: Info) -> List[ProjectType]:
        """
        Get all projects for the current tenant.
        
        Returns:
            List[ProjectType]: List of projects belonging to the current tenant
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        
        if not current_user:
            raise Exception("Not authenticated")
            
        # Get tenant-aware projects
        tenant_projects = get_tenant_aware_records(db_session, current_user.tenant_id, Project)
        
        # Convert to GraphQL types
        project_types = [
            ProjectType(
                id=project.id,
                name=project.name,
                description=project.description,
                createdAt=project.created_at.isoformat() if project.created_at else None,
                userId=project.user_id
            )
            for project in tenant_projects
        ]
        
        return project_types
        
    @strawberry.field
    async def getConversationsByProject(self, info: Info, project_id: int) -> List[ConversationType]:
        """
        Get all conversations for a specific project.
        
        Args:
            project_id: The ID of the project to get conversations for
            
        Returns:
            List[ConversationType]: List of conversations belonging to the specified project
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        
        if not current_user:
            raise Exception("Not authenticated")
            
        # Verify that the project belongs to the current tenant
        project = get_tenant_aware_record_by_id(db_session, current_user.tenant_id, Project, project_id)
        if not project:
            raise Exception("Project not found or access denied.")
            
        # Get conversations for this project
        statement = select(Conversation).where(Conversation.project_id == project_id)
        project_conversations = db_session.exec(statement).all()
        
        # Convert to GraphQL types
        conversation_types = [
            ConversationType(
                id=conversation.id,
                title=conversation.title,
                createdAt=conversation.created_at.isoformat() if conversation.created_at else None,
                projectId=conversation.project_id
            )
            for conversation in project_conversations
        ]
        
        return conversation_types

    # ========================================================================
    # THREADS AND MESSAGES
    # ========================================================================

    @strawberry.field
    async def getThread(self, info: Info, thread_id: str) -> Optional[ThreadType]:
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            raise Exception("Not authenticated")
        stmt = select(ThreadModel).where(ThreadModel.thread_id == thread_id, ThreadModel.tenant_id == current_user.tenant_id)
        rec = db_session.exec(stmt).first() if not isinstance(db_session, AsyncSession) else (await db_session.execute(stmt)).scalars().first()
        if not rec:
            return None
        return ThreadType(
            threadId=rec.thread_id,
            title=getattr(rec, 'title', None),
            teamId=getattr(rec, 'team_id', None),
            provider=getattr(rec, 'provider', None),
            model=getattr(rec, 'model', None),
            createdAt=(rec.created_at.isoformat() if getattr(rec, 'created_at', None) else ""),
            lastActivityAt=(rec.last_activity_at.isoformat() if getattr(rec, 'last_activity_at', None) else None),
        )

    @strawberry.field
    async def listThreads(self, info: Info, limit: int = 50, offset: int = 0) -> List[ThreadType]:
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            raise Exception("Not authenticated")
        stmt = select(ThreadModel).where(ThreadModel.tenant_id == current_user.tenant_id).offset(offset).limit(limit)
        rows = db_session.exec(stmt).all() if not isinstance(db_session, AsyncSession) else (await db_session.execute(stmt)).scalars().all()
        out: List[ThreadType] = []
        for rec in rows:
            out.append(ThreadType(
                threadId=rec.thread_id,
                title=getattr(rec, 'title', None),
                teamId=getattr(rec, 'team_id', None),
                provider=getattr(rec, 'provider', None),
                model=getattr(rec, 'model', None),
                createdAt=(rec.created_at.isoformat() if getattr(rec, 'created_at', None) else ""),
                lastActivityAt=(rec.last_activity_at.isoformat() if getattr(rec, 'last_activity_at', None) else None),
            ))
        return out

    @strawberry.field
    async def listMessages(self, info: Info, thread_id: str, branch_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[MessageType]:
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]
        if not current_user:
            raise Exception("Not authenticated")

        thread_stmt = select(ThreadModel).where(
            ThreadModel.thread_id == thread_id,
            ThreadModel.tenant_id == current_user.tenant_id,
        )
        if isinstance(db_session, AsyncSession):
            thread_res = await db_session.execute(thread_stmt)
            thread_rec = thread_res.scalars().first()
        else:
            thread_rec = db_session.exec(thread_stmt).first()
        if not thread_rec:
            return []

        stmt = select(MessageModel).where(MessageModel.thread_id == thread_id)
        if branch_id:
            stmt = stmt.where(MessageModel.branch_id == branch_id)
        stmt = stmt.order_by(MessageModel.created_at.asc()).offset(offset).limit(limit)
        rows = db_session.exec(stmt).all() if not isinstance(db_session, AsyncSession) else (await db_session.execute(stmt)).scalars().all()
        out: List[MessageType] = []
        for m in rows:
            out.append(MessageType(
                messageId=m.message_id,
                threadId=m.thread_id,
                role=m.role,
                content=m.content,
                parentId=getattr(m, 'parent_id', None),
                branchId=getattr(m, 'branch_id', None),
                createdAt=(m.created_at.isoformat() if getattr(m, 'created_at', None) else ""),
            ))
        return out

    @strawberry.field
    async def listRepositoryAssets(
        self,
        info: Info,
        limit: int = 50,
        job_id: Annotated[Optional[str], strawberry.argument(name="jobId")] = None,
        include_download: bool = True,
    ) -> List[RepositoryAssetType]:
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")

        # Dev/LES safety: If GCP project is not configured locally, degrade gracefully
        try:
            import os as _os
            if not (_os.getenv("GOOGLE_CLOUD_PROJECT") or _os.getenv("GCP_PROJECT_ID")):
                return []
            svc = ContentRepositoryService(tenant_id=str(current_user.tenant_id))
            # Enforce AI-origin list via ContentRepositoryService
            assets, next_token = [], None
            try:
                # list via BigQuery directly with origin='ai' using the service
                # reuse underlying query through get_access loop (we need metadata fields anyway)
                # Fetch limited set: we will call get_access per asset for download/base64
                from google.cloud import bigquery as _bq
                # fallback: use svc.bq client to query similar to list_assets; but ContentRepositoryService already
                # provides list_assets with AI origin, so simply call repository_service for listing equivalent
            except Exception:
                pass
            # Use ContentRepositoryService.list_assets for AI-origin assets
            try:
                from src.services.repository_service import RepositoryService as _Repo
                _repo = _Repo(tenant_id=current_user.tenant_id)
                assets = _repo.list_assets(limit=limit, job_id=job_id, origin="ai")
            except Exception:
                assets = []

            out: List[RepositoryAssetType] = []
            for a in assets:
                dl_url = None
                preview_b64 = None
                if include_download:
                    try:
                        access = svc.get_access(a.asset_id)
                        if access:
                            if access.get("base64"):
                                preview_b64 = access["base64"]
                            elif access.get("url"):
                                dl_url = access["url"]
                    except Exception:
                        dl_url = None
                        preview_b64 = None
                out.append(
                    RepositoryAssetType(
                        assetId=a.asset_id,
                        jobId=a.job_id,
                        filename=a.filename,
                        mimeType=a.mime_type,
                        sizeBytes=a.size_bytes,
                        createdAt=a.created_at,
                        downloadUrl=dl_url,
                        previewBase64=preview_b64,
                    )
                )
            return out
        except Exception:
            return []

    # ============================================================================
    # AGENT TEAM QUERIES
    # ============================================================================

    @strawberry.field
    async def listAgentTeams(self, info: Info, limit: int = 50, offset: int = 0) -> List[AgentTeamType]:
        """
        List agent teams for the current tenant.
        """
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        from sqlmodel import select
        from src.database.models import AgentTeam as AT

        stmt = select(AT).where(AT.tenant_id == current_user.tenant_id).offset(offset).limit(limit)
        rows = db_session.exec(stmt).all()

        out: List[AgentTeamType] = []
        for rec in rows:
            out.append(
                AgentTeamType(
                    id=rec.agent_team_id,
                    name=rec.name,
                    description=rec.description,
                    createdAt=rec.created_at.isoformat() if hasattr(rec, 'created_at') and rec.created_at else "",
                    lastUpdatedAt=rec.last_updated_at.isoformat() if rec.last_updated_at else "",
                    isActive=rec.is_active,
                    isSystemTeam=rec.is_system_agent,
                    version=rec.version,
                    customAgentIDs=rec.get_custom_agent_ids(),
                    preApprovedToolNames=rec.get_pre_approved_tool_names(),
                )
            )
        return out

    @strawberry.field
    async def getVendorQuotaRemaining(self, info: Info, vendor: str) -> int:
        """Return remaining daily quota for a vendor for the current tenant."""
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        if not current_user:
            raise Exception("Not authenticated")
        tenant_id = current_user.tenant_id
        import datetime as _dt
        date_str = _dt.datetime.utcnow().strftime("%Y%m%d")
        key = f"quota:{tenant_id}:{vendor.lower()}:{date_str}"
        # Match defaults used in API
        from src.etherion_ai.app import QUOTA_DEFAULTS
        limit = QUOTA_DEFAULTS.get(vendor.lower(), 2000)
        redis = get_redis_client()
        current = int(await redis.get(key, 0) or 0)
        remaining = max(0, int(limit - current))
        return remaining

    # ============================================================================
    # AGENT MANAGEMENT QUERIES
    # ============================================================================

    @strawberry.field
    async def getAgents(self, info: Info, tenant_id: int, limit: int = 50, offset: int = 0, include_deleted: bool = False) -> List[Agent]:
        """
        Get all agents for a specific tenant.

        Args:
            tenant_id: The ID of the tenant to get agents for

        Returns:
            List[Agent]: List of agents belonging to the specified tenant
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        # Authorization check - ensure user has permission to view agents
        try:
            auth_context_obj = await get_authorization_context_for_user(
                user_id=current_user.user_id,
                tenant_id=current_user.tenant_id,
                db_session=db_session,
            )

            if not auth_context_obj.has_permission(Permission.MANAGE_AGENTS):
                raise Exception("Insufficient permissions to view agents")
        except Exception as e:
            raise Exception(f"Authorization check failed: {str(e)}")

        from sqlmodel import select
        from src.database.models.custom_agent import CustomAgentDefinition
        # Fetch tenant-scoped agents with pagination and optional soft-delete filter
        stmt = select(CustomAgentDefinition).where(CustomAgentDefinition.tenant_id == tenant_id)
        if not include_deleted:
            stmt = stmt.where(CustomAgentDefinition.is_deleted == False)  # noqa: E712
        stmt = stmt.offset(offset).limit(limit)
        rows = db_session.exec(stmt).all()
        out: List[Agent] = []
        for rec in rows:
            try:
                md = rec.get_custom_metadata() or {}
                caps = md.get("capabilities", [])
            except Exception:
                caps = []
            out.append(
                Agent(
                    id=rec.custom_agent_id,
                    name=rec.name,
                    description=rec.description,
                    createdAt=rec.created_at.isoformat() if rec.created_at else "",
                    lastUsed=rec.last_executed_at.isoformat() if rec.last_executed_at else None,
                    status=("inactive" if rec.is_deleted else ("active" if rec.is_active else "inactive")),
                    agentType="custom",
                    capabilities=caps,
                    performanceMetrics={"totalExecutions": rec.execution_count},
                )
            )
        return out

    # ============================================================================
    # INTEGRATION MANAGEMENT QUERIES
    # ============================================================================

    @strawberry.field
    async def getIntegrations(self, info: Info, tenant_id: int) -> List[Integration]:
        """
        Get all integrations for a specific tenant.

        Args:
            tenant_id: The ID of the tenant to get integrations for

        Returns:
            List[Integration]: List of integrations for the specified tenant
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        # Map available MCP tools to Integration items and mark status via stored credentials
        try:
            mcp_manager = MCPToolManager(db_session)
            tools = await mcp_manager.get_available_tools()
        except Exception as e:
            raise Exception(f"Failed to enumerate integrations: {str(e)}")

        tsm = TenantSecretsManager()
        tenant_str = str(current_user.tenant_id)
        out: List[Integration] = []

        for t in tools:
            connected = False
            last_connected: Optional[str] = None
            # Prefer a consolidated 'credentials' secret; fallback to first required credential key
            try:
                val = await tsm.get_secret(tenant_str, t.name, "credentials")
                if val and str(val).strip() not in ("", "null", "{}"):
                    connected = True
            except Exception:
                connected = connected or False

            if not connected:
                req = getattr(t, "required_credentials", None) or []
                for key in req:
                    try:
                        v = await tsm.get_secret(tenant_str, t.name, str(key))
                        if v and str(v).strip() != "":
                            connected = True
                            break
                    except Exception:
                        continue

            status = "connected" if connected else "disconnected"
            out.append(
                Integration(
                    serviceName=t.name,
                    status=status,
                    lastConnected=last_connected,
                    errorMessage=None,
                    capabilities=getattr(t, "capabilities", []) or [],
                )
            )

        return out

    # ============================================================================
    # MCP TOOL QUERIES
    # ============================================================================

    @strawberry.field
    async def getAvailableMCPTools(self, info: Info) -> List[MCPTool]:
        """
        Get all available MCP tools.

        Returns:
            List[MCPTool]: List of all available MCP tools
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Initialize MCP Tool Manager
            mcp_manager = MCPToolManager(db_session)

            # Get all available MCP tools
            available_tools = await mcp_manager.get_available_tools()

            # Convert to GraphQL types
            mcp_tools = [
                MCPTool(
                    name=tool.name,
                    description=tool.description,
                    category=tool.category,
                    requiredCredentials=tool.required_credentials,
                    capabilities=tool.capabilities,
                    status=tool.status
                )
                for tool in available_tools
            ]

            return mcp_tools

        except Exception as e:
            raise Exception(f"Failed to retrieve MCP tools: {str(e)}")

    @strawberry.field
    async def getJobHistory(
        self,
        info: Info,
        limit: Optional[int] = 50,
        offset: Optional[int] = 0,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> JobHistory:
        """
        Get paginated job history with optional filtering.

        Args:
            limit: Maximum number of jobs to return (default: 50)
            offset: Number of jobs to skip for pagination (default: 0)
            status: Filter by job status (optional)
            date_from: Start date for filtering (ISO format, optional)
            date_to: End date for filtering (ISO format, optional)

        Returns:
            JobHistory: Paginated job history results
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Build query with filters - SECURITY: filter by BOTH tenant_id AND user_id
            # to ensure users can only see their own jobs, not all jobs in the tenant
            query = select(Job).where(
                Job.tenant_id == current_user.tenant_id,
                Job.user_id == current_user.id  # CRITICAL: user-level isolation
            )

            if status:
                query = query.where(Job.status == status)

            if date_from:
                from datetime import datetime
                date_from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                query = query.where(Job.created_at >= date_from_dt)

            if date_to:
                from datetime import datetime
                date_to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                query = query.where(Job.created_at <= date_to_dt)

            # Get total count
            if isinstance(db_session, AsyncSession):
                result_all = await db_session.execute(query)
                all_rows = result_all.scalars().all()
                total_count = len(all_rows)
                # Apply pagination
                paged_query = query.offset(offset).limit(limit)
                result_paged = await db_session.execute(paged_query)
                jobs = result_paged.scalars().all()
            else:
                total_count = len(db_session.exec(query).all())
                # Apply pagination
                query = query.offset(offset).limit(limit)
                jobs = db_session.exec(query).all()

            # Convert to GraphQL types
            job_items = []
            for job in jobs:
                # Calculate duration if job is completed
                duration = "-"
                if job.created_at and hasattr(job, 'completed_at') and job.completed_at:
                    duration_seconds = (job.completed_at - job.created_at).total_seconds()
                    hours = int(duration_seconds // 3600)
                    minutes = int((duration_seconds % 3600) // 60)
                    duration = f"{hours}h {minutes}m"

                # Get output data for cost and metrics
                output_data = {}
                try:
                    output_data = job.get_output_data() or {}
                except:
                    pass

                md = None
                try:
                    md = job.get_job_metadata() or {}
                except Exception:
                    md = {}
                job_items.append(JobHistoryItem(
                    id=job.job_id,
                    goal=job.get_input_data().get('goal', 'Unknown goal') if job.get_input_data() else 'Unknown goal',
                    status=job.status.value,
                    createdAt=job.created_at.isoformat() if job.created_at else "",
                    completedAt=job.completed_at.isoformat() if hasattr(job, 'completed_at') and job.completed_at else None,
                    duration=duration,
                    totalCost=f"${output_data.get('total_cost', 0):.2f}",
                    modelUsed=output_data.get('model_used'),
                    tokenCount=output_data.get('token_count'),
                    successRate=output_data.get('success_rate'),
                    threadId=(md.get('thread_id') if isinstance(md, dict) else None),
                ))

            # Determine pagination info
            has_next_page = (offset + limit) < total_count
            has_previous_page = offset > 0

            return JobHistory(
                jobs=job_items,
                totalCount=total_count,
                pageInfo=JobHistoryPageInfo(
                    hasNextPage=has_next_page,
                    hasPreviousPage=has_previous_page
                )
            )

        except Exception as e:
            raise Exception(f"Failed to retrieve job history: {str(e)}")

    @strawberry.field
    async def getJobDetails(self, info: Info, job_id: str) -> Optional[JobDetails]:
        """
        Get detailed information about a specific job.

        Args:
            job_id: The ID of the job to get details for

        Returns:
            JobDetails: Detailed job information or None if not found
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        db_session = auth_context["db_session"]

        if not current_user:
            raise Exception("Not authenticated")

        try:
            # Find the job - SECURITY: filter by BOTH tenant_id AND user_id
            job = db_session.exec(
                select(Job).where(
                    Job.job_id == job_id,
                    Job.tenant_id == current_user.tenant_id,
                    Job.user_id == current_user.id  # CRITICAL: user-level isolation
                )
            ).first()

            if not job:
                return None

            # TODO: Implement execution trace retrieval
            # For now, return basic job information
            md = None
            try:
                md = job.get_job_metadata() or {}
            except Exception:
                md = {}
            return JobDetails(
                job_id=job.job_id,
                status=job.status.value,
                job_type=job.job_type,
                created_at=job.created_at.isoformat() if job.created_at else "",
                started_at=job.started_at.isoformat() if hasattr(job, 'started_at') and job.started_at else None,
                completed_at=job.completed_at.isoformat() if hasattr(job, 'completed_at') and job.completed_at else None,
                input_data=job.get_input_data(),
                output_data=job.get_output_data(),
                error_message=None,  # TODO: Extract from job data
                execution_steps=None,  # TODO: Implement execution steps
                threadId=(md.get('thread_id') if isinstance(md, dict) else None),
            )

        except Exception as e:
            raise Exception(f"Failed to retrieve job details: {str(e)}")