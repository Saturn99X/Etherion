"""
Autonomous specialist executor with native LangChain tool calling.

A specialist is an autonomous agent that:
- Has its own checklist of sub-tasks
- Calls tools via LangChain's native bind_tools() — no text parsing
- Runs until checklist is complete or max iterations hit
- Tool calls are structured JSON from the model, not regex from free text
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.services.orchestration.checklist import (
    ChecklistItem,
    ChecklistItemStatus,
    ChecklistPlan,
)
from src.utils.llm_loader import get_gemini_llm

logger = logging.getLogger(__name__)


@dataclass
class ToolRequest:
    tool_name: str
    arguments: Dict[str, Any]
    justification: str
    step: int


@dataclass
class ToolApproval:
    approved: bool
    feedback: str = ""


@dataclass
class SpecialistRunResult:
    specialist_id: str
    specialist_name: str
    output: str
    checklist: Dict[str, Any]
    tools_used: List[str] = field(default_factory=list)
    iterations: int = 0
    duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None


class SpecialistExecutor:
    """
    Autonomous specialist with native LangChain tool calling.

    Uses bind_tools() so the model returns structured tool_calls
    instead of free-text tool descriptions — eliminates hallucinations.
    """

    def __init__(
        self,
        specialist_id: str,
        specialist_name: str,
        system_prompt: str,
        tool_names: List[str],
        model_name: str = "gemini-2.5-flash",
        temperature: float = 0.1,
        max_iterations: int = 10,
        auto_approved_tools: Optional[set] = None,
        tool_instances: Optional[Dict[str, Any]] = None,
        tool_approval_callback: Optional[Callable[[ToolRequest], ToolApproval]] = None,
        trace_callback: Optional[Callable] = None,
        tenant_id: int = 0,
        job_id: str = "",
    ):
        self.specialist_id = specialist_id
        self.specialist_name = specialist_name
        self.system_prompt = system_prompt
        self.tool_names = set(tool_names)
        self.model_name = model_name
        self.temperature = temperature
        self.max_iterations = max_iterations
        self.auto_approved_tools = auto_approved_tools or set()
        self.tool_instances = tool_instances or {}
        self.tool_approval_callback = tool_approval_callback
        self.trace_callback = trace_callback
        self.tenant_id = tenant_id
        self.job_id = job_id

    async def run(
        self,
        instruction: str,
        checklist: Optional[ChecklistPlan] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> SpecialistRunResult:
        t_start = time.monotonic()

        try:
            from src.utils.llm_registry import load_llm
            llm = load_llm(provider="bedrock", tier_or_alias="fast", config={})
        except Exception:
            try:
                from src.utils.llm_loader import get_llm
                llm = get_llm(provider="bedrock", tier="fast")
            except Exception:
                llm = get_gemini_llm(model_tier="flash")

        available_instances = [v for k, v in self.tool_instances.items() if k in self.tool_names]
        if available_instances:
            llm = llm.bind_tools(available_instances, tool_choice="any")

        tools_desc = "\n".join(
            f"- {n}" for n in sorted(self.tool_names)
        ) if self.tool_names else "(none)"
        checklist_text = self._format_checklist(checklist) if checklist else "(no specific checklist — complete the instruction)"
        context_text = ""
        if context:
            prev = context.get("previous_results", {})
            if prev:
                context_text = f"\n\nPREVIOUS SPECIALIST RESULTS:\n{json.dumps(prev, default=str, indent=2)[:3000]}"

        system_msg = f"""{self.system_prompt}

RUNTIME CONTEXT:
- tenant_id: {self.tenant_id}
- job_id: {self.job_id}
- goal: {instruction[:200]}

AVAILABLE TOOLS:
{tools_desc}

