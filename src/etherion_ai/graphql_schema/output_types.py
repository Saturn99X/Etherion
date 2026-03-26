# src/etherion_ai/graphql_schema/output_types.py

import strawberry
from strawberry.scalars import JSON
from typing import Optional, List
from datetime import datetime
from strawberry.scalars import JSON
@strawberry.type
class ImageAsset:
    gcsUri: str = strawberry.field(description="GCS URI of the saved image")
    mimeType: str = strawberry.field(description="MIME type, e.g., image/png")

@strawberry.type
class ImageGenResult:
    success: bool = strawberry.field(description="Whether generation succeeded")
    assets: Optional[List[ImageAsset]] = strawberry.field(default=None, description="Saved image assets")
    safety: Optional[JSON] = strawberry.field(default=None, description="Prompt/model safety feedback")
    safetyRatings: Optional[JSON] = strawberry.field(default=None, description="Safety ratings from candidate")
    durationSeconds: Optional[float] = strawberry.field(default=None, description="Generation duration")


@strawberry.type
class LinkSuggestion:
    """
    Represents a suggested internal or external link to enhance content.

    Example:
    {
      "text": "Learn more about AI",
      "url": "https://example.com/ai-introduction"
    }
    """
    text: str = strawberry.field(
        description="""The suggested anchor text for the link.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters"""
    )
    url: str = strawberry.field(
        description="""The URL the text should link to.

        Constraints:
        - Must be a valid URL format
        - Maximum length: 2000 characters"""
    )

@strawberry.type
class SEOOutput:
    """
    Holds the generated SEO metadata for a piece of content.

    Example:
    {
      "seo_title": "Understanding AI: A Complete Guide for Beginners",
      "meta_description": "Learn everything you need to know about artificial intelligence, from basic concepts to real-world applications."
    }
    """
    seo_title: str = strawberry.field(
        description="""The optimized title for search engine results pages (SERPs).

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 60 characters (recommended for SEO)"""
    )
    meta_description: str = strawberry.field(
        description="""The optimized meta description for SERPs.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 160 characters (recommended for SEO)"""
    )

@strawberry.type
class BlogPostOutput:
    """
    Represents a complete, finalized blog post with all its components.

    Example:
    {
      "title": "The Future of AI in Healthcare",
      "body": "# The Future of AI in Healthcare

Artificial intelligence is revolutionizing...",
      "seo_metadata": {
        "seo_title": "AI in Healthcare: Transforming Patient Care",
        "meta_description": "Discover how AI is improving diagnostics, treatment, and patient outcomes in healthcare."
      },
      "link_suggestions": [
        {
          "text": "AI ethics guidelines",
          "url": "https://example.com/ai-ethics"
        }
      ]
    }
    """
    title: str = strawberry.field(
        description="""The final title of the blog post.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 200 characters"""
    )
    body: str = strawberry.field(
        description="""The full body content of the blog post in Markdown format.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 50000 characters"""
    )
    seo_metadata: SEOOutput = strawberry.field(
        description="The SEO metadata for the blog post."
    )
    link_suggestions: List[LinkSuggestion] = strawberry.field(
        description="A list of suggested links to include in the post."
    )

@strawberry.type
class SocialMediaPostOutput:
    """
    Represents a single, finalized social media post ready for publishing.

    Example:
    {
      "platform": "Twitter",
      "post_text": "Just discovered how AI is transforming healthcare! 🤖💊 #HealthTech #AI",
      "hashtags": ["#HealthTech", "#AI"],
      "image_url": "https://example.com/ai-healthcare.jpg",
      "thread_structure": {
        "posts": [
          {"text": "Post 1 content..."},
          {"text": "Post 2 content..."}
        ]
      }
    }
    """
    platform: str = strawberry.field(
        description="""The target social media platform (e.g., 'Twitter', 'LinkedIn').

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 50 characters"""
    )
    post_text: str = strawberry.field(
        description="""The final, polished text content of the post.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 280 characters (for Twitter) to 2000 characters (for other platforms)"""
    )
    hashtags: Optional[List[str]] = strawberry.field(
        default=None,
        description="""A list of relevant hashtags for the post.

        Constraints:
        - Maximum of 30 hashtags
        - Each hashtag must follow platform guidelines"""
    )
    image_url: Optional[str] = strawberry.field(
        default=None,
        description="""URL of a relevant image, if generated or found.

        Constraints:
        - Must be a valid URL format
        - Maximum length: 2000 characters"""
    )
    thread_structure: Optional[JSON] = strawberry.field(
        default=None,
        description="""For threaded posts (like Twitter), this holds the structure.

        Format:
        {
          "posts": [
            {"text": "Post 1 content...", "image_url": "optional_url"},
            {"text": "Post 2 content...", "image_url": "optional_url"}
          ]
        }"""
    )

