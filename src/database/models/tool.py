from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class ToolStatus(str, Enum):
    """Tool status enumeration for security and lifecycle management."""
    STABLE = "STABLE"
    BETA = "BETA"
    DEPRECATED = "DEPRECATED"


class Tool(SQLModel, table=True):
    """
    Tool database model for tracking tool metadata, status, and security validation.

    This model stores information about all available tools in the system,
    including their status (STABLE, BETA, DEPRECATED) which is used for
    security validation and dynamic tool loading in custom agents.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)  # e.g., "VertexAISearch", "MCPSlackTool"
    description: str = Field(description="Human-readable description of the tool's purpose")
    status: ToolStatus = Field(default=ToolStatus.BETA, index=True)
    is_custom_agent_executor: bool = Field(
        default=False,
        description="True if this is the CustomAgentRuntimeExecutor tool itself"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional metadata fields for tool management
    version: Optional[str] = Field(default=None, description="Tool version identifier")
    documentation_url: Optional[str] = Field(default=None, description="Link to tool documentation")
    category: Optional[str] = Field(default=None, index=True, description="Tool category (e.g., 'research', 'communication')")
    requires_auth: bool = Field(default=False, description="Whether tool requires authentication")
    max_concurrent_calls: Optional[int] = Field(default=None, description="Maximum concurrent calls allowed")

    def update_timestamp(self) -> None:
        """Update the last_updated_at timestamp."""
        self.last_updated_at = datetime.utcnow()

    def is_available_for_use(self) -> bool:
        """Check if tool is available for use (STABLE or BETA status)."""
        return self.status in [ToolStatus.STABLE, ToolStatus.BETA]

    def is_production_ready(self) -> bool:
        """Check if tool is production ready (STABLE status only)."""
        return self.status == ToolStatus.STABLE

    def is_deprecated(self) -> bool:
        """Check if tool is deprecated and should not be used."""
        return self.status == ToolStatus.DEPRECATED

    class Config:
        """Pydantic configuration for ORM compatibility."""
        from_attributes = True
        arbitrary_types_allowed = True

    def __str__(self) -> str:
        return f"Tool(name='{self.name}', status='{self.status.value}')"

    def __repr__(self) -> str:
        return f"Tool(id={self.id}, name='{self.name}', status='{self.status.value}', is_custom_agent_executor={self.is_custom_agent_executor})"
