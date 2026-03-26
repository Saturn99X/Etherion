from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any, Optional


class FailureReport(BaseModel):
    last_thought: str
    last_action: str
    observation: str
    trace: str  # JSON string of the execution trace (no secrets/PII)
    reason: str
    job_id: str
    tenant_id: int
    created_at: datetime = datetime.utcnow()


class SpecialistAgentInput(BaseModel):
    """Input model for specialist agents."""
    original_user_goal: str
    orchestrator_plan: str
    research_findings: Dict[str, Any]
    specific_instruction: str
    pitfalls_to_avoid: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