@strawberry.type
class GoalOutput:
    """
    A universal output structure from the Orchestrator Agent's execution.
    The 'result' field is a flexible JSON object that can hold any structured data.

    Example for successful execution:
    {
      "success": true,
      "result": {
        "type": "final",
        "data": "Here is the completed task..."
      },
      "log": "final"
    }

    Example for error:
    {
      "success": false,
      "result": {
        "type": "error",
        "data": "An error occurred while processing your request."
      },
      "log": "error"
    }
    """
    success: bool = strawberry.field(
        description="Indicates whether the goal execution was successful."
    )

    # Using strawberry.scalars.JSON for flexible JSON structure
    # This is CRITICAL for flexibility.
    result: JSON = strawberry.field(
        description="""The final output of the executed goal. This could be a string, a list,
        or a complex JSON object representing the completed work.

        For streaming execution, this field will contain intermediate results with different types:
        - {"type": "thought", "data": "..."} - Agent's reasoning process
        - {"type": "action", "data": "..."} - Agent's actions
        - {"type": "observation", "data": "..."} - Results of actions
        - {"type": "final", "data": "..."} - Final output
        - {"type": "error", "data": "..."} - Error information"""
    )

    log: Optional[str] = strawberry.field(
        default=None,
        description="""A trace or log of the Orchestrator Agent's thought process and the specialist agents it invoked.

        Possible values:
        - "thought" - Agent is thinking/reasoning
        - "action" - Agent is taking an action
        - "observation" - Agent is observing results
        - "final" - Execution completed successfully
        - "error" - An error occurred
        - "timeout" - Execution timed out
        - "validation_error" - Input validation failed"""
    )

@strawberry.type
class SupportResponse:
    """
    Represents a drafted customer support response.

    Example:
    {
      "responseText": "Thank you for contacting us about your account access issue...",
      "sentiment": "neutral",
      "orderId": "order_7890",
      "confidenceScore": 0.95
    }
    """
    responseText: str = strawberry.field(
        description="""The complete drafted support response text.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 10000 characters"""
    )

    sentiment: str = strawberry.field(
        description="""The detected sentiment of the customer's original ticket.

        Possible values:
        - "positive" - Customer is satisfied
        - "neutral" - Customer is neither satisfied nor dissatisfied
        - "negative" - Customer is dissatisfied
        - "mixed" - Customer has mixed feelings"""
    )

    orderId: Optional[str] = strawberry.field(
        default=None,
        description="""The order ID related to this support response, if applicable.

        Constraints:
        - Maximum length: 50 characters"""
    )

    confidenceScore: Optional[float] = strawberry.field(
        default=None,
        description="""Confidence score of the response quality (0.0 to 1.0).

        Interpretation:
        - 0.0-0.3: Low confidence
        - 0.3-0.7: Medium confidence
        - 0.7-1.0: High confidence"""
    )

