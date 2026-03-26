from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import secrets
import string


class AgentTeam(SQLModel, table=True):
    """
    AgentTeam database model for grouping custom agents and managing tool permissions.

    This model represents a collection of custom agents that work together as a team,
    along with a set of pre-approved standard tools that the team is allowed to use.
    Teams provide a way to organize and manage permissions for groups of custom agents.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_team_id: str = Field(unique=True, index=True)  # UUID identifier
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant
    name: str = Field(max_length=200, description="Human-readable name for the agent team")
    description: str = Field(description="Detailed description of the team's purpose and capabilities")
    custom_agent_ids: str = Field(
        default="[]",
        description="JSON string containing list of CustomAgentDefinition.custom_agent_id values"
    )
    pre_approved_tool_names: str = Field(
        default="[]",
        description="JSON string containing list of STABLE Tool.name values pre-approved for this team"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional team management fields
    is_active: bool = Field(default=True, index=True, description="Whether this team is active")
    is_system_agent: bool = Field(default=False, index=True, description="True if this team is platform-owned and immutable")
    
    # Versioning fields
    version: str = Field(default="1.0.0", description="Semantic version of the agent team definition")
    version_notes: Optional[str] = Field(default=None, description="Notes about this version")
    parent_version: Optional[str] = Field(default=None, description="Parent version this was created from")
    is_latest_version: bool = Field(default=True, index=True, description="True if this is the latest version")
    max_concurrent_executions: Optional[int] = Field(
        default=5,
        description="Maximum concurrent executions allowed for this team"
    )
    default_timeout_seconds: Optional[int] = Field(
        default=1800,  # 30 minutes
        description="Default timeout for team executions in seconds"
    )

    # Usage tracking
    execution_count: int = Field(default=0, description="Total number of team executions")
    last_executed_at: Optional[datetime] = Field(default=None, description="Last execution timestamp")

    # Team metadata
    team_metadata: Optional[str] = Field(default=None, description="JSON string for additional team metadata")

    # Relationships
    tenant: "Tenant" = Relationship(back_populates="agent_teams")

    @staticmethod
    def generate_agent_team_id(length: int = 16) -> str:
        """Generate a unique URL-safe agent team identifier."""
        alphabet = string.ascii_letters + string.digits + '-_'
        return 'at_' + ''.join(secrets.choice(alphabet) for _ in range(length))

    def set_custom_agent_ids(self, agent_ids: List[str]) -> None:
        """Set the list of custom agent IDs as JSON string."""
        self.custom_agent_ids = json.dumps(agent_ids) if agent_ids else json.dumps([])
        self.update_timestamp()

    def get_custom_agent_ids(self) -> List[str]:
        """Get the list of custom agent IDs from JSON string."""
        try:
            return json.loads(self.custom_agent_ids) if self.custom_agent_ids else []
        except (json.JSONDecodeError, TypeError):
            return []

    def add_custom_agent_id(self, agent_id: str) -> None:
        """Add a custom agent ID to the team."""
        current_agents = self.get_custom_agent_ids()
        if agent_id not in current_agents:
            current_agents.append(agent_id)
            self.set_custom_agent_ids(current_agents)

    def remove_custom_agent_id(self, agent_id: str) -> None:
        """Remove a custom agent ID from the team."""
        current_agents = self.get_custom_agent_ids()
        if agent_id in current_agents:
            current_agents.remove(agent_id)
            self.set_custom_agent_ids(current_agents)

    def set_pre_approved_tool_names(self, tool_names: List[str]) -> None:
        """Set the list of pre-approved tool names as JSON string."""
        self.pre_approved_tool_names = json.dumps(tool_names) if tool_names else json.dumps([])
        self.update_timestamp()

    def get_pre_approved_tool_names(self) -> List[str]:
        """Get the list of pre-approved tool names from JSON string."""
        try:
            return json.loads(self.pre_approved_tool_names) if self.pre_approved_tool_names else []
        except (json.JSONDecodeError, TypeError):
            return []

    def add_pre_approved_tool_name(self, tool_name: str) -> None:
        """Add a pre-approved tool name to the team."""
        current_tools = self.get_pre_approved_tool_names()
        if tool_name not in current_tools:
            current_tools.append(tool_name)
            self.set_pre_approved_tool_names(current_tools)

    def remove_pre_approved_tool_name(self, tool_name: str) -> None:
        """Remove a pre-approved tool name from the team."""
        current_tools = self.get_pre_approved_tool_names()
        if tool_name in current_tools:
            current_tools.remove(tool_name)
            self.set_pre_approved_tool_names(current_tools)

    def set_team_metadata(self, metadata: Dict[str, Any]) -> None:
        """Set team metadata as JSON string."""
        self.team_metadata = json.dumps(metadata) if metadata else None
        self.update_timestamp()

    def get_team_metadata(self) -> Optional[Dict[str, Any]]:
        """Get team metadata from JSON string."""
        try:
            return json.loads(self.team_metadata) if self.team_metadata else None
        except (json.JSONDecodeError, TypeError):
            return None

    def update_timestamp(self) -> None:
        """Update the last_updated_at timestamp."""
        self.last_updated_at = datetime.utcnow()

    def increment_execution_count(self) -> None:
        """Increment execution count and update last executed timestamp."""
        self.execution_count += 1
        self.last_executed_at = datetime.utcnow()
        self.update_timestamp()
    
    def create_new_version(self, new_version: str, version_notes: Optional[str] = None) -> 'AgentTeam':
        """Create a new version of this agent team definition."""
        # Create a copy with new version info
        new_team = AgentTeam(
            agent_team_id=self.generate_agent_team_id(),
            tenant_id=self.tenant_id,
            name=self.name,
            description=self.description,
            custom_agent_ids=self.custom_agent_ids,
            pre_approved_tool_names=self.pre_approved_tool_names,
            is_active=self.is_active,
            is_system_agent=self.is_system_agent,
            version=new_version,
            version_notes=version_notes,
            parent_version=self.version,
            is_latest_version=True,
            max_concurrent_executions=self.max_concurrent_executions,
            default_timeout_seconds=self.default_timeout_seconds,
            team_metadata=self.team_metadata
        )
        
        # Mark current version as not latest
        self.is_latest_version = False
        self.update_timestamp()
        
        return new_team
    
    def get_version_history(self) -> Dict[str, Any]:
        """Get version history information."""
        return {
            'current_version': self.version,
            'is_latest': self.is_latest_version,
            'parent_version': self.parent_version,
            'version_notes': self.version_notes,
            'created_at': self.created_at.isoformat(),
            'last_updated_at': self.last_updated_at.isoformat()
        }

    def is_executable(self) -> bool:
        """Check if the team is in a state where it can be executed."""
        return (
            self.is_active and
            len(self.get_custom_agent_ids()) > 0
        )

    def get_total_tools_count(self) -> int:
        """Get total number of tools available to this team (custom agents + pre-approved tools)."""
        return len(self.get_custom_agent_ids()) + len(self.get_pre_approved_tool_names())

    def validate_configuration(self) -> List[str]:
        """Validate the team configuration and return list of validation errors."""
        errors = []

        if not self.name or not self.name.strip():
            errors.append("Team name is required")

        if not self.description or not self.description.strip():
            errors.append("Team description is required")

        custom_agent_ids = self.get_custom_agent_ids()
        pre_approved_tools = self.get_pre_approved_tool_names()

        if not custom_agent_ids and not pre_approved_tools:
            errors.append("Team must have at least one custom agent or pre-approved tool")

        if self.max_concurrent_executions is not None and self.max_concurrent_executions < 1:
            errors.append("Max concurrent executions must be at least 1")

        if self.default_timeout_seconds is not None and self.default_timeout_seconds < 1:
            errors.append("Default timeout must be at least 1 second")

        # Check for duplicate agent IDs
        if len(custom_agent_ids) != len(set(custom_agent_ids)):
            errors.append("Duplicate custom agent IDs found")

        # Check for duplicate tool names
        if len(pre_approved_tools) != len(set(pre_approved_tools)):
            errors.append("Duplicate pre-approved tool names found")

        return errors

    def to_execution_config(self) -> Dict[str, Any]:
        """Convert to execution configuration dictionary for runtime use."""
        return {
            "agent_team_id": self.agent_team_id,
            "name": self.name,
            "description": self.description,
            "custom_agent_ids": self.get_custom_agent_ids(),
            "pre_approved_tool_names": self.get_pre_approved_tool_names(),
            "max_concurrent_executions": self.max_concurrent_executions,
            "default_timeout_seconds": self.default_timeout_seconds,
            "team_metadata": self.get_team_metadata()
        }

    class Config:
        """Pydantic configuration for ORM compatibility."""
        from_attributes = True
        arbitrary_types_allowed = True

    def __str__(self) -> str:
        agent_count = len(self.get_custom_agent_ids())
        tool_count = len(self.get_pre_approved_tool_names())
        return f"AgentTeam(name='{self.name}', agents={agent_count}, tools={tool_count}, active={self.is_active})"

    def __repr__(self) -> str:
        return (
            f"AgentTeam(id={self.id}, agent_team_id='{self.agent_team_id}', "
            f"name='{self.name}', tenant_id={self.tenant_id}, is_active={self.is_active})"
        )
