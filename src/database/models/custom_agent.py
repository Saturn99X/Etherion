from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import secrets
import string


class CustomAgentDefinition(SQLModel, table=True):
    """
    CustomAgentDefinition database model for storing user-defined agent configurations.

    This model stores the complete configuration for custom agents that can be
    dynamically instantiated and executed by the CustomAgentRuntimeExecutor.
    Each custom agent has its own system prompt, tool restrictions, and model configuration.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    custom_agent_id: str = Field(unique=True, index=True)  # UUID identifier
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant
    name: str = Field(max_length=200, description="Human-readable name for the custom agent")
    description: str = Field(description="Detailed description of the agent's purpose and capabilities")
    system_prompt: str = Field(description="LLM system prompt that defines the agent's behavior and instructions")
    tool_names: str = Field(description="JSON string containing list of allowed tool names")
    model_name: str = Field(default="gemini-2.5-flash", description="LLM model to use for this agent")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional configuration fields
    max_iterations: Optional[int] = Field(default=10, description="Maximum iterations for agent execution")
    timeout_seconds: Optional[int] = Field(default=300, description="Execution timeout in seconds (5 minutes default)")
    temperature: Optional[float] = Field(default=0.1, description="LLM temperature setting")
    is_active: bool = Field(default=True, index=True, description="Whether this agent is active and can be executed")
    is_system_agent: bool = Field(default=False, index=True, description="True if this definition is platform-owned and immutable")
    # Soft delete flags
    is_deleted: bool = Field(default=False, index=True, description="Soft-delete flag; true means logically deleted")
    deleted_at: Optional[datetime] = Field(default=None, description="Timestamp when the agent was soft-deleted")
    
    # Versioning fields
    version: str = Field(default="1.0.0", description="Semantic version of the agent definition")
    version_notes: Optional[str] = Field(default=None, description="Notes about this version")
    parent_version: Optional[str] = Field(default=None, description="Parent version this was created from")
    is_latest_version: bool = Field(default=True, index=True, description="True if this is the latest version")

    # Usage tracking
    execution_count: int = Field(default=0, description="Total number of times this agent has been executed")
    last_executed_at: Optional[datetime] = Field(default=None, description="Last execution timestamp")

    # Metadata for additional configuration
    custom_metadata: Optional[str] = Field(default=None, description="JSON string for additional metadata")

    # Relationships
    tenant: "Tenant" = Relationship(back_populates="custom_agents")

    @staticmethod
    def generate_custom_agent_id(length: int = 16) -> str:
        """Generate a unique URL-safe custom agent identifier."""
        alphabet = string.ascii_letters + string.digits + '-_'
        return 'ca_' + ''.join(secrets.choice(alphabet) for _ in range(length))

    def set_tool_names(self, tool_names: List[str]) -> None:
        """Set the list of allowed tool names as JSON string."""
        self.tool_names = json.dumps(tool_names) if tool_names else json.dumps([])
        self.update_timestamp()

    def get_tool_names(self) -> List[str]:
        """Get the list of allowed tool names from JSON string."""
        try:
            return json.loads(self.tool_names) if self.tool_names else []
        except (json.JSONDecodeError, TypeError):
            return []

    def add_tool_name(self, tool_name: str) -> None:
        """Add a tool name to the allowed tools list."""
        current_tools = self.get_tool_names()
        if tool_name not in current_tools:
            current_tools.append(tool_name)
            self.set_tool_names(current_tools)

    def remove_tool_name(self, tool_name: str) -> None:
        """Remove a tool name from the allowed tools list."""
        current_tools = self.get_tool_names()
        if tool_name in current_tools:
            current_tools.remove(tool_name)
            self.set_tool_names(current_tools)

    def set_custom_metadata(self, metadata: Dict[str, Any]) -> None:
        """Set custom metadata as JSON string."""
        self.custom_metadata = json.dumps(metadata) if metadata else None
        self.update_timestamp()

    def get_custom_metadata(self) -> Optional[Dict[str, Any]]:
        """Get custom metadata from JSON string."""
        try:
            return json.loads(self.custom_metadata) if self.custom_metadata else None
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
    
    def create_new_version(self, new_version: str, version_notes: Optional[str] = None) -> 'CustomAgentDefinition':
        """Create a new version of this agent definition."""
        # Create a copy with new version info
        new_agent = CustomAgentDefinition(
            custom_agent_id=self.generate_custom_agent_id(),
            tenant_id=self.tenant_id,
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            tool_names=self.tool_names,
            model_name=self.model_name,
            max_iterations=self.max_iterations,
            timeout_seconds=self.timeout_seconds,
            temperature=self.temperature,
            is_active=self.is_active,
            is_system_agent=self.is_system_agent,
            version=new_version,
            version_notes=version_notes,
            parent_version=self.version,
            is_latest_version=True,
            custom_metadata=self.custom_metadata
        )
        
        # Mark current version as not latest
        self.is_latest_version = False
        self.update_timestamp()
        
        return new_agent
    
    def get_version_history(self) -> List[Dict[str, Any]]:
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
        """Check if the agent is in a state where it can be executed."""
        return (
            self.is_active and
            bool(self.system_prompt.strip()) and
            len(self.get_tool_names()) > 0
        )

    def validate_configuration(self) -> List[str]:
        """Validate the agent configuration and return list of validation errors."""
        errors = []

        if not self.name or not self.name.strip():
            errors.append("Agent name is required")

        if not self.system_prompt or not self.system_prompt.strip():
            errors.append("System prompt is required")

        if not self.model_name or not self.model_name.strip():
            errors.append("Model name is required")

        tool_names = self.get_tool_names()
        if not tool_names:
            errors.append("At least one tool must be specified")

        if self.max_iterations is not None and self.max_iterations < 1:
            errors.append("Max iterations must be at least 1")

        if self.timeout_seconds is not None and self.timeout_seconds < 1:
            errors.append("Timeout must be at least 1 second")

        if self.temperature is not None and (self.temperature < 0 or self.temperature > 2):
            errors.append("Temperature must be between 0 and 2")

        return errors

    def to_execution_config(self) -> Dict[str, Any]:
        """Convert to execution configuration dictionary for runtime use."""
        return {
            "custom_agent_id": self.custom_agent_id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tool_names": self.get_tool_names(),
            "model_name": self.model_name,
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
            "temperature": self.temperature,
            "custom_metadata": self.get_custom_metadata()
        }

    class Config:
        """Pydantic configuration for ORM compatibility."""
        from_attributes = True
        arbitrary_types_allowed = True

    def __str__(self) -> str:
        return f"CustomAgent(name='{self.name}', id='{self.custom_agent_id}', active={self.is_active})"

    def __repr__(self) -> str:
        return (
            f"CustomAgentDefinition(id={self.id}, custom_agent_id='{self.custom_agent_id}', "
            f"name='{self.name}', tenant_id={self.tenant_id}, is_active={self.is_active})"
        )