@strawberry.type
class TenantResponse:
    """
    Represents a created tenant.

    Example:
    {
      "id": 1,
      "tenantId": "abc123def456",
      "subdomain": "acme",
      "name": "Acme Corporation",
      "adminEmail": "admin@acme.com",
      "createdAt": "2025-08-21T10:30:00Z"
    }
    """
    tenantId: str = strawberry.field(
        description="The unique identifier for the tenant."
    )

    subdomain: str = strawberry.field(
        description="The subdomain for the tenant."
    )

    name: str = strawberry.field(
        description="The display name of the tenant."
    )

    adminEmail: str = strawberry.field(
        description="The email address of the tenant administrator."
    )

    createdAt: str = strawberry.field(
        description="ISO format timestamp of when the tenant was created."
    )

    inviteToken: Optional[str] = strawberry.field(
        default=None,
        description="Single-use invite token for the tenant admin to join."
    )
    
    success: Optional[bool] = strawberry.field(
        default=None,
        description="Operation success status (for update operations)."
    )
    
    message: Optional[str] = strawberry.field(
        default=None,
        description="Operation result message (for update operations)."
    )

@strawberry.type
class ProjectType:
    """
    Represents a project workspace.

    Example:
    {
      "id": 1,
      "name": "Marketing Campaign",
      "description": "Q4 marketing campaign for new product launch",
      "createdAt": "2025-08-21T10:30:00Z",
      "userId": 1
    }
    """
    id: int = strawberry.field(
        description="The internal database ID of the project."
    )

    name: str = strawberry.field(
        description="""The name of the project.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters"""
    )

    description: str = strawberry.field(
        description="""The description of the project.

        Constraints:
        - Maximum length: 1000 characters"""
    )

    createdAt: Optional[str] = strawberry.field(
        description="ISO format timestamp of when the project was created."
    )

    userId: int = strawberry.field(
        description="The ID of the user who owns this project."
    )

@strawberry.type
class ConversationType:
    """
    Represents a conversation within a project.

    Example:
    {
      "id": 1,
      "title": "New Product Launch Discussion",
      "createdAt": "2025-08-21T10:30:00Z",
      "projectId": 1
    }
    """
    id: int = strawberry.field(
        description="The internal database ID of the conversation."
    )

    title: str = strawberry.field(
        description="""The title of the conversation.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 200 characters"""
    )

    createdAt: Optional[str] = strawberry.field(
        description="ISO format timestamp of when the conversation was created."
    )

    projectId: int = strawberry.field(
        description="The ID of the project this conversation belongs to."
    )

@strawberry.type
class ScheduledTaskType:
    """
    Represents a scheduled task.

    Example:
    {
      "id": 1,
      "tenantId": 1,
      "userId": 1,
      "projectId": 1,
      "scheduledAt": "2025-08-25T10:00:00Z",
      "status": "pending",
      "executionLog": null,
      "createdAt": "2025-08-21T10:30:00Z",
      "updatedAt": "2025-08-21T10:30:00Z"
    }
    """
    id: int = strawberry.field(
        description="The internal database ID of the scheduled task."
    )

    tenantId: int = strawberry.field(
        description="The ID of the tenant this task belongs to."
    )

    userId: int = strawberry.field(
        description="The ID of the user who created this task."
    )

    projectId: int = strawberry.field(
        description="The ID of the project this task belongs to."
    )

    scheduledAt: datetime = strawberry.field(
        description="ISO format timestamp of when the task is scheduled to run."
    )

    status: str = strawberry.field(
        description="""The status of the scheduled task.

        Possible values:
        - "pending" - Task is scheduled but not yet executed
        - "running" - Task is currently being executed
        - "completed" - Task has been successfully completed
        - "failed" - Task failed but may be retried
        - "permanently_failed" - Task failed permanently after retries"""
    )

    executionLog: Optional[str] = strawberry.field(
        default=None,
        description="Log of the task execution, including any errors."
    )

    createdAt: datetime = strawberry.field(
        description="ISO format timestamp of when the task was created."
    )

    updatedAt: datetime = strawberry.field(
        description="ISO format timestamp of when the task was last updated."
    )

