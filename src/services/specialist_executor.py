"""Specialist LLM execution wrapper with retry and trace publishing."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SpecialistResult:
    output: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    retry_count: int = 0
    error: Optional[str] = None


async def execute_specialist(
    agent_def: Dict[str, Any],
    prompt: str,
    tools: Optional[List[Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> SpecialistResult:
    """Run a specialist agent with the given prompt.

    Wraps model loading, retry logic, and execution trace publishing.
    """
    from src.utils.llm_providers.base import get_provider

    t0 = time.monotonic()
    retry_count = 0
    last_error = None
    max_retries = (config or {}).get("max_retries", 2)
    provider_name = agent_def.get("llm_provider", "gemini")
    model = agent_def.get("model", "default")

    for attempt in range(max_retries + 1):
        try:
            llm = get_provider(provider_name).load(model, config)
            if tools:
                llm = llm.bind_tools(tools)

            from langchain_core.messages import HumanMessage
            response = await llm.ainvoke([HumanMessage(content=prompt)])

            output = response.content if hasattr(response, "content") else str(response)
            tool_calls = getattr(response, "tool_calls", []) or []

            result = SpecialistResult(
                output=output,
                tool_calls=tool_calls,
                duration_ms=int((time.monotonic() - t0) * 1000),
                retry_count=retry_count,
            )
            _publish_trace(job_id, tenant_id, agent_def, result)
            return result

        except Exception as e:
            last_error = str(e)
            retry_count += 1
            logger.warning("Specialist attempt %d/%d failed: %s", attempt + 1, max_retries + 1, e)
            if attempt < max_retries:
                try:
                    from src.services.specialist_retry import should_retry
                    if not should_retry(e):
                        break
                except ImportError:
                    pass

    return SpecialistResult(
        output="",
        duration_ms=int((time.monotonic() - t0) * 1000),
        retry_count=retry_count,
        error=last_error,
    )


def _publish_trace(job_id, tenant_id, agent_def, result: SpecialistResult) -> None:
    if not job_id:
        return
    try:
        from src.core.redis import publish_execution_trace
        import asyncio
        asyncio.create_task(publish_execution_trace(job_id, {
            "type": "SPECIALIST_RESPONSE",
            "agent": agent_def.get("name", "unknown"),
            "duration_ms": result.duration_ms,
            "output_preview": result.output[:500],
            "error": result.error,
        }))
    except Exception:
        pass
