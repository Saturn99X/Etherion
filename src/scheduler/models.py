# src/scheduler/models.py
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class ScheduledTask(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id")
    user_id: int = Field(foreign_key="user.id")
    project_id: int = Field(foreign_key="project.id")
    goal_input: str  # JSON string of the GoalInput
    scheduled_at: datetime
    status: str = Field(default="pending")  # pending, running, completed, failed, permanently_failed
    execution_log: Optional[str] = Field(default=None)
    celery_task_id: Optional[str] = Field(default=None)
    last_execution_result: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)