@strawberry.type
class ToneProfileType:
    """
    Represents a tone profile.

    Example:
    {
      "id": 1,
      "name": "Professional",
      "profileText": "Use a formal, professional tone with proper grammar and business language.",
      "description": "Formal tone suitable for business communications",
      "isDefault": false,
      "userId": 1,
      "createdAt": "2025-08-21T10:30:00Z"
    }
    """
    id: int = strawberry.field(
        description="The internal database ID of the tone profile."
    )

    name: str = strawberry.field(
        description="""The name of the tone profile.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 100 characters"""
    )

    profileText: str = strawberry.field(
        description="""The text that describes the tone profile.

        Constraints:
        - Minimum length: 1 character
        - Maximum length: 1000 characters"""
    )

    description: Optional[str] = strawberry.field(
        default=None,
        description="""Optional description of the tone profile.

        Constraints:
        - Maximum length: 500 characters"""
    )

    isDefault: bool = strawberry.field(
        description="Whether this is a default tone profile."
    )

    userId: int = strawberry.field(
        description="The ID of the user who owns this tone profile."
    )

    createdAt: str = strawberry.field(
        description="ISO format timestamp of when the tone profile was created."
    )

    @strawberry.field
    def type(self) -> str:
        """Derived profile type for FE bridge compatibility (system_default vs user_created)."""
        return "system_default" if self.isDefault else "user_created"

@strawberry.type
class UserAuthType:
    """
    Represents user authentication information.

    Example:
    {
      "user_id": "123456789",
      "email": "user@example.com",
      "name": "John Doe",
      "provider": "google",
      "profile_picture_url": "https://example.com/profile.jpg"
    }
    """
    user_id: str = strawberry.field(
        description="OAuth provider user ID."
    )

    email: str = strawberry.field(
        description="User's email address."
    )

    name: str = strawberry.field(
        description="User's display name."
    )

    provider: str = strawberry.field(
        description="OAuth provider (google, apple, etc.)."
    )

    profile_picture_url: Optional[str] = strawberry.field(
        default=None,
        description="URL to user's profile picture."
    )

    tenant_subdomain: Optional[str] = strawberry.field(
        default=None,
        description="Subdomain of the user's tenant for redirection."
    )

@strawberry.type
class JobResponse:
    """
    Represents the immediate response from executing a goal asynchronously.

    Example:
    {
      "success": true,
      "job_id": "job_abc123xyz",
      "status": "QUEUED",
      "message": "Goal execution has been queued for processing"
    }
    """
    success: bool = strawberry.field(
        description="Indicates whether the job was successfully queued."
    )

    job_id: str = strawberry.field(
        description="Unique identifier for the job that can be used to track progress.",
        name="job_id",
    )

    status: str = strawberry.field(
        description="Current status of the job (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED)."
    )

    message: str = strawberry.field(
        description="Human-readable message about the job status."
    )

    @strawberry.field(name="jobId")
    def jobId(self) -> str:
        return self.job_id

@strawberry.type
class JobStatusUpdate:
    """
    Represents a real-time job status update delivered via GraphQL subscription.

    Example:
    {
      "job_id": "job_abc123xyz",
      "status": "RUNNING",
      "timestamp": "2025-01-08T10:00:00Z",
      "message": "Orchestrator agent initialized",
      "progress_percentage": 25,
      "current_step_description": "THOUGHT: Analyzing user requirements",
      "error_message": null,
      "additional_data": {
        "step_type": "THOUGHT",
        "model_used": "gemini-2.5-pro"
      }
    }
    """
    job_id: str = strawberry.field(
        description="The job identifier this update relates to."
    )

    status: str = strawberry.field(
        description="Current job status (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED)."
    )

    timestamp: str = strawberry.field(
        description="ISO format timestamp when this update occurred."
    )

    message: Optional[str] = strawberry.field(
        default=None,
        description="Human-readable status message."
    )

    progress_percentage: Optional[int] = strawberry.field(
        default=None,
        description="Progress percentage (0-100) if available."
    )

    current_step_description: Optional[str] = strawberry.field(
        default=None,
        description="Description of the current execution step."
    )

    error_message: Optional[str] = strawberry.field(
        default=None,
        description="Error message if the job failed."
    )

    additional_data: Optional[JSON] = strawberry.field(
        default=None,
        description="Additional structured data related to this update."
    )

