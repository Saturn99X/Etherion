from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Feedback(SQLModel, table=True):
    """
    Feedback model for storing anonymized user feedback.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    user_id: int = Field(index=True)
    job_id: str = Field(index=True)
    score: int = Field(index=True, description="1-5 rating")
    goal_text: Optional[str] = Field(default=None, description="Anonymized goal text")
    final_output_text: Optional[str] = Field(default=None, description="Anonymized final output text")
    comment_text: Optional[str] = Field(default=None, description="Anonymized feedback comment")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


