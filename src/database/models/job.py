from __future__ import annotations
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List, Dict, Any
from datetime import datetime
import secrets
import string
import json
from enum import Enum

from src.database.ts_models import Tenant, User

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PENDING_APPROVAL = "PENDING_APPROVAL"

class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(unique=True, index=True)  # URL-safe unique identifier
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant
    user_id: int = Field(foreign_key="user.id", index=True)  # Foreign key to User
    status: JobStatus = Field(default=JobStatus.QUEUED, index=True)
    job_type: str = Field(index=True)  # e.g., "execute_goal", "generate_report"
    input_data: Optional[str] = Field(default=None)  # JSON string for input data
    output_data: Optional[str] = Field(default=None)  # JSON string for output data
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = Field(default=None)
    job_metadata: Optional[str] = Field(default=None)  # JSON string for metadata
    thread_id: Optional[str] = Field(default=None, index=True)  # FK to thread table (logical)
    expires_at: Optional[datetime] = Field(default=None, index=True)  # Global job timeout
    trace_data_uri: Optional[str] = Field(default=None)  # GCS URI for execution trace archive

    # Relationships
    # Use concrete Tenant/User classes to avoid string-based resolution issues
    tenant: Tenant = Relationship(back_populates="jobs", sa_relationship_kwargs={"lazy": "select"})
    user: User = Relationship(back_populates="jobs", sa_relationship_kwargs={"lazy": "select"})

    @staticmethod
    def generate_job_id(length: int = 16) -> str:
        """Generate a unique URL-safe job identifier."""
        alphabet = string.ascii_letters + string.digits + '-_'
        return 'job_' + ''.join(secrets.choice(alphabet) for _ in range(length))

    def set_input_data(self, data: Dict[str, Any]) -> None:
        """Set input data as JSON string."""
        self.input_data = json.dumps(data) if data else None

    def get_input_data(self) -> Optional[Dict[str, Any]]:
        """Get input data as Python dict."""
        return json.loads(self.input_data) if self.input_data else None

    def set_output_data(self, data: Dict[str, Any]) -> None:
        """Set output data as JSON string."""
        self.output_data = json.dumps(data, default=str) if data else None

    def get_output_data(self) -> Optional[Dict[str, Any]]:
        """Get output data as Python dict."""
        return json.loads(self.output_data) if self.output_data else None

    def set_job_metadata(self, data: Dict[str, Any]) -> None:
        """Set job metadata as JSON string."""
        self.job_metadata = json.dumps(data) if data else None

    def get_job_metadata(self) -> Optional[Dict[str, Any]]:
        """Get job metadata as Python dict."""
        return json.loads(self.job_metadata) if self.job_metadata else None

    def update_status(self, new_status: JobStatus) -> None:
        """Update job status and relevant timestamps."""
        old_status = self.status
        self.status = new_status
        self.last_updated_at = datetime.utcnow()

        if new_status == JobStatus.RUNNING and old_status == JobStatus.QUEUED:
            self.started_at = datetime.utcnow()
        elif new_status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            if not self.completed_at:
                self.completed_at = datetime.utcnow()