@strawberry.type
class JobDetails:
    """
    Represents complete job details including execution history.

    Example:
    {
      "job_id": "job_abc123xyz",
      "status": "COMPLETED",
      "job_type": "execute_goal",
      "created_at": "2025-01-08T09:00:00Z",
      "started_at": "2025-01-08T09:01:00Z",
      "completed_at": "2025-01-08T09:15:00Z",
      "input_data": {"goal": "Create a blog post", "context": "..."},
      "output_data": {"type": "final", "data": "..."},
      "error_message": null,
      "execution_steps": [...]
    }
    """
    job_id: str = strawberry.field(
        description="Unique job identifier."
    )

    status: str = strawberry.field(
        description="Current job status."
    )

    job_type: str = strawberry.field(
        description="Type of job (e.g., execute_goal, generate_report)."
    )

    created_at: str = strawberry.field(
        description="ISO format timestamp when job was created."
    )

    started_at: Optional[str] = strawberry.field(
        default=None,
        description="ISO format timestamp when job started executing."
    )

    completed_at: Optional[str] = strawberry.field(
        default=None,
        description="ISO format timestamp when job completed."
    )

    input_data: Optional[JSON] = strawberry.field(
        default=None,
        description="The input data provided when the job was created."
    )

    output_data: Optional[JSON] = strawberry.field(
        default=None,
        description="The final output data from the job execution."
    )

    error_message: Optional[str] = strawberry.field(
        default=None,
        description="Error message if the job failed."
    )

    execution_steps: Optional[List["ExecutionStepType"]] = strawberry.field(
        default=None,
        description="List of execution steps that were performed."
    )

    threadId: Optional[str] = strawberry.field(
        default=None,
        description="Optional thread ID mapped to this job for deep-linking to chat."
    )

# ============================================================================
# THREADS AND MESSAGES OUTPUT TYPES
# ============================================================================

@strawberry.type
class ThreadType:
    """Represents a chat thread for rolling conversations."""
    threadId: str = strawberry.field(description="Stable thread identifier")
    title: Optional[str] = strawberry.field(default=None, description="Optional thread title")
    teamId: Optional[str] = strawberry.field(default=None, description="Agent team bound to this thread")
    provider: Optional[str] = strawberry.field(default=None, description="Preferred LLM provider for this thread, if any")
    model: Optional[str] = strawberry.field(default=None, description="Preferred LLM model for this thread, if any")
    createdAt: str = strawberry.field(description="ISO timestamp when created")
    lastActivityAt: Optional[str] = strawberry.field(default=None, description="ISO timestamp of last activity")

@strawberry.type
class MessageType:
    """Represents a message within a thread."""
    messageId: str = strawberry.field(description="Stable message identifier")
    threadId: str = strawberry.field(description="Parent thread identifier")
    role: str = strawberry.field(description="user|assistant|system")
    content: str = strawberry.field(description="Message content")
    parentId: Optional[str] = strawberry.field(default=None, description="Optional parent for reply trees")
    branchId: Optional[str] = strawberry.field(default=None, description="Optional branch id for alternative paths")
    createdAt: str = strawberry.field(description="ISO timestamp when created")

@strawberry.type
class ExecutionStepType:
    """
    Represents a single step in the job execution trace.

    Example:
    {
      "step_number": 1,
      "step_type": "THOUGHT",
      "timestamp": "2025-01-08T09:01:30Z",
      "thought": "I need to understand what kind of blog post the user wants...",
      "action_tool": null,
      "action_input": null,
      "observation_result": null,
      "step_cost": 0.002,
      "model_used": "gemini-2.5-pro"
    }
    """
    step_number: int = strawberry.field(
        description="Sequential step number within the job execution."
    )

    step_type: str = strawberry.field(
        description="Type of step (THOUGHT, ACTION, OBSERVATION, COST_UPDATE)."
    )

    timestamp: str = strawberry.field(
        description="ISO format timestamp when this step occurred."
    )

    thought: Optional[str] = strawberry.field(
        default=None,
        description="The orchestrator's reasoning for THOUGHT steps."
    )

    action_tool: Optional[str] = strawberry.field(
        default=None,
        description="Name of the tool called for ACTION steps."
    )

    action_input: Optional[JSON] = strawberry.field(
        default=None,
        description="Input parameters provided to the tool for ACTION steps."
    )

    observation_result: Optional[str] = strawberry.field(
        default=None,
        description="Result returned from the tool for OBSERVATION steps."
    )

    step_cost: Optional[float] = strawberry.field(
        default=None,
        description="Cost incurred by this step in USD."
    )

    model_used: Optional[str] = strawberry.field(
        default=None,
        description="AI model used for this step (e.g., gemini-2.5-pro)."
    )

