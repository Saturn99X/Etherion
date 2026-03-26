import functools
from typing import Callable, Any
from langchain_core.tools import BaseTool

from src.services.pricing.cost_tracker import CostTracker


def instrument_tool_call(provider_name: str) -> Callable:
    """
    Decorator to instrument a tool function/method to record API call and data-in.
    Assumes decorated function receives kwargs containing 'job_id' and possibly
    'request_bytes' for inbound transfer accounting.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            job_id = kwargs.get("job_id") or "job_unknown"
            tenant_id = kwargs.get("tenant_id")
            request_bytes = int(kwargs.get("request_bytes") or 0)
            tracker = CostTracker()
            await tracker.record_api_call(job_id, provider_name, tenant_id=tenant_id)
            if request_bytes > 0:
                await tracker.record_data_transfer(job_id, mb_in=request_bytes / (1024 * 1024), tenant_id=tenant_id)
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def instrument_base_tool(tool: BaseTool, provider_name: str, job_id: str) -> BaseTool:
    """
    Wrap a LangChain BaseTool to record API calls and inbound bytes for each async invocation.
    """
    tracker = CostTracker()

    if hasattr(tool, "ainvoke") and callable(getattr(tool, "ainvoke")):
        original_ainvoke = tool.ainvoke

        async def ainvoke_wrapper(input: Any, *args, **kwargs):
            try:
                request_bytes = int(kwargs.get("request_bytes") or 0)
                tenant_id = kwargs.get("tenant_id")
                if request_bytes <= 0:
                    try:
                        request_bytes = len(str(input).encode("utf-8"))
                    except Exception:
                        request_bytes = 0
                await tracker.record_api_call(job_id, provider_name, tenant_id=tenant_id)
                if request_bytes > 0:
                    await tracker.record_data_transfer(job_id, mb_in=request_bytes / (1024 * 1024), tenant_id=tenant_id)
            except Exception:
                pass
            return await original_ainvoke(input, *args, **kwargs)

        tool.ainvoke = ainvoke_wrapper  # type: ignore

    return tool

