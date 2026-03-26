# src/etherion_ai/graphql_schema/input_types.py

import strawberry
from typing import Optional, List
from datetime import datetime
from strawberry.scalars import JSON

@strawberry.input
class GoalInput:
    """
    A universal input for the Orchestrator Agent.
    This structure allows users to define any high-level goal for the system to execute.
    
    Example:
    {
      "goal": "Create a 3-part welcome email series for new subscribers.",
      "context": "Our brand voice is friendly and professional. Target audience is tech-savvy professionals aged 25-40.",
      "output_format_instructions": "Return a JSON object with keys: subject, body for each email.",
      "userId": "user_123456"
    }
    """
    goal: Optional[str] = strawberry.field(
        description="""The primary, high-level objective for the agentic system. 
        Examples: 'Create a 3-part welcome email series for new subscribers.' or 
        'Write a comprehensive blog post about the impact of AI on renewable energy.'
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 2000 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    context: Optional[str] = strawberry.field(
        default=None,
        description="""Optional detailed context. Include brand voice, target audience details, 
        key points to mention, or any other relevant information to guide the Orchestrator.
        
        Constraints:
        - Maximum length: 5000 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    output_format_instructions: Optional[str] = strawberry.field(
        default=None,
        description="""Optional instructions on how the final output should be structured. 
        Examples: 'Return a single markdown string.' or 'Return a JSON object with keys: title, body, seo_keywords.'
        
        Constraints:
        - Maximum length: 1000 characters
        - Must not contain script tags or other potentially有害 content"""
    )

    userId: Optional[str] = strawberry.field(
        description="""The unique identifier for the user making the request.
        Essential for personalizing the experience.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters"""
    )

    agentTeamId: Optional[str] = strawberry.field(
        default=None,
        description="""Optional ID of a custom AgentTeam to use for this goal.
        If provided, the system will load the specified AgentTeam definition
        and use its custom agents and pre-approved tools for execution.

        Constraints:
        - Must be a valid AgentTeam ID if provided
        - Maximum length: 50 characters"""
    )

    # Execution preferences — explicit fields (not context hints)
    plan_mode: Optional[bool] = strawberry.field(
        default=None,
        description="""Optional: prefer planning-first behavior in the orchestrator UI/flow.
        This is a hint to the runtime, not a guarantee of behavior."""
    )

    search_force: Optional[bool] = strawberry.field(
        default=None,
        description="""Optional: force enable/disable enhanced search behavior (e.g., stronger web/KB retrieval).
        This is a hint to the runtime; platform may still perform mandatory baseline search."""
    )

    threadId: Optional[str] = strawberry.field(
        default=None,
        description="""Optional: existing thread ID to append this goal to.
        If omitted, the backend may create a new thread and return mapping via job metadata/trace."""
    )

    provider: Optional[str] = strawberry.field(
        default=None,
        description=(
            "Optional logical provider key (e.g. 'openai', 'vertex', 'azure_openai'). "
            "Used as a hint/override by the orchestrator."
        ),
    )
    model: Optional[str] = strawberry.field(
        default=None,
        description=(
            "Optional logical model key within the provider (e.g. 'gpt-4.1'). "
            "Used as a hint/override by the orchestrator."
        ),
    )

@strawberry.input
class FeedbackInput:
    """
    Input for user feedback on completed goals.
    
    Example:
    {
      "jobId": "job_7890",
      "userId": "user_123456",
      "goal": "Create a blog post about AI",
      "finalOutput": "Here is the blog post content...",
      "feedbackScore": 5,
      "feedbackComment": "This was exactly what I needed!"
    }
    """
    jobId: str = strawberry.field(
        description="""The unique identifier for the job being rated.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters"""
    )
    
    userId: str = strawberry.field(
        description="""The unique identifier for the user providing feedback.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters"""
    )
    
    goal: str = strawberry.field(
        description="""The original goal that was executed.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 2000 characters
        - Must not contain script tags"""
    )
    
    finalOutput: str = strawberry.field(
        description="""The final output generated by the system.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 10000 characters
        - Must not contain script tags"""
    )
    
    feedbackScore: int = strawberry.field(
        description="""User rating of the output quality (1-5 scale).
        
        Constraints:
        - Minimum value: 1
        - Maximum value: 5"""
    )
    
    feedbackComment: str = strawberry.field(
        description="""User's detailed feedback comment.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 1000 characters
        - Must not contain script tags"""
    )

@strawberry.input
class SupportTicketInput:
    """
    Input for customer support tickets.
    
    Example:
    {
      "ticketText": "I'm having trouble accessing my account.",
      "userId": "user_123456",
      "orderId": "order_7890",
      "attachedFiles": ["https://example.com/screenshot.png"]
    }
    """
    ticketText: str = strawberry.field(
        description="""The text content of the customer support ticket.
        
        Constraints:
        - Minimum length: 10 characters
        - Maximum length: 5000 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    userId: str = strawberry.field(
        description="""The unique identifier for the user submitting the ticket.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters"""
    )
    
    orderId: Optional[str] = strawberry.field(
        default=None,
        description="""The order ID related to the support ticket, if applicable.
        
        Constraints:
        - Maximum length: 50 characters
        - Must not contain script tags"""
    )
    
    attachedFiles: Optional[List[str]] = strawberry.field(
        default=None,
        description="""List of file URLs or identifiers attached to the ticket.
        
        Constraints:
        - Maximum of 10 files
        - Each URL must be a valid HTTP/HTTPS URL
        - Maximum length per URL: unlimited (but validated as URL)"""
    )

@strawberry.input
class TenantInput:
    """
    Input for creating a new tenant.
    
    Example:
    {
      "name": "Acme Corporation",
      "adminEmail": "admin@acme.com",
      "password": "securePassword123"
    }
    """
    name: str = strawberry.field(
        description="""The display name for the tenant.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    adminEmail: str = strawberry.field(
        description="""The email address of the tenant administrator.
        
        Constraints:
        - Must be a valid email format
        - Maximum length: 255 characters"""
    )
    
    password: Optional[str] = strawberry.field(
        default=None,
        description="""Optional password for the tenant administrator account.
        
        Notes:
        - When the caller is already authenticated (OAuth), password is not required.
        - When creating a tenant without an authenticated user, password is required and must meet strength rules.
        
        Constraints (when provided):
        - Minimum length: 8 characters
        - Maximum length: 128 characters
        - Must contain at least one uppercase letter, one lowercase letter, and one digit"""
    )
    
    subdomain: Optional[str] = strawberry.field(
        default=None,
        description="""Optional desired subdomain for the tenant.
        
        Constraints:
        - Lowercase letters, digits, and hyphens only
        - Must start and end with a letter or digit
        - Length between 3 and 63
        - Cannot be 'default' or a reserved keyword"""
    )

@strawberry.input
class ProjectInput:
    """
    Input for creating or updating a project.
    
    Example:
    {
      "name": "Marketing Campaign",
      "description": "Q4 marketing campaign for new product launch"
    }
    """
    name: str = strawberry.field(
        description="""The name of the project.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    description: str = strawberry.field(
        default="",
        description="""The description of the project.
        
        Constraints:
        - Maximum length: 1000 characters
        - Must not contain script tags or other potentially harmful content"""
    )

@strawberry.input
class ConversationInput:
    """
    Input for creating a conversation within a project.
    
    Example:
    {
      "title": "New Product Launch Discussion",
      "projectId": 1
    }
    """
    title: str = strawberry.field(
        description="""The title of the conversation.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 200 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    projectId: int = strawberry.field(
        description="""The ID of the project this conversation belongs to.
        
        Constraints:
        - Must be a positive integer"""
    )

@strawberry.input
class ToneProfileInput:
    """
    Input for creating or updating a tone profile.
    
    Example:
    {
      "name": "Professional",
      "profileText": "Use a formal, professional tone with proper grammar and business language.",
      "description": "Formal tone suitable for business communications",
      "isDefault": false
    }
    """
    name: str = strawberry.field(
        description="""The name of the tone profile.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    profileText: str = strawberry.field(
        description="""The text that describes the tone profile.
        
        Constraints:
        - Minimum length: 1 character
        - Maximum length: 1000 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    description: Optional[str] = strawberry.field(
        default=None,
        description="""Optional description of the tone profile.
        
        Constraints:
        - Maximum length: 500 characters
        - Must not contain script tags or other potentially harmful content"""
    )
    
    isDefault: Optional[bool] = strawberry.field(
        default=False,
        description="Whether this is a default tone profile."
    )

@strawberry.input
class ScheduledTaskInput:
    """
    Input for creating or updating a scheduled task.

    Example:
    {
      "projectId": 1,
      "goalInput": {
        "goal": "Create a blog post about AI",
        "context": "Focus on practical applications",
        "userId": "user_123456"
      },
      "scheduledAt": "2025-08-25T10:00:00Z"
    }
    """
    projectId: int = strawberry.field(
        description="""The ID of the project this task belongs to.

        Constraints:
        - Must be a positive integer"""
    )

    goalInput: GoalInput = strawberry.field(
        description="""The goal input for the scheduled task."""
    )

    scheduledAt: datetime = strawberry.field(
        description="""The datetime when the task should be executed.

        Constraints:
        - Must be a valid ISO format datetime
        - Must be in the future"""
    )

@strawberry.input
class ImageEditImageInput:
    """
    An image payload (base64) for editing or multi-image fusion.
    """
    mimeType: str = strawberry.field(description="MIME type of the image, e.g., image/png")
    base64: str = strawberry.field(description="Base64-encoded image data")

@strawberry.input
class ImageGenInput:
    """
    Input for image generation or editing using Gemini 2.5 Flash Image.
    """
    prompt: str = strawberry.field(description="Text prompt describing the desired image")
    images: Optional[List[ImageEditImageInput]] = strawberry.field(
        default=None,
        description="Optional list of input images for edit/fusion"
    )
    generationConfig: Optional[str] = strawberry.field(
        default=None,
        description="Optional JSON string for generation parameters (size, style, etc.)"
    )

# ============================================================================
# AGENT MANAGEMENT INPUT TYPES
# ============================================================================

@strawberry.input
class AgentInput:
    """
    Input for creating or updating an agent.

    Example:
    {
      "name": "Customer Support Agent",
      "description": "Handles customer inquiries and provides product information",
      "agentType": "specialized",
      "capabilities": ["customer_support", "product_info"],
      "systemPrompt": "You are a helpful customer support agent..."
    }
    """
    name: str = strawberry.field(
        description="""The name of the agent.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters"""
    )

    description: str = strawberry.field(
        description="""Description of what the agent does.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 1000 characters"""
    )

    agentType: str = strawberry.field(
        description="""Type of agent (specialized, general, assistant).

        Constraints:
        - Must be one of: specialized, general, assistant"""
    )

    capabilities: List[str] = strawberry.field(
        description="""List of capabilities the agent has.

        Constraints:
        - Maximum of 20 capabilities"""
    )

    systemPrompt: Optional[str] = strawberry.field(
        default=None,
        description="""Custom system prompt for the agent.

        Constraints:
        - Maximum length: 5000 characters"""
    )

@strawberry.input
class AgentTeamInput:
    """
    Input for creating a new agent team from a natural language specification.
    """
    name: str = strawberry.field(description="The name of the agent team.")
    description: str = strawberry.field(description="A description of the agent team's purpose.")
    specification: str = strawberry.field(description="A natural language specification of what the agent team should do.")
    # Optional fields to support FE 'from definition' flows
    customAgentIDs: Optional[List[str]] = strawberry.field(default=None, description="Optional: explicit list of CustomAgentDefinition IDs to include")
    pre_approved_tool_names: Optional[List[str]] = strawberry.field(default=None, description="Optional: explicit list of pre-approved tool names")

@strawberry.input
class CustomAgentDefinitionInput:
    """
    Input for creating a CustomAgentDefinition from a blueprint artifact.

    This mirrors the FE blueprint payload minimally and is intentionally permissive.
    """
    name: str = strawberry.field(description="Display name for the custom agent")
    specification: Optional[str] = strawberry.field(default=None, description="Free-form blueprint/spec text used as description")
    team_structure: Optional[JSON] = strawberry.field(default=None, description="Optional team structure object")
    user_personality: Optional[JSON] = strawberry.field(default=None, description="Optional user/system persona data")

@strawberry.input
class IntegrationInput:
    """
    Input for creating or updating an integration.

    Example:
    {
      "serviceName": "slack",
      "credentials": "{\"bot_token\": \"xoxb-...\"}",
      "configuration": "{\"channel\": \"#general\"}"
    }
    """
    serviceName: str = strawberry.field(
        description="""Name of the service to integrate with.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 50 characters"""
    )

    credentials: str = strawberry.field(
        description="""JSON string containing credentials for the service.

        Constraints:
        - Must be valid JSON
        - Maximum length: 10000 characters"""
    )

    configuration: Optional[str] = strawberry.field(
        default=None,
        description="""Optional configuration for the integration.

        Constraints:
        - Must be valid JSON if provided
        - Maximum length: 5000 characters"""
    )

# ============================================================================
# MCP TOOL INPUT TYPES
# ============================================================================

@strawberry.input
class MCPToolExecutionParams:
    """
    Input parameters for MCP tool execution.

    Example:
    {
      "toolName": "mcp_slack",
      "parameters": "{\"message\": \"Hello world\", \"channel\": \"#general\"}"
    }
    """
    toolName: str = strawberry.field(
        description="""Name of the MCP tool to execute.

        Constraints:
        - Must be a registered MCP tool name"""
    )

    parameters: str = strawberry.field(
        description="""JSON string containing parameters for the tool.

        Constraints:
        - Must be valid JSON
        - Maximum length: 10000 characters"""
    )

@strawberry.input
class MCPCredentials:
    """
    Input for MCP tool credentials.

    Example:
    {
      "toolName": "mcp_slack",
      "credentials": "{\"bot_token\": \"xoxb-...\", \"app_token\": \"xapp-...\"}"
    }
    """
    toolName: str = strawberry.field(
        description="""Name of the MCP tool.

        Constraints:
        - Must be a registered MCP tool name"""
    )

    credentials: str = strawberry.field(
        description="""JSON string containing credentials for the tool.

        Constraints:
        - Must be valid JSON
        - Maximum length: 10000 characters"""
    )

# ============================================================================
# JOB HISTORY INPUT TYPES
# ============================================================================

@strawberry.input
class JobHistoryFilter:
    """
    Input for filtering job history.

    Example:
    {
      "limit": 50,
      "offset": 0,
      "status": "completed",
      "dateFrom": "2025-01-01",
      "dateTo": "2025-01-31"
    }
    """
    limit: Optional[int] = strawberry.field(
        default=50,
        description="""Maximum number of jobs to return.

        Constraints:
        - Minimum: 1
        - Maximum: 1000"""
    )

    offset: Optional[int] = strawberry.field(
        default=0,
        description="""Number of jobs to skip for pagination.

        Constraints:
        - Minimum: 0"""
    )

    status: Optional[str] = strawberry.field(
        default=None,
        description="""Filter by job status.

        Possible values:
        - completed, running, failed, pending, cancelled"""
    )

    dateFrom: Optional[str] = strawberry.field(
        default=None,
        description="""Start date for filtering (ISO format).

        Example: 2025-01-01"""
    )

    dateTo: Optional[str] = strawberry.field(
        default=None,
        description="""End date for filtering (ISO format).

        Example: 2025-01-31"""
    )