RULES:
- You are an autonomous specialist. Think step-by-step and use tools to accomplish your task.
- Use the tools provided to you when you need them.
- After receiving tool results, analyze them and decide next steps.
- When your task is complete, write your final result.
- Be thorough but efficient. Don't repeat tool calls unnecessarily."""

        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=f"""TASK: {instruction}

YOUR CHECKLIST:
{checklist_text}
{context_text}

Begin working on this task now. Use tools as needed."""),
        ]

        tools_used = []
        iteration = 0
        final_output = ""

        while iteration < self.max_iterations:
            iteration += 1

            await self._trace("SPECIALIST_ITERATION", f"Specialist {self.specialist_name} iteration {iteration}",
                              specialist=self.specialist_name, iteration=iteration)

            try:
                response = await llm.ainvoke(messages)
            except Exception as e:
                final_output = f"LLM error: {e}"
                break

            if hasattr(response, 'tool_calls') and response.tool_calls:
                for tc in response.tool_calls:
                    tool_name = tc.get("name", "")
                    tool_args = tc.get("args", {})

                    if tool_name not in self.tool_names:
                        messages.append(AIMessage(content=str(response.content)))
                        messages.append(HumanMessage(content=f"[ERROR] Tool '{tool_name}' is not available. Available: {', '.join(sorted(self.tool_names))}"))
                        continue

                    await self._trace("SPECIALIST_TOOL_CALL", f"Specialist {self.specialist_name} calling {tool_name}",
                                      specialist=self.specialist_name, tool=tool_name)

                    tool_result = await self._execute_tool(tool_name, tool_args)
                    tools_used.append(tool_name)

                    messages.append(AIMessage(content=str(response.content)))
                    messages.append(ToolMessage(
                        content=json.dumps(tool_result, default=str)[:4000] if isinstance(tool_result, (dict, list)) else str(tool_result)[:4000],
                        tool_call_id=tc.get("id", ""),
                    ))
                continue

            response_text = ""
            if isinstance(response.content, list):
                for part in response.content:
                    if isinstance(part, dict):
                        response_text += part.get("text", str(part))
                    else:
                        response_text += str(part)
            else:
                response_text = str(response.content)

            if not response_text.strip():
                continue

            if iteration >= 2 and len(response_text.strip()) > 100:
                final_output = response_text.strip()
                break

            if iteration == 1 and len(response_text.strip()) > 50 and "?" not in response_text[:30]:
                final_output = response_text.strip()
                break

            messages.append(AIMessage(content=response_text))
            messages.append(HumanMessage(content="Continue working. If you need a tool, use one. When done, provide your answer."))

        if not final_output:
            final_output = response_text if 'response_text' in dir() else "No output produced"

        duration_ms = int((time.monotonic() - t_start) * 1000)
        checklist_dict = checklist.model_dump() if checklist else {}

        await self._trace("SPECIALIST_DONE", f"Specialist {self.specialist_name} finished",
                          specialist=self.specialist_name, iterations=iteration,
                          tools_used=len(set(tools_used)), duration_ms=duration_ms)

        return SpecialistRunResult(
            specialist_id=self.specialist_id,
            specialist_name=self.specialist_name,
            output=final_output,
            checklist=checklist_dict,
            tools_used=list(set(tools_used)),
            iterations=iteration,
            duration_ms=duration_ms,
            success=True,
        )

    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        try:
            import src.tools.unified_research_tool as urt_mod
            if tool_name == "unified_research_tool":
                query = args.get("query", args.get("input", ""))
                enable_web = args.get("enable_web", True)
                return await asyncio.to_thread(
                    urt_mod.unified_research_tool,
                    query=query,
                    tenant_id=str(self.tenant_id),
                    job_id=self.job_id,
                    enable_web=enable_web,
                )
        except Exception:
            pass

        inst = self.tool_instances.get(tool_name)
        if inst is None:
            return {"error": f"Tool '{tool_name}' not available"}

        try:
            if hasattr(inst, 'ainvoke') and callable(inst.ainvoke):
                return await inst.ainvoke(args)
            elif hasattr(inst, 'invoke') and callable(inst.invoke):
                return inst.invoke(args)
            elif callable(inst):
                if asyncio.iscoroutinefunction(inst):
                    return await inst(**args)
                return inst(**args)
            return {"error": f"Tool '{tool_name}' is not executable"}
        except Exception as e:
            return {"error": f"Tool '{tool_name}' failed: {e}"}

    def _format_checklist(self, plan: Optional[ChecklistPlan]) -> str:
        if not plan or not plan.items:
            return "(none)"
        lines = []
        for item in plan.items:
            status = item.status.value
            lines.append(f"  {item.step_number}. [{status}] {item.instruction}")
            if item.success_criteria:
                for c in item.success_criteria:
                    lines.append(f"     - criterion: {c}")
        return "\n".join(lines)

    async def _trace(self, event_type: str, message: str, **kwargs):
        ts = datetime.utcnow().isoformat()
        extra = " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None) if kwargs else ""
        log_line = f"[TRACE] ts={ts} job_id={self.job_id} type={event_type} | {message}"
        if extra:
            log_line += f" | {extra}"
        print(log_line, flush=True)

        if self.trace_callback:
            try:
                await self.trace_callback(self.job_id, {"type": event_type, "step_description": message, **kwargs})
            except Exception:
                pass