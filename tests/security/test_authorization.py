# tests/security/test_authorization.py
"""
Comprehensive tests for authorization and access control.
Tests tenant isolation, role-based access control, and permission validation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException, status
from sqlmodel import Session

from src.middleware.authorization import (
    AuthorizationContext,
    Permission,
    Role,
    ROLE_PERMISSIONS,
    get_authorization_context,
    require_permission,
    require_any_permission,
    validate_tenant_access,
    validate_project_access,
    validate_conversation_access,
    validate_job_access,
    validate_user_owns_resource,
    authorization_middleware
)
from src.database.models import User, Tenant, Project, Conversation, Job


class TestAuthorizationContext:
    """Test cases for AuthorizationContext."""
    
    def test_authorization_context_creation(self):
        """Test AuthorizationContext creation."""
        user = Mock(spec=User)
        user.id = 1
        user.user_id = "user123"
        
        tenant = Mock(spec=Tenant)
        tenant.id = 1
        
        auth_context = AuthorizationContext(user, tenant, Role.USER)
        
        assert auth_context.user == user
        assert auth_context.tenant == tenant
        assert auth_context.role == Role.USER
        assert isinstance(auth_context.permissions, set)
    
    def test_has_permission_admin(self):
        """Test permission checking for admin role."""
        user = Mock(spec=User)
        tenant = Mock(spec=Tenant)
        
        auth_context = AuthorizationContext(user, tenant, Role.ADMIN)
        
        # Admin should have all permissions
        assert auth_context.has_permission(Permission.MANAGE_TENANT)
        assert auth_context.has_permission(Permission.MANAGE_USERS)
        assert auth_context.has_permission(Permission.READ_AUDIT_LOGS)
        assert auth_context.has_permission(Permission.READ_PROJECT)
        assert auth_context.has_permission(Permission.WRITE_PROJECT)
    
    def test_has_permission_user(self):
        """Test permission checking for user role."""
        user = Mock(spec=User)
        tenant = Mock(spec=Tenant)
        
        auth_context = AuthorizationContext(user, tenant, Role.USER)
        
        # User should have basic permissions
        assert auth_context.has_permission(Permission.READ_PROJECT)
        assert auth_context.has_permission(Permission.WRITE_PROJECT)
        assert auth_context.has_permission(Permission.EXECUTE_GOAL)
        
        # User should not have admin permissions
        assert not auth_context.has_permission(Permission.MANAGE_TENANT)
        assert not auth_context.has_permission(Permission.MANAGE_USERS)
        assert not auth_context.has_permission(Permission.READ_AUDIT_LOGS)
    
    def test_has_permission_viewer(self):
        """Test permission checking for viewer role."""
        user = Mock(spec=User)
        tenant = Mock(spec=Tenant)
        
        auth_context = AuthorizationContext(user, tenant, Role.VIEWER)
        
        # Viewer should have read-only permissions
        assert auth_context.has_permission(Permission.READ_PROJECT)
        assert auth_context.has_permission(Permission.READ_CONVERSATION)
        assert auth_context.has_permission(Permission.READ_JOB)
        
        # Viewer should not have write permissions
        assert not auth_context.has_permission(Permission.WRITE_PROJECT)
        assert not auth_context.has_permission(Permission.EXECUTE_GOAL)
        assert not auth_context.has_permission(Permission.MANAGE_TENANT)
    
    def test_has_permission_guest(self):
        """Test permission checking for guest role."""
        user = Mock(spec=User)
        tenant = Mock(spec=Tenant)
        
        auth_context = AuthorizationContext(user, tenant, Role.GUEST)
        
        # Guest should have minimal permissions
        assert auth_context.has_permission(Permission.READ_PROJECT)
        
        # Guest should not have other permissions
        assert not auth_context.has_permission(Permission.WRITE_PROJECT)
        assert not auth_context.has_permission(Permission.EXECUTE_GOAL)
        assert not auth_context.has_permission(Permission.READ_CONVERSATION)
    
    def test_has_any_permission(self):
        """Test has_any_permission method."""
        user = Mock(spec=User)
        tenant = Mock(spec=Tenant)
        
        auth_context = AuthorizationContext(user, tenant, Role.USER)
        
        # Should return True if user has any of the permissions
        permissions = [Permission.READ_PROJECT, Permission.MANAGE_TENANT]
        assert auth_context.has_any_permission(permissions)
        
        # Should return False if user has none of the permissions
        permissions = [Permission.MANAGE_TENANT, Permission.MANAGE_USERS]
        assert not auth_context.has_any_permission(permissions)
    
    def test_has_all_permissions(self):
        """Test has_all_permissions method."""
        user = Mock(spec=User)
        tenant = Mock(spec=Tenant)
        
        auth_context = AuthorizationContext(user, tenant, Role.USER)
        
        # Should return True if user has all permissions
        permissions = [Permission.READ_PROJECT, Permission.WRITE_PROJECT]
        assert auth_context.has_all_permissions(permissions)
        
        # Should return False if user is missing any permission
        permissions = [Permission.READ_PROJECT, Permission.MANAGE_TENANT]
        assert not auth_context.has_all_permissions(permissions)


class TestTenantAccessValidation:
    """Test cases for tenant access validation."""
    
    @pytest.mark.asyncio
    async def test_validate_tenant_access_success(self):
        """Test successful tenant access validation."""
        user = Mock(spec=User)
        user.user_id = "user123"
        
        tenant = Mock(spec=Tenant)
        tenant.id = 1
        
        auth_context = AuthorizationContext(user, tenant, Role.USER)
        
        # Should not raise an exception
        result = await validate_tenant_access(auth_context, 1, "project")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_tenant_access_cross_tenant(self):
        """Test tenant access validation with cross-tenant access attempt."""
        user = Mock(spec=User)
        user.user_id = "user123"
        
        tenant = Mock(spec=Tenant)
        tenant.id = 1
        
        auth_context = AuthorizationContext(user, tenant, Role.USER)
        
        with patch('src.middleware.authorization.log_authorization_failure') as mock_log:
            with pytest.raises(HTTPException) as exc_info:
                await validate_tenant_access(auth_context, 2, "project")
            
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Cross-tenant access attempt" in str(exc_info.value.detail)
            mock_log.assert_called_once()


class TestProjectAccessValidation:
    """Test cases for project access validation."""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = Mock(spec=Session)
        return session
    
    @pytest.fixture
    def mock_auth_context(self):
        """Create a mock authorization context."""
        user = Mock(spec=User)
        user.user_id = "user123"
        
        tenant = Mock(spec=Tenant)
        tenant.id = 1
        
        return AuthorizationContext(user, tenant, Role.USER)
    
    @pytest.fixture
    def mock_project(self):
        """Create a mock project."""
        project = Mock(spec=Project)
        project.id = 1
        project.tenant_id = 1
        return project
    
    @pytest.mark.asyncio
    async def test_validate_project_access_success(self, mock_auth_context, mock_session, mock_project):
        """Test successful project access validation."""
        mock_session.exec.return_value.first.return_value = mock_project
        
        with patch('src.middleware.authorization.validate_tenant_access') as mock_validate_tenant:
            with patch('src.middleware.authorization.log_data_access') as mock_log_data:
                result = await validate_project_access(mock_auth_context, 1, mock_session)
                
                assert result == mock_project
                mock_validate_tenant.assert_called_once_with(mock_auth_context, 1, "project")
                mock_log_data.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_project_access_no_permission(self, mock_auth_context, mock_session):
        """Test project access validation without permission."""
        # Create auth context with viewer role (no write permission)
        viewer_context = AuthorizationContext(mock_auth_context.user, mock_auth_context.tenant, Role.VIEWER)
        
        with patch('src.middleware.authorization.log_authorization_failure') as mock_log:
            with pytest.raises(HTTPException) as exc_info:
                await validate_project_access(viewer_context, 1, mock_session, Permission.WRITE_PROJECT)
            
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Permission denied" in str(exc_info.value.detail)
            mock_log.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_project_access_not_found(self, mock_auth_context, mock_session):
        """Test project access validation with non-existent project."""
        mock_session.exec.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_project_access(mock_auth_context, 999, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Project not found" in str(exc_info.value.detail)


class TestConversationAccessValidation:
    """Test cases for conversation access validation."""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = Mock(spec=Session)
        return session
    
    @pytest.fixture
    def mock_auth_context(self):
        """Create a mock authorization context."""
        user = Mock(spec=User)
        user.user_id = "user123"
        
        tenant = Mock(spec=Tenant)
        tenant.id = 1
        
        return AuthorizationContext(user, tenant, Role.USER)
    
    @pytest.fixture
    def mock_conversation(self):
        """Create a mock conversation."""
        conversation = Mock(spec=Conversation)
        conversation.id = 1
        conversation.tenant_id = 1
        return conversation
    
    @pytest.mark.asyncio
    async def test_validate_conversation_access_success(self, mock_auth_context, mock_session, mock_conversation):
        """Test successful conversation access validation."""
        mock_session.exec.return_value.first.return_value = mock_conversation
        
        with patch('src.middleware.authorization.validate_tenant_access') as mock_validate_tenant:
            with patch('src.middleware.authorization.log_data_access') as mock_log_data:
                result = await validate_conversation_access(mock_auth_context, 1, mock_session)
                
                assert result == mock_conversation
                mock_validate_tenant.assert_called_once_with(mock_auth_context, 1, "conversation")
                mock_log_data.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_conversation_access_not_found(self, mock_auth_context, mock_session):
        """Test conversation access validation with non-existent conversation."""
        mock_session.exec.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_conversation_access(mock_auth_context, 999, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in str(exc_info.value.detail)


class TestJobAccessValidation:
    """Test cases for job access validation."""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = Mock(spec=Session)
        return session
    
    @pytest.fixture
    def mock_auth_context(self):
        """Create a mock authorization context."""
        user = Mock(spec=User)
        user.user_id = "user123"
        
        tenant = Mock(spec=Tenant)
        tenant.id = 1
        
        return AuthorizationContext(user, tenant, Role.USER)
    
    @pytest.fixture
    def mock_job(self):
        """Create a mock job."""
        job = Mock(spec=Job)
        job.job_id = "job123"
        job.tenant_id = 1
        return job
    
    @pytest.mark.asyncio
    async def test_validate_job_access_success(self, mock_auth_context, mock_session, mock_job):
        """Test successful job access validation."""
        mock_session.exec.return_value.first.return_value = mock_job
        
        with patch('src.middleware.authorization.validate_tenant_access') as mock_validate_tenant:
            with patch('src.middleware.authorization.log_data_access') as mock_log_data:
                result = await validate_job_access(mock_auth_context, "job123", mock_session)
                
                assert result == mock_job
                mock_validate_tenant.assert_called_once_with(mock_auth_context, 1, "job")
                mock_log_data.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_job_access_not_found(self, mock_auth_context, mock_session):
        """Test job access validation with non-existent job."""
        mock_session.exec.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_job_access(mock_auth_context, "nonexistent", mock_session)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Job not found" in str(exc_info.value.detail)


class TestUserOwnershipValidation:
    """Test cases for user ownership validation."""
    
    @pytest.fixture
    def mock_auth_context(self):
        """Create a mock authorization context."""
        user = Mock(spec=User)
        user.id = 1
        user.user_id = "user123"
        
        tenant = Mock(spec=Tenant)
        tenant.id = 1
        
        return AuthorizationContext(user, tenant, Role.USER)
    
    @pytest.mark.asyncio
    async def test_validate_user_owns_resource_success(self, mock_auth_context):
        """Test successful user ownership validation."""
        result = await validate_user_owns_resource(mock_auth_context, 1, "project")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_user_owns_resource_different_user(self, mock_auth_context):
        """Test user ownership validation with different user."""
        with patch('src.middleware.authorization.log_authorization_failure') as mock_log:
            with pytest.raises(HTTPException) as exc_info:
                await validate_user_owns_resource(mock_auth_context, 2, "project")
            
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "belongs to different user" in str(exc_info.value.detail)
            mock_log.assert_called_once()


class TestPermissionDecorators:
    """Test cases for permission decorators."""
    
    @pytest.fixture
    def mock_auth_context(self):
        """Create a mock authorization context."""
        user = Mock(spec=User)
        user.user_id = "user123"
        
        tenant = Mock(spec=Tenant)
        tenant.id = 1
        
        return AuthorizationContext(user, tenant, Role.USER)
    
    @pytest.mark.asyncio
    async def test_require_permission_success(self, mock_auth_context):
        """Test require_permission decorator with valid permission."""
        @require_permission(Permission.READ_PROJECT)
        async def test_function(auth_context: AuthorizationContext):
            return "success"
        
        result = await test_function(auth_context=auth_context)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_require_permission_failure(self, mock_auth_context):
        """Test require_permission decorator with invalid permission."""
        @require_permission(Permission.MANAGE_TENANT)
        async def test_function(auth_context: AuthorizationContext):
            return "success"
        
        with patch('src.middleware.authorization.log_authorization_failure') as mock_log:
            with pytest.raises(HTTPException) as exc_info:
                await test_function(auth_context=mock_auth_context)
            
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Permission denied" in str(exc_info.value.detail)
            mock_log.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_require_any_permission_success(self, mock_auth_context):
        """Test require_any_permission decorator with valid permission."""
        @require_any_permission([Permission.READ_PROJECT, Permission.MANAGE_TENANT])
        async def test_function(auth_context: AuthorizationContext):
            return "success"
        
        result = await test_function(auth_context=mock_auth_context)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_require_any_permission_failure(self, mock_auth_context):
        """Test require_any_permission decorator with no valid permissions."""
        @require_any_permission([Permission.MANAGE_TENANT, Permission.MANAGE_USERS])
        async def test_function(auth_context: AuthorizationContext):
            return "success"
        
        with patch('src.middleware.authorization.log_authorization_failure') as mock_log:
            with pytest.raises(HTTPException) as exc_info:
                await test_function(auth_context=mock_auth_context)
            
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Permission denied" in str(exc_info.value.detail)
            mock_log.assert_called_once()


class TestRolePermissions:
    """Test cases for role-based permissions."""
    
    def test_role_permissions_structure(self):
        """Test that role permissions are properly structured."""
        assert Role.ADMIN in ROLE_PERMISSIONS
        assert Role.USER in ROLE_PERMISSIONS
        assert Role.VIEWER in ROLE_PERMISSIONS
        assert Role.GUEST in ROLE_PERMISSIONS
        
        # Check that all permissions are valid
        for role, permissions in ROLE_PERMISSIONS.items():
            assert isinstance(permissions, list)
            for permission in permissions:
                assert isinstance(permission, Permission)
    
    def test_admin_has_all_permissions(self):
        """Test that admin role has all permissions."""
        admin_permissions = set(ROLE_PERMISSIONS[Role.ADMIN])
        all_permissions = set(Permission)
        
        assert admin_permissions == all_permissions
    
    def test_permission_hierarchy(self):
        """Test that permission hierarchy is logical."""
        admin_permissions = set(ROLE_PERMISSIONS[Role.ADMIN])
        user_permissions = set(ROLE_PERMISSIONS[Role.USER])
        viewer_permissions = set(ROLE_PERMISSIONS[Role.VIEWER])
        guest_permissions = set(ROLE_PERMISSIONS[Role.GUEST])
        
        # Admin should have all permissions
        assert admin_permissions.issuperset(user_permissions)
        assert admin_permissions.issuperset(viewer_permissions)
        assert admin_permissions.issuperset(guest_permissions)
        
        # User should have more permissions than viewer
        assert user_permissions.issuperset(viewer_permissions)
        assert user_permissions.issuperset(guest_permissions)
        
        # Viewer should have more permissions than guest
        assert viewer_permissions.issuperset(guest_permissions)
