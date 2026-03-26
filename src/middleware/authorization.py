# src/middleware/authorization.py
"""
Comprehensive authorization middleware for tenant isolation and role-based access control.
Implements proper authorization checks for all endpoints with tenant isolation validation.
"""

import logging
from typing import Optional, Dict, Any, List, Union
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, Tenant, Project, Conversation, Job
from src.database.db import get_session
from src.auth.service import get_current_user, get_current_user_with_tenant
from src.core.security.audit_logger import log_authorization_failure, log_data_access

logger = logging.getLogger(__name__)

# Security scheme for token validation
security = HTTPBearer()


class Permission(Enum):
    """Available permissions in the system."""
    READ_PROJECT = "read_project"
    WRITE_PROJECT = "write_project"
    DELETE_PROJECT = "delete_project"
    READ_CONVERSATION = "read_conversation"
    WRITE_CONVERSATION = "write_conversation"
    DELETE_CONVERSATION = "delete_conversation"
    EXECUTE_GOAL = "execute_goal"
    READ_JOB = "read_job"
    MANAGE_TENANT = "manage_tenant"
    MANAGE_USERS = "manage_users"
    READ_AUDIT_LOGS = "read_audit_logs"
    MANAGE_AGENTS = "manage_agents"
    MANAGE_INTEGRATIONS = "manage_integrations"


class Role(Enum):
    """User roles in the system."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"
    GUEST = "guest"


# Role-based permissions mapping
ROLE_PERMISSIONS = {
    Role.ADMIN: [
        Permission.READ_PROJECT,
        Permission.WRITE_PROJECT,
        Permission.DELETE_PROJECT,
        Permission.READ_CONVERSATION,
        Permission.WRITE_CONVERSATION,
        Permission.DELETE_CONVERSATION,
        Permission.EXECUTE_GOAL,
        Permission.READ_JOB,
        Permission.MANAGE_TENANT,
        Permission.MANAGE_USERS,
        Permission.READ_AUDIT_LOGS,
        Permission.MANAGE_AGENTS,
        Permission.MANAGE_INTEGRATIONS,
    ],
    Role.USER: [
        Permission.READ_PROJECT,
        Permission.WRITE_PROJECT,
        Permission.READ_CONVERSATION,
        Permission.WRITE_CONVERSATION,
        Permission.EXECUTE_GOAL,
        Permission.READ_JOB,
        Permission.MANAGE_AGENTS,
    ],
    Role.VIEWER: [
        Permission.READ_PROJECT,
        Permission.READ_CONVERSATION,
        Permission.READ_JOB,
    ],
    Role.GUEST: [
        Permission.READ_PROJECT,
    ]
}


class AuthorizationContext:
    """Context object containing authorization information."""
    
    def __init__(self, user: User, tenant: Tenant, role: Role = Role.USER):
        self.user = user
        self.tenant = tenant
        self.role = role
        self.permissions = set(ROLE_PERMISSIONS.get(role, []))
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if the user has a specific permission."""
        return permission in self.permissions
    
    def has_any_permission(self, permissions: List[Permission]) -> bool:
        """Check if the user has any of the specified permissions."""
        return any(permission in self.permissions for permission in permissions)
    
    def has_all_permissions(self, permissions: List[Permission]) -> bool:
        """Check if the user has all of the specified permissions."""
        return all(permission in self.permissions for permission in permissions)


