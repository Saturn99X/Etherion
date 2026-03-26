import json
import logging
import sys
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal

from src.database.db import get_scoped_session
from src.database.models import ExecutionTraceStep, StepType
from sqlmodel import select, func

logger = logging.getLogger(__name__)


def _log_replay(job_id: str, event_type: str, message: str, **kwargs):
    """Log replay service event to stdout for observability."""
    ts = datetime.utcnow().isoformat()
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None) if kwargs else ""
    log_line = f"[REPLAY] ts={ts} job_id={job_id} type={event_type} | {message}"
    if extra:
        log_line += f" | {extra}"
    print(log_line, file=sys.stdout, flush=True)


def _safe_json_dumps(obj: Any) -> Optional[str]:
    """Safely serialize object to JSON, falling back to repr() for non-serializable types."""
    if obj is None:
        return None
    
    class SafeEncoder(json.JSONEncoder):
        def default(self, o):
            # Handle common non-serializable types
            if hasattr(o, '__dict__'):
                return {"__type__": type(o).__name__, "__repr__": repr(o)[:500]}
            try:
                return str(o)
            except Exception:
                return f"<unserializable: {type(o).__name__}>"
    
    try:
        return json.dumps(obj, cls=SafeEncoder)
    except Exception as e:
        logger.warning(f"JSON serialization failed, using fallback: {e}")
        return json.dumps({"__serialization_error__": str(e), "__repr__": repr(obj)[:500]})

