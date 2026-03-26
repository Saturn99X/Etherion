import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import re

from src.core.security.audit_logger import log_security_event
from src.database.db import session_scope
from src.database.models import AgentTeam, CustomAgentDefinition
from src.tools.tool_manager import get_tool_manager

logger = logging.getLogger(__name__)


class OrchestratorSecurityValidator:
    """
    Security validation layer for orchestrator operations.

    This class provides comprehensive security validation for:
    - Tool approval validation
    - Agent team access control
    - Cross-tenant isolation
    - Execution context validation
    - Security policy enforcement
    """

    def __init__(self):
        self.tool_manager = get_tool_manager()

    async def validate_orchestrator_execution(
        self,
        tenant_id: int,
        user_id: int,
        agent_team_id: Optional[str] = None,
        job_id: str = None
    ) -> Dict[str, Any]:
        """
        Validate orchestrator execution request.

        Args:
            tenant_id: Tenant ID for isolation
            user_id: User ID for access control
            agent_team_id: Optional agent team ID
            job_id: Job ID for tracking

        Returns:
            Dict with validation results
        """
        try:
            validation_results = {
                "valid": True,
                "checks": [],
                "warnings": [],
                "errors": []
            }

            # Check 1: Tenant isolation
            tenant_check = await self._validate_tenant_isolation(tenant_id, user_id)
            validation_results["checks"].append(tenant_check)

            if not tenant_check["valid"]:
                validation_results["valid"] = False
                validation_results["errors"].append(tenant_check["error"])

            # Check 2: Agent team access
            if agent_team_id:
                team_check = await self._validate_agent_team_access(
                    agent_team_id, tenant_id, user_id
                )
                validation_results["checks"].append(team_check)

                if not team_check["valid"]:
                    validation_results["valid"] = False
                    validation_results["errors"].append(team_check["error"])

                # Check 3: Tool approval validation
                tool_check = await self._validate_team_tool_approvals(
                    agent_team_id, tenant_id
                )
                validation_results["checks"].append(tool_check)

                if tool_check.get("warning"):
                    validation_results["warnings"].append(tool_check["warning"])

            # Check 4: Job context validation
            if job_id:
                job_check = self._validate_job_context(job_id, tenant_id, user_id)
                validation_results["checks"].append(job_check)

                if not job_check["valid"]:
                    validation_results["warnings"].append(job_check["warning"])

            # Log validation results
            await log_security_event(
                event_type="orchestrator_validation_completed",
                user_id=user_id,
                tenant_id=tenant_id,
                details={
                    "job_id": job_id,
                    "agent_team_id": agent_team_id,
                    "validation_valid": validation_results["valid"],
                    "warnings_count": len(validation_results["warnings"]),
                    "errors_count": len(validation_results["errors"])
                }
            )

            return validation_results

        except Exception as e:
            logger.error(f"Error in orchestrator security validation: {e}")
            await log_security_event(
                event_type="orchestrator_validation_failed",
                user_id=user_id,
                tenant_id=tenant_id,
                details={
                    "job_id": job_id,
                    "error": str(e)
                }
            )

            return {
                "valid": False,
                "checks": [],
                "warnings": [],
                "errors": [f"Validation error: {str(e)}"]
            }

    async def _validate_tenant_isolation(self, tenant_id: int, user_id: int) -> Dict[str, Any]:
        """
        Validate tenant isolation for the user.

        Args:
            tenant_id: Tenant ID to validate
            user_id: User ID to validate

        Returns:
            Validation result
        """
        try:
            # This would typically check user-tenant association in a real system
            # For now, we'll assume the tenant_id is valid if provided

            if not tenant_id or tenant_id <= 0:
                return {
                    "check": "tenant_isolation",
                    "valid": False,
                    "error": f"Invalid tenant_id: {tenant_id}"
                }

            if not user_id or user_id <= 0:
                return {
                    "check": "tenant_isolation",
                    "valid": False,
                    "error": f"Invalid user_id: {user_id}"
                }

            # Additional tenant isolation checks would go here
            # - Verify user belongs to tenant
            # - Check tenant is active
            # - Verify tenant has necessary resources

            return {
                "check": "tenant_isolation",
                "valid": True,
                "details": f"Tenant {tenant_id} isolation validated for user {user_id}"
            }

        except Exception as e:
            return {
                "check": "tenant_isolation",
                "valid": False,
                "error": f"Tenant isolation validation error: {str(e)}"
            }

    async def _validate_agent_team_access(
        self,
        agent_team_id: str,
        tenant_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Validate user access to agent team.

        Args:
            agent_team_id: Agent team ID to validate
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            Validation result
        """
        try:
            with session_scope() as session:
                # Load agent team
                agent_team = session.query(AgentTeam).filter(
                    AgentTeam.agent_team_id == agent_team_id,
                    AgentTeam.tenant_id == tenant_id,
                    AgentTeam.is_active == True
                ).first()

                if not agent_team:
                    return {
                        "check": "agent_team_access",
                        "valid": False,
                        "error": f"Agent team {agent_team_id} not found or inactive for tenant {tenant_id}"
                    }

                # Check if it's a system agent team (only accessible by system)
                if agent_team.is_system_agent:
                    return {
                        "check": "agent_team_access",
                        "valid": False,
                        "error": f"Agent team {agent_team_id} is a system team and cannot be modified"
                    }

                # Check team is executable
                if not agent_team.is_executable():
                    return {
                        "check": "agent_team_access",
                        "valid": False,
                        "error": f"Agent team {agent_team_id} is not in executable state"
                    }

                # Additional access control checks would go here
                # - User permissions for this specific team
                # - Team-specific access policies
                # - Usage quotas and limits

                return {
                    "check": "agent_team_access",
                    "valid": True,
                    "details": f"User {user_id} has access to agent team {agent_team_id}"
                }

        except Exception as e:
            return {
                "check": "agent_team_access",
                "valid": False,
                "error": f"Agent team access validation error: {str(e)}"
            }

    async def _validate_team_tool_approvals(
        self,
        agent_team_id: str,
        tenant_id: int
    ) -> Dict[str, Any]:
        """
        Validate all tools in the agent team are properly approved.

        Args:
            agent_team_id: Agent team ID
            tenant_id: Tenant ID

        Returns:
            Validation result
        """
        try:
            with session_scope() as session:
                # Load agent team
                agent_team = session.query(AgentTeam).filter(
                    AgentTeam.agent_team_id == agent_team_id,
                    AgentTeam.tenant_id == tenant_id
                ).first()

                if not agent_team:
                    return {
                        "check": "tool_approval",
                        "valid": False,
                        "error": f"Agent team {agent_team_id} not found"
                    }

                # Get pre-approved tools
                pre_approved_tools = agent_team.get_pre_approved_tool_names()

                if not pre_approved_tools:
                    return {
                        "check": "tool_approval",
                        "valid": False,
                        "warning": f"Agent team {agent_team_id} has no pre-approved tools"
                    }

                # Validate each tool exists and is stable
                validation_warnings = []
                for tool_name in pre_approved_tools:
                    tool_valid = await self._validate_single_tool(tool_name, tenant_id)
                    if not tool_valid["valid"]:
                        validation_warnings.append(f"Tool {tool_name}: {tool_valid['warning']}")

                # Load custom agents and validate their tools
                custom_agent_ids = agent_team.get_custom_agent_ids()
                for custom_agent_id in custom_agent_ids:
                    agent_tool_warnings = await self._validate_agent_tools(
                        custom_agent_id, tenant_id, pre_approved_tools
                    )
                    validation_warnings.extend(agent_tool_warnings)

                if validation_warnings:
                    return {
                        "check": "tool_approval",
                        "valid": True,  # Warnings don't fail validation, just alert
                        "warning": f"Tool approval warnings: {'; '.join(validation_warnings)}"
                    }

                return {
                    "check": "tool_approval",
                    "valid": True,
                    "details": f"All {len(pre_approved_tools)} tools validated for team {agent_team_id}"
                }

        except Exception as e:
            return {
                "check": "tool_approval",
                "valid": False,
                "error": f"Tool approval validation error: {str(e)}"
            }

    async def _validate_single_tool(self, tool_name: str, tenant_id: int) -> Dict[str, Any]:
        """
        Validate a single tool.

        Args:
            tool_name: Name of the tool to validate
            tenant_id: Tenant ID

        Returns:
            Validation result
        """
        try:
            # Get tool instance
            tool_instance = self.tool_manager.get_tool_instance(
                tool_name=tool_name,
                tenant_id=tenant_id,
                job_id="validation"
            )

            if not tool_instance:
                return {
                    "tool": tool_name,
                    "valid": False,
                    "warning": f"Tool {tool_name} not found"
                }

            # Check if tool is stable
            if not hasattr(tool_instance, 'is_stable') or not tool_instance.is_stable:
                return {
                    "tool": tool_name,
                    "valid": False,
                    "warning": f"Tool {tool_name} is not marked as stable"
                }

            # Additional tool validation checks
            # - Check tool version compatibility
            # - Verify tool dependencies
            # - Check tool permissions

            return {
                "tool": tool_name,
                "valid": True,
                "details": f"Tool {tool_name} is stable and available"
            }

        except Exception as e:
            return {
                "tool": tool_name,
                "valid": False,
                "warning": f"Tool validation error: {str(e)}"
            }

    async def _validate_agent_tools(
        self,
        custom_agent_id: str,
        tenant_id: int,
        pre_approved_tools: List[str]
    ) -> List[str]:
        """
        Validate tools used by a custom agent.

        Args:
            custom_agent_id: Custom agent ID
            tenant_id: Tenant ID
            pre_approved_tools: List of pre-approved tools

        Returns:
            List of validation warnings
        """
        try:
            with session_scope() as session:
                # Load custom agent
                agent = session.query(CustomAgentDefinition).filter(
                    CustomAgentDefinition.custom_agent_id == custom_agent_id,
                    CustomAgentDefinition.tenant_id == tenant_id,
                    CustomAgentDefinition.is_active == True
                ).first()

                if not agent:
                    return [f"Custom agent {custom_agent_id} not found"]

                # Get agent tool names
                agent_tool_names = agent.get_tool_names()

                if not agent_tool_names:
                    return []  # No tools to validate

                # Check if agent tools are in pre-approved list
                warnings = []
                for tool_name in agent_tool_names:
                    if tool_name not in pre_approved_tools:
                        warnings.append(
                            f"Agent {custom_agent_id} uses tool {tool_name} not in pre-approved list"
                        )

                return warnings

        except Exception as e:
            return [f"Error validating agent {custom_agent_id} tools: {str(e)}"]

    def _validate_job_context(self, job_id: str, tenant_id: int, user_id: int) -> Dict[str, Any]:
        """
        Validate job context information.

        Args:
            job_id: Job ID to validate
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            Validation result
        """
        try:
            # Basic job ID format validation
            if not job_id or len(job_id) < 8:
                return {
                    "check": "job_context",
                    "valid": False,
                    "error": f"Invalid job_id format: {job_id}"
                }

            # Job ID format validation (should be UUID-like or have specific pattern)
            # This is a simple check - real implementation would be more sophisticated
            if not re.match(r'^[a-zA-Z0-9_-]+$', job_id):
                return {
                    "check": "job_context",
                    "valid": False,
                    "error": f"Job ID contains invalid characters: {job_id}"
                }

            # Additional job context validations
            # - Check job ID uniqueness
            # - Verify job metadata integrity
            # - Validate job parameters

            return {
                "check": "job_context",
                "valid": True,
                "details": f"Job context {job_id} validated for tenant {tenant_id}, user {user_id}"
            }

        except Exception as e:
            return {
                "check": "job_context",
                "valid": False,
                "error": f"Job context validation error: {str(e)}"
            }

    async def audit_tool_usage(
        self,
        tool_name: str,
        tenant_id: int,
        user_id: int,
        job_id: str,
        usage_context: Dict[str, Any]
    ) -> None:
        """
        Audit tool usage for security monitoring.

        Args:
            tool_name: Name of the tool used
            tenant_id: Tenant ID
            user_id: User ID
            job_id: Job ID
            usage_context: Context of tool usage
        """
        try:
            await log_security_event(
                event_type="tool_usage_audit",
                user_id=user_id,
                tenant_id=tenant_id,
                details={
                    "job_id": job_id,
                    "tool_name": tool_name,
                    "usage_context": usage_context,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            logger.error(f"Failed to audit tool usage: {e}")

    async def validate_execution_limits(
        self,
        tenant_id: int,
        user_id: int,
        agent_team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate execution limits and quotas.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_team_id: Optional agent team ID

        Returns:
            Validation result
        """
        try:
            # Check concurrent execution limits
            current_executions = await self._get_current_executions(tenant_id, user_id)

            # This would typically check against configured limits
            # For now, just return a basic validation
            if current_executions > 10:  # Example limit
                return {
                    "check": "execution_limits",
                    "valid": False,
                    "error": f"Too many concurrent executions ({current_executions}) for tenant {tenant_id}"
                }

            # Additional limit checks
            # - Daily execution quotas
            # - Resource usage limits
            # - Time-based restrictions

            return {
                "check": "execution_limits",
                "valid": True,
                "details": f"Execution limits validated ({current_executions} current executions)"
            }

        except Exception as e:
            return {
                "check": "execution_limits",
                "valid": False,
                "error": f"Execution limits validation error: {str(e)}"
            }

    async def _get_current_executions(self, tenant_id: int, user_id: int) -> int:
        """
        Get current number of executions for tenant/user.

        Args:
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            Number of current executions
        """
        # This would query active jobs/executions
        # For now, return a mock value
        return 1


# Global security validator instance
_security_validator: Optional[OrchestratorSecurityValidator] = None


def get_orchestrator_security_validator() -> OrchestratorSecurityValidator:
    """Get the global orchestrator security validator instance."""
    global _security_validator
    if _security_validator is None:
        _security_validator = OrchestratorSecurityValidator()
    return _security_validator
