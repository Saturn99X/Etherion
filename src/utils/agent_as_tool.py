from __future__ import annotations

from typing import Any, Dict, Optional
import asyncio
import inspect


class AgentTool:
    """Lightweight wrapper to expose an agent/executor as a tool instance.

    This is intentionally minimal and **does not** depend on LangChain tool types.
    TeamOrchestrator and the orchestrator runtime only require that the instance
    provides an async `ainvoke` method (and optionally a sync `invoke`).
    """

    def __init__(self, agent: Any, name: str, description: str = "") -> None:
        self._agent = agent
        self.name = name
        self.description = description or ""

    async def ainvoke(self, payload: Dict[str, Any]) -> Any:
        """Async entrypoint used by TeamOrchestrator.

        The payload is forwarded as-is to the underlying agent. If the
        underlying agent does not implement `ainvoke`, but is callable, we
        invoke it and await the result when needed.
        """
        # Preferred path: delegate to underlying async interface
        if hasattr(self._agent, "ainvoke") and callable(getattr(self._agent, "ainvoke")):
            return await self._agent.ainvoke(payload)

        # Fallback: call the underlying object directly
        if callable(self._agent):
            result = self._agent(payload)
            if inspect.isawaitable(result):
                return await result
            return result

        raise TypeError("Underlying agent is not callable or async-invokable")

    def invoke(self, payload: Dict[str, Any]) -> Any:
        """Best-effort sync wrapper for environments that call `invoke`.

        If only `ainvoke` is available, run it in the current or a temporary
        event loop.
        """
        if hasattr(self._agent, "invoke") and callable(getattr(self._agent, "invoke")):
            return self._agent.invoke(payload)

        if hasattr(self._agent, "ainvoke") and callable(getattr(self._agent, "ainvoke")):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_running():
                # In a running loop, caller should prefer `ainvoke`; fall back to direct call
                coro = self._agent.ainvoke(payload)
                if inspect.isawaitable(coro):
                    # This will not actually wait in a running loop, but keeps type expectations
                    return coro
                return coro
            return loop.run_until_complete(self._agent.ainvoke(payload))

        # Last resort: direct call
        if callable(self._agent):
            return self._agent(payload)

        raise TypeError("Underlying agent is not callable or invokable")


def agent_to_tool(agent: Any, name: str, description: str = "") -> AgentTool:
    """Create an AgentTool wrapper for use in TeamOrchestrator.

    TeamOrchestrator expects the returned object to expose `ainvoke` (and
    optionally `invoke`). It does **not** rely on LangChain-specific base
    classes here, so this wrapper stays small and dependency-free.
    """
    return AgentTool(agent=agent, name=name, description=description)