class ReplayService:
    """
    Service to handle full-fidelity execution trace persistence in Postgres.
    """

    async def record_step(
        self,
        job_id: str,
        tenant_id: int,
        actor: str,
        event_type: str,
        step_type: StepType = StepType.OBSERVATION,
        thought: Optional[str] = None,
        action_tool: Optional[str] = None,
        action_input: Optional[Dict[str, Any]] = None,
        observation_result: Optional[str] = None,
        step_cost: Optional[Decimal] = None,
        model_used: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        message_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> Optional[ExecutionTraceStep]:
        """
        Record a single execution trace step to the database.
        """
        try:
            async with get_scoped_session() as session:
                # Determine next step number
                # Use a plain SQLAlchemy text query or properly typed select for max
                from sqlalchemy import text
                stmt = text("SELECT COALESCE(MAX(step_number), 0) FROM executiontracestep WHERE job_id = :job_id")
                result = await session.execute(stmt, {"job_id": job_id})
                max_step = result.scalar() or 0
                step_number = max_step + 1

                # LOG: Recording step
                _log_replay(job_id, "RECORD_STEP", f"Recording step {step_number}",
                            actor=actor, event_type=event_type, step_type=str(step_type),
                            action_tool=action_tool, thought_preview=str(thought)[:100] if thought else None)

                step = ExecutionTraceStep(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    step_number=step_number,
                    timestamp=datetime.utcnow(),
                    step_type=step_type,
                    thought=thought,
                    action_tool=action_tool,
                    action_input=_safe_json_dumps(action_input),
                    observation_result=observation_result,
                    step_cost=step_cost,
                    model_used=model_used,
                    raw_data=_safe_json_dumps(raw_data),
                    thread_id=thread_id,
                    message_id=message_id,
                    actor=actor,
                    event_type=event_type,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                )
                session.add(step)
                # Session commit is handled by get_scoped_session context manager
                return step
        except Exception as e:
            _log_replay(job_id, "RECORD_STEP_ERROR", f"Failed to record step: {e}",
                        actor=actor, event_type=event_type)
            logger.error(f"Failed to record execution trace step for job {job_id}: {e}")
            # Do not raise to avoid breaking the orchestrator
            return None

    async def record_llm_request(
        self,
        job_id: str,
        tenant_id: int,
        actor: str,
        input_messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        thread_id: Optional[str] = None,
        message_id: Optional[str] = None,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[ExecutionTraceStep]:
        """Record LLM request turn."""
        _log_replay(job_id, "LLM_REQUEST", f"Recording LLM request",
                    actor=actor, model=model, message_count=len(input_messages) if input_messages else 0)
        raw_data = {
            "langchain": {
                "input_messages": input_messages,
                "model": model,
            },
            "runtime": runtime_context or {},
        }
        return await self.record_step(
            job_id=job_id,
            tenant_id=tenant_id,
            actor=actor,
            event_type="llm_request",
            step_type=StepType.THOUGHT,
            model_used=model,
            raw_data=raw_data,
            thread_id=thread_id,
            message_id=message_id,
        )

    async def record_llm_response(
        self,
        job_id: str,
        tenant_id: int,
        actor: str,
        output_message: Dict[str, Any],
        token_usage: Optional[Dict[str, int]] = None,
        model: Optional[str] = None,
        thread_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Optional[ExecutionTraceStep]:
        """Record LLM response turn."""
        _log_replay(job_id, "LLM_RESPONSE", f"Recording LLM response",
                    actor=actor, model=model,
                    tokens_in=token_usage.get("input_tokens") if token_usage else None,
                    tokens_out=token_usage.get("output_tokens") if token_usage else None)
        raw_data = {
            "langchain": {
                "output_message": output_message,
                "token_usage": token_usage or {},
            }
        }
        # Extract thought if possible
        thought = output_message.get("content") if isinstance(output_message, dict) else str(output_message)
        
        return await self.record_step(
            job_id=job_id,
            tenant_id=tenant_id,
            actor=actor,
            event_type="llm_response",
            step_type=StepType.THOUGHT,
            thought=thought,
            model_used=model,
            raw_data=raw_data,
            thread_id=thread_id,
            message_id=message_id,
        )

    async def record_tool_call(
        self,
        job_id: str,
        tenant_id: int,
        tool_name: str,
        input_payload: Dict[str, Any],
        output_payload: Optional[Any] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
        thread_id: Optional[str] = None,
        message_id: Optional[str] = None,
        invocation_id: Optional[str] = None,
    ) -> Optional[ExecutionTraceStep]:
        """Record tool execution."""
        event_type = "tool_end" if output_payload or error else "tool_start"
        _log_replay(job_id, f"TOOL_{event_type.upper()}", f"Recording tool {event_type}",
                    tool_name=tool_name, duration_ms=duration_ms, error=error,
                    output_preview=str(output_payload)[:100] if output_payload else None)
        raw_data = {
            "tool": {
                "name": tool_name,
                "input": input_payload,
                "output": output_payload,
                "error": error,
                "duration_ms": duration_ms,
                "invocation_id": invocation_id,
            }
        }
        return await self.record_step(
            job_id=job_id,
            tenant_id=tenant_id,
            actor="tool",
            event_type=event_type,
            step_type=StepType.ACTION,
            action_tool=tool_name,
            action_input=input_payload,
            observation_result=str(output_payload) if output_payload else None,
            raw_data=raw_data,
            thread_id=thread_id,
            message_id=message_id,
        )

    async def record_specialist_call(
        self,
        job_id: str,
        tenant_id: int,
        specialist_id: str,
        specialist_name: str,
        input_payload: Any,
        output_payload: Optional[Any] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
        thread_id: Optional[str] = None,
    ) -> Optional[ExecutionTraceStep]:
        """Record specialist delegation."""
        event_type = "specialist_response" if output_payload or error else "specialist_request"
        _log_replay(job_id, f"SPECIALIST_{event_type.upper()}", f"Recording specialist {event_type}",
                    specialist_id=specialist_id, specialist_name=specialist_name,
                    duration_ms=duration_ms, error=error,
                    output_preview=str(output_payload)[:100] if output_payload else None)
        raw_data = {
            "specialist": {
                "specialist_id": specialist_id,
                "specialist_name": specialist_name,
                "input": input_payload,
                "output": output_payload,
                "error": error,
                "duration_ms": duration_ms,
            }
        }
        return await self.record_step(
            job_id=job_id,
            tenant_id=tenant_id,
            actor="specialist",
            event_type=event_type,
            step_type=StepType.ACTION,
            action_tool=specialist_name,
            raw_data=raw_data,
            thread_id=thread_id,
        )

_replay_service = None

def get_replay_service() -> ReplayService:
    global _replay_service
    if _replay_service is None:
        _replay_service = ReplayService()
    return _replay_service