# ============================================================================
# AGENT MANAGEMENT OUTPUT TYPES
# ============================================================================

@strawberry.type
class Agent:
    """
    Represents a custom AI agent.

    Example:
    {
      "id": "agent_001",
      "name": "Customer Support Agent",
      "description": "Handles customer inquiries and provides product information",
      "createdAt": "2025-01-08T10:00:00Z",
      "lastUsed": "2025-01-08T15:30:00Z",
      "status": "active",
      "agentType": "specialized",
      "capabilities": ["customer_support", "product_info"],
      "performanceMetrics": {
        "successRate": 0.95,
        "averageExecutionTime": 45.2,
        "totalExecutions": 150
      }
    }
    """
    id: str = strawberry.field(
        description="Unique identifier for the agent."
    )

    name: str = strawberry.field(
        description="Display name of the agent."
    )

    description: str = strawberry.field(
        description="Description of what the agent does."
    )

    createdAt: str = strawberry.field(
        description="ISO format timestamp when the agent was created."
    )

    lastUsed: Optional[str] = strawberry.field(
        default=None,
        description="ISO format timestamp when the agent was last used."
    )

    status: str = strawberry.field(
        description="Current status of the agent (active, inactive, training)."
    )

    agentType: str = strawberry.field(
        description="Type of agent (specialized, general, assistant)."
    )

    capabilities: List[str] = strawberry.field(
        description="List of capabilities the agent has."
    )

    performanceMetrics: Optional[JSON] = strawberry.field(
        default=None,
        description="Performance metrics for the agent."
    )

@strawberry.type
class AgentExecutionResult:
    """
    Result of executing an agent.

    Example:
    {
      "success": true,
      "result": "Customer inquiry handled successfully",
      "executionTime": 23.5,
      "cost": 0.0023
    }
    """
    success: bool = strawberry.field(
        description="Whether the agent execution was successful."
    )

    result: str = strawberry.field(
        description="The result or output from the agent execution."
    )

    executionTime: float = strawberry.field(
        description="Time taken to execute the agent in seconds."
    )

    cost: float = strawberry.field(
        description="Cost of the agent execution in USD."
    )

@strawberry.type
class CustomAgentDefinitionType:
    """
    Minimal view of a CustomAgentDefinition for creation flows.
    """
    id: str
    name: str
    version: str

@strawberry.type
class AgentTeamType:
    """
    Represents a team of custom AI agents.
    """
    id: str = strawberry.field(description="Unique identifier for the agent team (agent_team_id).")
    name: str = strawberry.field(description="Display name of the agent team.")
    description: str = strawberry.field(description="Description of what the agent team does.")
    createdAt: str = strawberry.field(description="ISO format timestamp when the agent team was created.")
    lastUpdatedAt: str = strawberry.field(description="ISO format timestamp when the agent team was last updated.")
    isActive: bool = strawberry.field(description="Whether this team is active.")
    isSystemTeam: bool = strawberry.field(description="True if this team is platform-owned and immutable.")
    version: str = strawberry.field(description="Semantic version of the agent team definition.")
    customAgentIDs: List[str] = strawberry.field(description="List of custom agent IDs in this team.")
    preApprovedToolNames: List[str] = strawberry.field(description="List of pre-approved tool names for this team.")

# ============================================================================
# INTEGRATION MANAGEMENT OUTPUT TYPES
# ============================================================================

