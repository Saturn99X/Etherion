# src/tools/natural_language_tool_router.py
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, Optional, Tuple, Callable

from src.tools.tool_manager import ToolManager


class NaturalLanguageToolRouter:
    """
    Minimal router that maps pure natural language to a concrete tool call.

    Strategy:
    - Keyword-based intent classification for file generation tools.
    - Runtime supplies tenant_id/job_id (and optionally agent_id).
    - Returns the tool result; can run in dry-run to only return mapping.

    This is intentionally simple and deterministic so it can be driven by any LLM
    that only produces free text instructions.
    """

    def __init__(self, tool_manager: Optional[ToolManager] = None):
        self.tool_manager = tool_manager or ToolManager()
        # Simple keyword -> tool mapping; can be extended or replaced with a model later
        self._patterns: Tuple[Tuple[re.Pattern[str], str], ...] = (
            (re.compile(r"\b(image|picture|render|png|jpg|jpeg|generate an image)\b", re.I), "generate_image_file"),
            (re.compile(r"\b(pdf|resume|one[- ]page|report)\b", re.I), "generate_pdf_file"),
            (re.compile(r"\b(excel|spreadsheet|xlsx|table)\b", re.I), "generate_excel_file"),
            (re.compile(r"\b(presentation|slide|slides|ppt|powerpoint)\b", re.I), "generate_presentation_file"),
        )

    def classify(self, text: str) -> Optional[str]:
        for pat, tool in self._patterns:
            if pat.search(text or ""):
                return tool
        return None

    def build_input(self, tool_name: str, text: str, *, tenant_id: str, job_id: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        agent = agent_id or "platform_orchestrator"
        # Basic payload extraction per tool
        if tool_name == "generate_image_file":
            data = {"prompt": text.strip()}
            return {"tenant_id": tenant_id, "job_id": job_id, "agent_id": agent, "data": data}
        if tool_name in ("generate_pdf_file", "generate_excel_file", "generate_presentation_file"):
            # Heuristic for template selection; can be overridden by orchestrator prompts
            template = None
            if tool_name == "generate_pdf_file":
                template = "generic_one_pager"
                if re.search(r"\bresume\b", text, re.I):
                    template = "resume_one_page"
            if tool_name == "generate_presentation_file":
                template = "pitch_deck_minimal"
            # Naive extraction of key-value lines into data map
            data: Dict[str, Any] = {"instructions": text.strip()}
            return {"tenant_id": tenant_id, "job_id": job_id, "agent_id": agent, "template": template, "data": data}
        # Default passthrough for unknowns
        return {"tenant_id": tenant_id, "job_id": job_id, "agent_id": agent, "data": {"instructions": text.strip()}}

    async def execute(self, text: str, *, tenant_id: str, job_id: str, agent_id: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        tool_name = self.classify(text)
        if not tool_name:
            return {"success": False, "error": "UNMAPPED_INTENT", "message": "No tool mapped from text."}

        input_data = self.build_input(tool_name, text, tenant_id=tenant_id, job_id=job_id, agent_id=agent_id)
        if dry_run:
            return {"success": True, "tool": tool_name, "input_data": input_data}

        tool_fn = self.tool_manager.get_tool_instance(
            tool_name=tool_name,
            tenant_id=int(tenant_id) if isinstance(tenant_id, str) and tenant_id.isdigit() else tenant_id,  # type: ignore
            job_id=job_id,
        )

        # tool_fn may be async; call accordingly
        if asyncio.iscoroutinefunction(tool_fn):
            return await tool_fn(input_data)
        # If it's a BaseTool or sync callable, just call (LangChain tools are often callable)
        res = tool_fn(input_data)
        if asyncio.iscoroutine(res):
            return await res
        return res
