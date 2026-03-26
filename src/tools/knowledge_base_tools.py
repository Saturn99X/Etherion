from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from sqlmodel import select

from src.database.db import get_scoped_session
from src.database.models import Feedback


@tool
async def search_user_feedback_history(
    query: str,
    *,
    tenant_id: int,
    user_id: Optional[int] = None,
    limit: int = 10,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Search recent user feedback entries for a query string."""
    q = (query or "").strip()
    if not q:
        raise ValueError("search_user_feedback_history requires 'query'.")
    if limit <= 0:
        limit = 10

    results: List[Dict[str, Any]] = []
    try:
        async with get_scoped_session() as session:
            stmt = select(Feedback).where(Feedback.tenant_id == int(tenant_id))
            if user_id is not None:
                stmt = stmt.where(Feedback.user_id == int(user_id))
            stmt = stmt.order_by(Feedback.created_at.desc()).limit(int(limit))
            rows = await session.exec(stmt)
            for fb in rows.all() or []:
                blob = " ".join(
                    [
                        str(fb.goal_text or ""),
                        str(fb.final_output_text or ""),
                        str(fb.comment_text or ""),
                    ]
                ).lower()
                if q.lower() not in blob:
                    continue
                results.append(
                    {
                        "job_id": fb.job_id,
                        "score": fb.score,
                        "comment": fb.comment_text,
                        "created_at": fb.created_at.isoformat() if getattr(fb, "created_at", None) else None,
                    }
                )
    except Exception as e:
        return {"query": q, "results": [], "provider": "feedback", "error": str(e)}

    return {"query": q, "results": results, "provider": "feedback"}