@strawberry.type
class Integration:
    """
    Represents a third-party service integration.

    Example:
    {
      "serviceName": "slack",
      "status": "connected",
      "lastConnected": "2025-01-08T10:00:00Z",
      "errorMessage": null,
      "capabilities": ["send_message", "read_channel", "file_upload"]
    }
    """
    serviceName: str = strawberry.field(
        description="Name of the integrated service."
    )

    status: str = strawberry.field(
        description="Current status of the integration (connected, disconnected, error)."
    )

    lastConnected: Optional[str] = strawberry.field(
        default=None,
        description="ISO format timestamp when last connected."
    )

    errorMessage: Optional[str] = strawberry.field(
        default=None,
        description="Error message if integration failed."
    )

    capabilities: List[str] = strawberry.field(
        description="List of capabilities provided by this integration."
    )

@strawberry.type
class IntegrationStatus:
    """
    Status result from connecting or testing an integration.

    Example:
    {
      "serviceName": "slack",
      "status": "connected",
      "validationErrors": null
    }
    """
    serviceName: str = strawberry.field(
        description="Name of the service."
    )

    status: str = strawberry.field(
        description="Status of the integration operation."
    )

    validationErrors: Optional[List[str]] = strawberry.field(
        default=None,
        description="List of validation errors if any."
    )

@strawberry.type
class IntegrationTestResult:
    """
    Result from testing an integration connection.

    Example:
    {
      "success": true,
      "testResult": "Successfully connected to Slack API",
      "errorMessage": null
    }
    """
    success: bool = strawberry.field(
        description="Whether the integration test was successful."
    )

    testResult: str = strawberry.field(
        description="Description of the test result."
    )

    errorMessage: Optional[str] = strawberry.field(
        default=None,
        description="Error message if test failed."
    )

# ============================================================================
# MCP TOOL OUTPUT TYPES
# ============================================================================

@strawberry.type
class MCPTool:
    """
    Represents an MCP (Model Context Protocol) tool.

    Example:
    {
      "name": "mcp_slack",
      "description": "Send messages and interact with Slack",
      "category": "communication",
      "requiredCredentials": ["bot_token"],
      "capabilities": ["send_message", "read_channel", "file_upload"],
      "status": "available"
    }
    """
    name: str = strawberry.field(
        description="Unique name of the MCP tool."
    )

    description: str = strawberry.field(
        description="Description of what the tool does."
    )

    category: str = strawberry.field(
        description="Category of the tool (communication, productivity, etc)."
    )

    requiredCredentials: List[str] = strawberry.field(
        description="List of required credential fields."
    )

    capabilities: List[str] = strawberry.field(
        description="List of capabilities the tool provides."
    )

    status: str = strawberry.field(
        description="Current status of the tool (available, connected, error)."
    )

@strawberry.type
class MCPToolResult:
    """
    Result from executing an MCP tool.

    Example:
    {
      "success": true,
      "result": "Message sent successfully",
      "executionTime": 1.2,
      "errorMessage": null,
      "toolOutput": {"message_id": "1234567890.123456", "channel": "C1234567890"}
    }
    """
    success: bool = strawberry.field(
        description="Whether the MCP tool execution was successful."
    )

    result: str = strawberry.field(
        description="Human-readable result description."
    )

    executionTime: float = strawberry.field(
        description="Time taken to execute the tool in seconds."
    )

    errorMessage: Optional[str] = strawberry.field(
        default=None,
        description="Error message if execution failed."
    )

    toolOutput: Optional[JSON] = strawberry.field(
        default=None,
        description="Raw output from the MCP tool."
    )

@strawberry.type
class MCPCredentialStatus:
    """
    Status result from managing MCP tool credentials.

    Example:
    {
      "success": true,
      "validationErrors": null
    }
    """
    success: bool = strawberry.field(
        description="Whether the credential management was successful."
    )

    validationErrors: Optional[List[str]] = strawberry.field(
        default=None,
        description="List of validation errors if any."
    )

