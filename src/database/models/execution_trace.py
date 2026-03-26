from __future__ import annotations
from sqlmodel import SQLModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)

class StepType(str, Enum):
    THOUGHT = "THOUGHT"
    ACTION = "ACTION"
    OBSERVATION = "OBSERVATION"
    COST_UPDATE = "COST_UPDATE"

class ExecutionTraceStep(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)  # Store job_id string directly, not FK to job table
    tenant_id: int = Field(foreign_key="tenant.id", index=True)  # Foreign key to Tenant
    step_number: int = Field(index=True)  # Incremental counter within job
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    step_type: StepType = Field(index=True)

    # Step content fields
    thought: Optional[str] = Field(default=None)  # Orchestrator's reasoning
    action_tool: Optional[str] = Field(default=None)  # Tool name called
    action_input: Optional[str] = Field(default=None)  # JSON string for tool input
    observation_result: Optional[str] = Field(default=None)  # Tool output/result

    # New fields for full fidelity replay
    thread_id: Optional[str] = Field(default=None, index=True)
    message_id: Optional[str] = Field(default=None, index=True)
    actor: str = Field(default="orchestrator", index=True)
    event_type: str = Field(default="unknown", index=True)
    span_id: Optional[str] = Field(default=None)
    parent_span_id: Optional[str] = Field(default=None)

    # Cost and model tracking
    step_cost: Optional[Decimal] = Field(default=None, decimal_places=6)
    model_used: Optional[str] = Field(default=None)  # e.g., "gemini-2.5-pro"

    # Additional data
    raw_data: Optional[str] = Field(default=None)  # JSON string for extra context

    # Observation recording attributes
    _observation_service = None
    _user_id = None
    _record_observations = False

    def set_action_input(self, data: Dict[str, Any]) -> None:
        """Set action input as JSON string."""
        self.action_input = json.dumps(data) if data else None

    def get_action_input(self) -> Optional[Dict[str, Any]]:
        """Get action input as Python dict."""
        return json.loads(self.action_input) if self.action_input else None

    def set_raw_data(self, data: Dict[str, Any]) -> None:
        """Set raw data as JSON string."""
        self.raw_data = json.dumps(data) if data else None

    def get_raw_data(self) -> Optional[Dict[str, Any]]:
        """Get raw data as Python dict."""
        return json.loads(self.raw_data) if self.raw_data else None

    @classmethod
    def enable_observation_recording(cls, user_id: int, tenant_id: int):
        """Enable observation recording for this execution trace step."""
        try:
            from src.services.user_observation_service import get_user_observation_service
            cls._observation_service = get_user_observation_service()
            cls._user_id = user_id
            cls._record_observations = True
            logger.info(f"Enabled observation recording for user {user_id} in tenant {tenant_id}")
        except Exception as e:
            logger.warning(f"Failed to enable observation recording: {e}")
            cls._record_observations = False

    @classmethod
    def disable_observation_recording(cls):
        """Disable observation recording."""
        cls._observation_service = None
        cls._user_id = None
        cls._record_observations = False

    def record_observation(self, observation_data: Dict[str, Any]) -> None:
        """Record an observation for this execution step."""
        if not self._record_observations or not self._observation_service or not self._user_id:
            return

        try:
            # Enhance observation data with execution trace information
            enhanced_data = {
                **observation_data,
                'execution_step_id': self.id,
                'step_type': self.step_type.value,
                'step_number': self.step_number,
                'tools_used': [self.action_tool] if self.action_tool else [],
                'execution_time': (datetime.utcnow() - self.timestamp).total_seconds()
            }

            # Record the observation asynchronously
            if self._observation_service:
                # Use a background task to avoid blocking
                import asyncio
                from src.core.celery import celery_app

                @celery_app.task
                def record_observation_task(user_id: int, tenant_id: int, data: Dict[str, Any]):
                    try:
                        service = get_user_observation_service()
                        service.record_interaction(user_id, tenant_id, data)
                    except Exception as e:
                        logger.error(f"Failed to record observation in background: {e}")

                # Schedule the observation recording
                record_observation_task.delay(self._user_id, self.tenant_id, enhanced_data)

        except Exception as e:
            logger.warning(f"Failed to record observation for step {self.id}: {e}")

    def after_creation(self) -> None:
        """Called after the execution trace step is created."""
        if not self._record_observations:
            return

        # Record basic observation about step creation
        observation_data = {
            'response_content': f"Execution step {self.step_type.value} created",
            'success_indicators': {'success': True},
            'tools_used': [self.action_tool] if self.action_tool else [],
            'approaches_used': ['execution_trace_step'],
            'response_time': 0,
            'follow_up_count': 0,
            'content': f"Step {self.step_number}: {self.thought or self.action_tool or 'Unknown'}"
        }

        self.record_observation(observation_data)

    def after_completion(self, success: bool, output: str = "") -> None:
        """Called after the execution step is completed."""
        if not self._record_observations:
            return

        # Record completion observation
        observation_data = {
            'response_content': output,
            'success_indicators': {'success': success},
            'tools_used': [self.action_tool] if self.action_tool else [],
            'approaches_used': ['execution_trace_completion'],
            'response_time': (datetime.utcnow() - self.timestamp).total_seconds(),
            'follow_up_count': 0,
            'content': f"Step {self.step_number} completion: {'Success' if success else 'Failed'}"
        }

        self.record_observation(observation_data)

    class Config:
        arbitrary_types_allowed = True