async def get_authorization_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session)
) -> AuthorizationContext:
    """
    Get authorization context for the current user.
    
    Args:
        credentials: HTTP Authorization header credentials
        session: Database session
        
    Returns:
        AuthorizationContext: Authorization context with user, tenant, and permissions
        
    Raises:
        HTTPException: If authentication or authorization fails
    """
    try:
        # Get current user and tenant
        user, tenant = get_current_user_with_tenant(credentials, session)
        
        # Determine user role (for now, default to USER - in production, this would come from the database)
        role = Role.USER
        
        # Create authorization context
        auth_context = AuthorizationContext(user, tenant, role)
        
        return auth_context
        
    except Exception as e:
        logger.error(f"Authorization context creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not create authorization context",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_authorization_context_for_user(
    user_id: str,
    tenant_id: Optional[int],
    db_session: Union[Session, AsyncSession]
) -> AuthorizationContext:
    """Construct an `AuthorizationContext` from explicit user and tenant identifiers."""

    if db_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization context requires a database session",
        )

    try:
        if isinstance(db_session, AsyncSession):
            user_result = await db_session.execute(select(User).where(User.user_id == user_id))
            user = user_result.scalars().first()

            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

            effective_tenant_id = tenant_id or user.tenant_id
            tenant_result = await db_session.execute(select(Tenant).where(Tenant.id == effective_tenant_id))
            tenant = tenant_result.scalars().first()
        else:
            user = db_session.exec(select(User).where(User.user_id == user_id)).first()
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

            effective_tenant_id = tenant_id or user.tenant_id
            tenant = db_session.exec(select(Tenant).where(Tenant.id == effective_tenant_id)).first()

        if tenant is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not found")

        role = Role.USER
        return AuthorizationContext(user=user, tenant=tenant, role=role)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Authorization context creation failed for user {user_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not create authorization context",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_permission(permission: Permission):
    """
    Decorator to require a specific permission.
    
    Args:
        permission: Required permission
        
    Returns:
        Decorator function
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract authorization context from kwargs
            auth_context = None
            for key, value in kwargs.items():
                if isinstance(value, AuthorizationContext):
                    auth_context = value
                    break
            
            if not auth_context:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authorization context not found"
                )
            
            # Check permission
            if not auth_context.has_permission(permission):
                await log_authorization_failure(
                    user_id=auth_context.user.user_id,
                    tenant_id=auth_context.tenant.id,
                    ip_address="unknown",  # Would be extracted from request
                    user_agent="unknown",  # Would be extracted from request
                    endpoint=func.__name__,
                    method="POST",  # Would be extracted from request
                    reason=f"Missing permission: {permission.value}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value} required"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(permissions: List[Permission]):
    """
    Decorator to require any of the specified permissions.
    
    Args:
        permissions: List of required permissions (user needs at least one)
        
    Returns:
        Decorator function
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract authorization context from kwargs
            auth_context = None
            for key, value in kwargs.items():
                if isinstance(value, AuthorizationContext):
                    auth_context = value
                    break
            
            if not auth_context:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authorization context not found"
                )
            
            # Check permissions
            if not auth_context.has_any_permission(permissions):
                await log_authorization_failure(
                    user_id=auth_context.user.user_id,
                    tenant_id=auth_context.tenant.id,
                    ip_address="unknown",
                    user_agent="unknown",
                    endpoint=func.__name__,
                    method="POST",
                    reason=f"Missing any of permissions: {[p.value for p in permissions]}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: one of {[p.value for p in permissions]} required"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


async def validate_tenant_access(
    auth_context: AuthorizationContext,
    resource_tenant_id: int,
    resource_type: str = "resource"
) -> bool:
    """
    Validate that the user has access to a resource within their tenant.
    
    Args:
        auth_context: Authorization context
        resource_tenant_id: Tenant ID of the resource
        resource_type: Type of resource for logging
        
    Returns:
        bool: True if access is allowed
        
    Raises:
        HTTPException: If access is denied
    """
    if auth_context.tenant.id != resource_tenant_id:
        await log_authorization_failure(
            user_id=auth_context.user.user_id,
            tenant_id=auth_context.tenant.id,
            ip_address="unknown",
            user_agent="unknown",
            endpoint=f"access_{resource_type}",
            method="GET",
            reason=f"Cross-tenant access attempt to tenant {resource_tenant_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {resource_type} belongs to different tenant"
        )
    
    return True


async def validate_project_access(
    auth_context: AuthorizationContext,
    project_id: int,
    session: Session,
    permission: Permission = Permission.READ_PROJECT
) -> Project:
    """
    Validate that the user has access to a specific project.
    
    Args:
        auth_context: Authorization context
        project_id: ID of the project
        session: Database session
        permission: Required permission
        
    Returns:
        Project: The project if access is allowed
        
    Raises:
        HTTPException: If access is denied or project not found
    """
    # Check permission
    if not auth_context.has_permission(permission):
        await log_authorization_failure(
            user_id=auth_context.user.user_id,
            tenant_id=auth_context.tenant.id,
            ip_address="unknown",
            user_agent="unknown",
            endpoint=f"access_project_{project_id}",
            method="GET",
            reason=f"Missing permission: {permission.value}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission.value} required"
        )
    
    # Get project and validate tenant access
    statement = select(Project).where(Project.id == project_id)
    project = session.exec(statement).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Validate tenant access
    await validate_tenant_access(auth_context, project.tenant_id, "project")
    
    # Log data access
    await log_data_access(
        user_id=auth_context.user.user_id,
        tenant_id=auth_context.tenant.id,
        ip_address="unknown",
        user_agent="unknown",
        endpoint=f"access_project_{project_id}",
        method="GET",
        data_type="project",
        operation="read"
    )
    
    return project


async def validate_conversation_access(
    auth_context: AuthorizationContext,
    conversation_id: int,
    session: Session,
    permission: Permission = Permission.READ_CONVERSATION
) -> Conversation:
    """
    Validate that the user has access to a specific conversation.
    
    Args:
        auth_context: Authorization context
        conversation_id: ID of the conversation
        session: Database session
        permission: Required permission
        
    Returns:
        Conversation: The conversation if access is allowed
        
    Raises:
        HTTPException: If access is denied or conversation not found
    """
    # Check permission
    if not auth_context.has_permission(permission):
        await log_authorization_failure(
            user_id=auth_context.user.user_id,
            tenant_id=auth_context.tenant.id,
            ip_address="unknown",
            user_agent="unknown",
            endpoint=f"access_conversation_{conversation_id}",
            method="GET",
            reason=f"Missing permission: {permission.value}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission.value} required"
        )
    
    # Get conversation and validate tenant access
    statement = select(Conversation).where(Conversation.id == conversation_id)
    conversation = session.exec(statement).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Validate tenant access
    await validate_tenant_access(auth_context, conversation.tenant_id, "conversation")
    
    # Log data access
    await log_data_access(
        user_id=auth_context.user.user_id,
        tenant_id=auth_context.tenant.id,
        ip_address="unknown",
        user_agent="unknown",
        endpoint=f"access_conversation_{conversation_id}",
        method="GET",
        data_type="conversation",
        operation="read"
    )
    
    return conversation


async def validate_job_access(
    auth_context: AuthorizationContext,
    job_id: str,
    session: Session,
    permission: Permission = Permission.READ_JOB
) -> Job:
    """
    Validate that the user has access to a specific job.
    
    Args:
        auth_context: Authorization context
        job_id: ID of the job
        session: Database session
        permission: Required permission
        
    Returns:
        Job: The job if access is allowed
        
    Raises:
        HTTPException: If access is denied or job not found
    """
    # Check permission
    if not auth_context.has_permission(permission):
        await log_authorization_failure(
            user_id=auth_context.user.user_id,
            tenant_id=auth_context.tenant.id,
            ip_address="unknown",
            user_agent="unknown",
            endpoint=f"access_job_{job_id}",
            method="GET",
            reason=f"Missing permission: {permission.value}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission.value} required"
        )
    
    # Get job and validate tenant access
    statement = select(Job).where(Job.job_id == job_id)
    job = session.exec(statement).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    # Validate tenant access
    await validate_tenant_access(auth_context, job.tenant_id, "job")
    
    # Log data access
    await log_data_access(
        user_id=auth_context.user.user_id,
        tenant_id=auth_context.tenant.id,
        ip_address="unknown",
        user_agent="unknown",
        endpoint=f"access_job_{job_id}",
        method="GET",
        data_type="job",
        operation="read"
    )
    
    return job


async def validate_user_owns_resource(
    auth_context: AuthorizationContext,
    resource_user_id: int,
    resource_type: str = "resource"
) -> bool:
    """
    Validate that the user owns a specific resource.
    
    Args:
        auth_context: Authorization context
        resource_user_id: User ID of the resource owner
        resource_type: Type of resource for logging
        
    Returns:
        bool: True if user owns the resource
        
    Raises:
        HTTPException: If user doesn't own the resource
    """
    if auth_context.user.id != resource_user_id:
        await log_authorization_failure(
            user_id=auth_context.user.user_id,
            tenant_id=auth_context.tenant.id,
            ip_address="unknown",
            user_agent="unknown",
            endpoint=f"access_{resource_type}",
            method="GET",
            reason=f"User {auth_context.user.id} attempted to access {resource_type} owned by user {resource_user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {resource_type} belongs to different user"
        )
    
    return True


# Middleware for automatic authorization checks
async def authorization_middleware(request: Request, call_next):
    """
    Middleware to automatically check authorization for protected endpoints.
    """
    # Skip authorization for public endpoints
    public_endpoints = ["/health", "/docs", "/openapi.json", "/auth/login", "/auth/oauth"]
    if any(request.url.path.startswith(endpoint) for endpoint in public_endpoints):
        return await call_next(request)
    
    # For GraphQL endpoints, authorization is handled in the GraphQL resolvers
    if request.url.path.startswith("/graphql"):
        return await call_next(request)
    
    # For other endpoints, check for authorization header
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Process request
    response = await call_next(request)
    return response