@strawberry.type
class MCPToolTestResult:
    """
    Result from testing MCP tool credentials.

    Example:
    {
      "success": true,
      "testResult": "Slack credentials are valid",
      "errorMessage": null
    }
    """
    success: bool = strawberry.field(
        description="Whether the MCP tool test was successful."
    )

    testResult: str = strawberry.field(
        description="Description of the test result."
    )

    errorMessage: Optional[str] = strawberry.field(
        default=None,
        description="Error message if test failed."
    )

# ============================================================================
# JOB HISTORY OUTPUT TYPES
# ============================================================================

@strawberry.type
class JobHistoryItem:
    """
    Represents a single job in the history.

    Example:
    {
      "id": "job_001",
      "goal": "Analyze customer sentiment from social media data",
      "status": "completed",
      "createdAt": "2025-01-08T10:00:00Z",
      "completedAt": "2025-01-08T12:15:00Z",
      "duration": "2h 15m",
      "totalCost": "$12.50",
      "modelUsed": "gemini-2.5-pro",
      "tokenCount": 15420,
      "successRate": 0.95
    }
    """
    id: str = strawberry.field(
        description="Unique job identifier."
    )

    goal: str = strawberry.field(
        description="The goal that was executed."
    )

    status: str = strawberry.field(
        description="Current status of the job."
    )

    createdAt: str = strawberry.field(
        description="ISO format timestamp when job was created."
    )

    completedAt: Optional[str] = strawberry.field(
        default=None,
        description="ISO format timestamp when job completed."
    )

    duration: str = strawberry.field(
        description="Human-readable duration of the job."
    )

    totalCost: str = strawberry.field(
        description="Total cost of the job execution."
    )

    modelUsed: Optional[str] = strawberry.field(
        default=None,
        description="AI model used for the job."
    )

    tokenCount: Optional[int] = strawberry.field(
        default=None,
        description="Total number of tokens processed."
    )

    successRate: Optional[float] = strawberry.field(
        default=None,
        description="Success rate of the job (0.0-1.0)."
    )

    threadId: Optional[str] = strawberry.field(
        default=None,
        description="Optional thread ID mapped to this job for deep-linking to chat."
    )

@strawberry.type
class JobHistoryPageInfo:
    """
    Pagination information for job history.

    Example:
    {
      "hasNextPage": true,
      "hasPreviousPage": false
    }
    """
    hasNextPage: bool = strawberry.field(
        description="Whether there are more jobs after the current page."
    )

    hasPreviousPage: bool = strawberry.field(
        description="Whether there are jobs before the current page."
    )

@strawberry.type
class JobHistory:
    """
    Paginated job history results.

    Example:
    {
      "jobs": [...],
      "totalCount": 150,
      "pageInfo": {
        "hasNextPage": true,
        "hasPreviousPage": false
      }
    }
    """
    jobs: List[JobHistoryItem] = strawberry.field(
        description="List of jobs for the current page."
    )

    totalCount: int = strawberry.field(
        description="Total number of jobs matching the filter."
    )

    pageInfo: JobHistoryPageInfo = strawberry.field(
        description="Pagination information."
    )

# ============================================================================
# TONE PROFILE OUTPUT TYPES
# ============================================================================

@strawberry.type
class ToneProfile:
    """
    Represents a tone profile for AI responses.

    Example:
    {
      "id": "profile_001",
      "name": "Professional",
      "type": "system_default",
      "description": "Formal, professional tone for business communications",
      "usageCount": 45,
      "lastUsed": "2025-01-08T14:30:00Z",
      "effectiveness": 0.92
    }
    """
    id: str = strawberry.field(
        description="Unique identifier for the tone profile."
    )

    name: str = strawberry.field(
        description="Display name of the tone profile."
    )

    type: str = strawberry.field(
        description="Type of profile (system_default, user_created)."
    )

    description: str = strawberry.field(
        description="Description of the tone profile."
    )

    usageCount: int = strawberry.field(
        description="Number of times this profile has been used."
    )

    lastUsed: Optional[str] = strawberry.field(
        default=None,
        description="ISO format timestamp when last used."
    )

    effectiveness: Optional[float] = strawberry.field(
        default=None,
        description="Effectiveness score based on user feedback (0.0-1.0)."
    )
