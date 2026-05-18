from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class PermissionMode(str, Enum):
    BYPASS_PERMISSION = "bypass_permission"
    RESTRICTED = "restricted"


class ChecklistItemStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"


class ChecklistItem(BaseModel):
    step_number: int = Field(..., description="1-indexed step number")
    specialist: Optional[str] = Field(None, description="Specialist name or ID to invoke")
    tool: Optional[str] = Field(None, description="Tool name to invoke (alternative to specialist)")
    instruction: str = Field(..., description="What to ask the specialist/tool to do")
    success_criteria: List[str] = Field(
        default_factory=list,
        description="List of criteria that must pass for this step to be accepted",
    )
    depends_on: List[int] = Field(
        default_factory=list,
        description="Step numbers this step depends on (must complete first)",
    )
    status: ChecklistItemStatus = Field(default=ChecklistItemStatus.PENDING)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=2)
    result: Optional[Dict[str, Any]] = Field(None, description="Result after execution")
    validation: Optional["ValidationResult"] = Field(None, description="Validation outcome")
    error: Optional[str] = Field(None, description="Error message if failed")


class ValidationResult(BaseModel):
    passed: bool = False
    confidence: float = 0.0
    checks: List[CriterionCheck] = Field(default_factory=list)
    reasoning: Optional[str] = None


class CriterionCheck(BaseModel):
    criterion: str
    satisfied: bool = False
    confidence: float = 0.0
    reasoning: Optional[str] = None


class ChecklistPlan(BaseModel):
    goal: str = Field(..., description="The original user goal")
    items: List[ChecklistItem] = Field(default_factory=list)
    mode: ExecutionMode = Field(default=ExecutionMode.SEQUENTIAL)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def pending_items(self) -> List[ChecklistItem]:
        return [i for i in self.items if i.status == ChecklistItemStatus.PENDING]

    def ready_items(self) -> List[ChecklistItem]:
        completed_numbers = {
            i.step_number
            for i in self.items
            if i.status in (ChecklistItemStatus.PASSED, ChecklistItemStatus.SKIPPED)
        }
        return [
            i
            for i in self.items
            if i.status == ChecklistItemStatus.PENDING
            and all(d in completed_numbers for d in i.depends_on)
        ]

    def all_passed(self) -> bool:
        return all(
            i.status in (ChecklistItemStatus.PASSED, ChecklistItemStatus.SKIPPED)
            for i in self.items
        )

    def failed_items(self) -> List[ChecklistItem]:
        return [i for i in self.items if i.status == ChecklistItemStatus.FAILED]

    def passed_results(self) -> Dict[int, Dict[str, Any]]:
        return {
            i.step_number: i.result
            for i in self.items
            if i.status == ChecklistItemStatus.PASSED and i.result
        }


class SynthesisResult(BaseModel):
    final_output: str = ""
    sources: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    confidence: float = 0.0


def parse_checklist_plan(text: str, goal: str) -> ChecklistPlan:
    try:
        data = json.loads(text)
    except Exception:
        return ChecklistPlan(goal=goal, items=[])

    if isinstance(data, dict) and "steps" in data:
        steps = data["steps"]
    elif isinstance(data, list):
        steps = data
    else:
        return ChecklistPlan(goal=goal, items=[])

    items = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        items.append(
            ChecklistItem(
                step_number=idx + 1,
                specialist=step.get("specialist"),
                tool=step.get("tool"),
                instruction=step.get("instruction", step.get("description", "")),
                success_criteria=step.get("success_criteria", step.get("criteria", [])),
                depends_on=step.get("depends_on", []),
                max_retries=step.get("max_retries", 2),
            )
        )

    mode_str = data.get("mode", "sequential") if isinstance(data, dict) else "sequential"
    mode = ExecutionMode.PARALLEL if mode_str == "parallel" else ExecutionMode.SEQUENTIAL

    return ChecklistPlan(goal=goal, items=items, mode=mode)


ChecklistItem.model_rebuild()
