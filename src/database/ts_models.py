from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List, Dict, Any
from datetime import datetime
import secrets
import string
import json
from pydantic import field_validator

class Tenant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(unique=True, index=True)  # 13-character unique identifier (URL-safe)
    subdomain: str = Field(unique=True, index=True)  # Unique subdomain name
    name: str  # Tenant display name
    admin_email: str  # Administrator email
    default_retention_policy_days: int = Field(default=365, index=True)
    is_active: bool = Field(default=True, index=True)  # Whether tenant is active
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    users: List["User"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    projects: List["Project"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    tone_profiles: List["ToneProfile"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    expenses: List["Expense"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    conversations: List["Conversation"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    kb_files: List["ProjectKBFile"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    messages: List["Message"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    execution_costs: List["ExecutionCost"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    jobs: List["Job"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    custom_agents: List["CustomAgentDefinition"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    agent_teams: List["AgentTeam"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})
    execution_trace_steps: List["ExecutionTraceStep"] = Relationship(sa_relationship_kwargs={"lazy": "select"})
    user_observations: List["UserObservation"] = Relationship(back_populates="tenant", sa_relationship_kwargs={"lazy": "select"})


    @staticmethod
    def generate_unique_id(length: int = 13) -> str:
        """Generate a unique URL-safe identifier."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(unique=True, index=True)  # This will be the OAuth user identifier
    email: Optional[str] = Field(default=None, index=True)  # Email for authentication
    name: Optional[str] = Field(default=None)  # User's display name
    profile_picture_url: Optional[str] = Field(default=None)  # URL to profile picture
    provider: str = Field(default="google")  # OAuth provider (google, apple, etc.)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = Field(default=None)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant
    is_active: bool = Field(default=True)  # Whether user account is active
    is_admin: bool = Field(default=False)  # Whether user has admin privileges
    updated_at: Optional[datetime] = Field(default=None)  # Last update timestamp
    password_hash: Optional[str] = Field(default=None)  # Password hash for non-OAuth users

    # Relationships
    tenant: Tenant = Relationship(back_populates="users")
    projects: List["Project"] = Relationship(back_populates="user")
    tone_profiles: List["ToneProfile"] = Relationship(back_populates="user")
    expenses: List["Expense"] = Relationship(back_populates="user")
    jobs: List["Job"] = Relationship(back_populates="user")
    user_observations: List["UserObservation"] = Relationship(back_populates="user")

class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = Field(default="")  # Add description field
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: int = Field(foreign_key="user.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant

    # Relationships
    user: User = Relationship(back_populates="projects")
    tenant: Tenant = Relationship(back_populates="projects")
    conversations: List["Conversation"] = Relationship(back_populates="project")
    kb_files: List["ProjectKBFile"] = Relationship(back_populates="project")

class ToneProfile(SQLModel, table=True, extend_existing=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    profile_text: str
    description: Optional[str] = Field(default=None)
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: int = Field(foreign_key="user.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant

    # Relationships
    user: User = Relationship(back_populates="tone_profiles")
    tenant: Tenant = Relationship(back_populates="tone_profiles")

class Conversation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(default="")  # Add title field
    created_at: datetime = Field(default_factory=datetime.utcnow)
    project_id: int = Field(foreign_key="project.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant

    # Relationships
    project: Project = Relationship(back_populates="conversations")
    tenant: Tenant = Relationship(back_populates="conversations")
    messages: List["Message"] = Relationship(back_populates="conversation")

class ProjectKBFile(SQLModel, table=True, extend_existing=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    file_name: str
    file_uri: str
    file_size: int = Field(default=0)
    mime_type: str = Field(default="application/octet-stream")
    status: str = Field(default="processing")  # processing, available, failed
    error_message: Optional[str] = Field(default=None)
    retention_policy_days: int = Field(default=365, index=True)
    archive_after: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    project_id: int = Field(foreign_key="project.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant

    # Relationships
    project: Project = Relationship(back_populates="kb_files")
    tenant: Tenant = Relationship(back_populates="kb_files")

class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str  # 'user', 'assistant', 'system'
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant

    # Relationships
    conversation: Conversation = Relationship(back_populates="messages")
    tenant: Tenant = Relationship(back_populates="messages")

class Expense(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vendor_name: str
    transaction_date: datetime
    total_amount: float
    tax_amount: Optional[float] = Field(default=None)
    currency: str
    category: Optional[str] = Field(default=None, index=True)
    raw_document_uri: Optional[str] = Field(default=None)
    user_id: int = Field(foreign_key="user.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant

    # Relationships
    user: User = Relationship(back_populates="expenses")
    tenant: Tenant = Relationship(back_populates="expenses")

class ExecutionCost(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    step_name: str  # e.g., "Specialist: drafting_agent"
    model_used: str
    input_tokens: int
    output_tokens: int
    step_cost: float  # Cost in USD
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    tenant: Tenant = Relationship(back_populates="execution_costs")


class CreditLedger(SQLModel, table=True):
    __tablename__ = "credit_ledger"
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    job_id: Optional[str] = Field(default=None, index=True)
    source: str  # DEDUCTION|PAYMENT|REFUND|FREE_GRANT|ADJUSTMENT
    credits_delta: int  # positive or negative; negative for deductions
    usd_amount: Optional[float] = Field(default=None)
    payment_reference: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships (optional minimal backrefs)
    tenant: Tenant = Relationship(back_populates=None)
    user: User = Relationship(back_populates=None)


class StripeEvent(SQLModel, table=True):
    __tablename__ = "stripe_event"
    event_id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TenantCreditBalance(SQLModel, table=True):
    __tablename__ = "tenant_credit_balance"
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    balance_credits: int = Field(default=0)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserObservation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)

    # Communication Preferences
    preferred_tone: str = Field(default="")  # formal, casual, technical, friendly
    response_length_preference: str = Field(default="")  # concise, detailed, comprehensive
    technical_level: str = Field(default="")  # beginner, intermediate, expert
    formality_level: str = Field(default="")  # high, medium, low

    # Personality & Behavior
    patience_level: str = Field(default="")  # high, medium, low
    detail_orientation: str = Field(default="")  # high, medium, low
    risk_tolerance: str = Field(default="")  # conservative, balanced, aggressive
    decision_making_style: str = Field(default="")  # analytical, intuitive, collaborative

    # Success Patterns
    successful_tools: str = Field(default="")  # JSON list of preferred tools
    successful_approaches: str = Field(default="")  # JSON list of what works
    failed_approaches: str = Field(default="")  # JSON list of what to avoid
    learning_style: str = Field(default="")  # visual, hands-on, theoretical

    # Behavioral Patterns
    peak_activity_hours: str = Field(default="")  # JSON time preferences
    response_time_expectations: str = Field(default="")  # immediate, same-day, relaxed
    follow_up_frequency: str = Field(default="")  # never, occasional, regular

    # Content Preferences
    complexity_level: str = Field(default="")  # simple, moderate, complex
    example_requirements: str = Field(default="")  # none, some, extensive
    visual_vs_text: str = Field(default="")  # text-heavy, balanced, visual

    # Emotional & Success Metrics
    frustration_triggers: str = Field(default="")  # JSON list
    motivation_factors: str = Field(default="")  # JSON list
    stress_patterns: str = Field(default="")  # JSON list
    completion_rates_by_task_type: str = Field(default="")  # JSON stats

    # Metadata
    observation_count: int = Field(default=0)
    last_observation_at: Optional[datetime] = Field(default=None)
    confidence_score: float = Field(default=0.0)  # How reliable are these observations
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: User = Relationship(back_populates="user_observations")
    tenant: Tenant = Relationship(back_populates="user_observations")

    # JSON field helper methods
    def set_json_field(self, field_name: str, data: Any) -> None:
        """Helper method to set JSON data in string fields"""
        if hasattr(self, field_name):
            setattr(self, field_name, json.dumps(data))

    def get_json_field(self, field_name: str, default: Any = None) -> Any:
        """Helper method to get JSON data from string fields"""
        if hasattr(self, field_name):
            field_value = getattr(self, field_name)
            if field_value:
                try:
                    return json.loads(field_value)
                except json.JSONDecodeError:
                    return default or []
            return default or []
        return default or []

    def update_successful_tools(self, tools: List[str]) -> None:
        """Update successful tools list"""
        self.set_json_field('successful_tools', tools)

    def get_successful_tools(self) -> List[str]:
        """Get successful tools list"""
        return self.get_json_field('successful_tools', [])

    def update_successful_approaches(self, approaches: List[str]) -> None:
        """Update successful approaches list"""
        self.set_json_field('successful_approaches', approaches)

    def get_successful_approaches(self) -> List[str]:
        """Get successful approaches list"""
        return self.get_json_field('successful_approaches', [])

    def update_failed_approaches(self, approaches: List[str]) -> None:
        """Update failed approaches list"""
        self.set_json_field('failed_approaches', approaches)

    def get_failed_approaches(self) -> List[str]:
        """Get failed approaches list"""
        return self.get_json_field('failed_approaches', [])

    def update_peak_activity_hours(self, hours: Dict[str, Any]) -> None:
        """Update peak activity hours"""
        self.set_json_field('peak_activity_hours', hours)

    def get_peak_activity_hours(self) -> Dict[str, Any]:
        """Get peak activity hours"""
        return self.get_json_field('peak_activity_hours', {})

    def update_frustration_triggers(self, triggers: List[str]) -> None:
        """Update frustration triggers list"""
        self.set_json_field('frustration_triggers', triggers)

    def get_frustration_triggers(self) -> List[str]:
        """Get frustration triggers list"""
        return self.get_json_field('frustration_triggers', [])

    def update_motivation_factors(self, factors: List[str]) -> None:
        """Update motivation factors list"""
        self.set_json_field('motivation_factors', factors)

    def get_motivation_factors(self) -> List[str]:
        """Get motivation factors list"""
        return self.get_json_field('motivation_factors', [])

    def update_stress_patterns(self, patterns: List[str]) -> None:
        """Update stress patterns list"""
        self.set_json_field('stress_patterns', patterns)

    def get_stress_patterns(self) -> List[str]:
        """Get stress patterns list"""
        return self.get_json_field('stress_patterns', [])

    def update_completion_rates(self, rates: Dict[str, float]) -> None:
        """Update completion rates by task type"""
        self.set_json_field('completion_rates_by_task_type', rates)

    def get_completion_rates(self) -> Dict[str, float]:
        """Get completion rates by task type"""
        return self.get_json_field('completion_rates_by_task_type', {})

    def increment_observation_count(self) -> None:
        """Increment observation count and update timestamp"""
        self.observation_count += 1
        self.last_observation_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def update_confidence_score(self, new_confidence: float = None) -> None:
        """Update confidence score based on observation count and consistency"""
        if new_confidence is not None:
            self.confidence_score = new_confidence
        else:
            # Simple confidence calculation based on observation count
            if self.observation_count < 5:
                self.confidence_score = min(0.3 + (self.observation_count * 0.1), 0.7)
            else:
                self.confidence_score = min(0.8 + (self.observation_count * 0.02), 1.0)
        self.updated_at = datetime.utcnow()

    @field_validator('confidence_score')
    def validate_confidence_score(cls, v):
        """Ensure confidence score is between 0 and 1"""
        if v < 0 or v > 1:
            raise ValueError('Confidence score must be between 0 and 1')
        return v


class TenantInvite(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(unique=True, index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    email: str = Field(index=True)
    expires_at: datetime = Field(index=True)
    used_at: Optional[datetime] = Field(default=None, index=True)
    created_by_user_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    tenant: Tenant = Relationship(back_populates=None)


class IPAddressUsage(SQLModel, table=True):
    """Tracks usage of hashed client IPs for critical actions.

    Purposes:
    - 'tenant_create': creating a new tenant
    - 'account_signup': creating a new user account

    We store a salted hash of the IP (see utils.ip_utils.hash_ip) to avoid
    keeping raw IPs while still enforcing uniqueness.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    ip_hash: str = Field(index=True)
    purpose: str = Field(index=True)
    tenant_id: Optional[int] = Field(default=None, index=True)
    user_id: Optional[int] = Field(default=None, index=True)
    count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    blocked_reason: Optional[str] = Field(default=None)


# Import the new models at the end to avoid circular imports
from .models.job import Job, JobStatus
from .models.execution_trace import ExecutionTraceStep, StepType
from .models.tool import Tool, ToolStatus
from .models.custom_agent import CustomAgentDefinition
from .models.agent_team import AgentTeam
