from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class Thread(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True, unique=True)
    tenant_id: int = Field(index=True, foreign_key="tenant.id")
    team_id: Optional[str] = Field(default=None, index=True)
    title: Optional[str] = Field(default=None)
    provider: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    tone_profile_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_activity_at: Optional[datetime] = Field(default=None, index=True)

class ThreadMessage(SQLModel, table=True):
    __tablename__ = "message"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: str = Field(index=True, unique=True)
    thread_id: str = Field(index=True, foreign_key="thread.thread_id")
    role: str = Field(description="user|assistant|system")
    content: str
    parent_id: Optional[str] = Field(default=None, index=True)
    branch_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    metadata_json: Optional[str] = Field(default=None)

class MessageArtifact(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: str = Field(index=True, foreign_key="message.message_id")
    kind: str = Field(description="e.g., image, file, code")
    payload_ref: Optional[str] = Field(default=None, description="GCS URI or pointer")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

class ToolInvocation(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    invocation_id: str = Field(index=True, unique=True)
    thread_id: str = Field(index=True, foreign_key="thread.thread_id")
    message_id: Optional[str] = Field(default=None, foreign_key="message.message_id")
    tool: str = Field(index=True)
    params_json: Optional[str] = Field(default=None)
    status: str = Field(default="PENDING", index=True)
    result_json: Optional[str] = Field(default=None)
    cost: Optional[float] = Field(default=None)
    timings: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
