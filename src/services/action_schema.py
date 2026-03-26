from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

# Pydantic v2-compatible validator import with v1 fallback
try:  # Prefer Pydantic v2
    from pydantic import field_validator as _field_validator  # type: ignore
    _HAS_PYDANTIC_V2 = True
except Exception:  # Pydantic v1 fallback
    _field_validator = None
    _HAS_PYDANTIC_V2 = False
    from pydantic import validator as _validator  # type: ignore


ActionType = Literal["tool", "specialist", "finish", "request_stop"]


class Action(BaseModel):
    type: ActionType = Field(..., description="Action type: tool, specialist, or finish")
    name: Optional[str] = Field(None, description="Tool or logical action name. Optional for finish.")
    input: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured input for the action")
    target_specialist_id: Optional[str] = Field(None, description="Target custom_agent_id when type is specialist")
    idempotency_key: Optional[str] = Field(None, description="Optional key to deduplicate actions")
    timeout_seconds: Optional[int] = Field(120, ge=1, description="Optional action timeout")

    # Pydantic v2 validator with v1 fallback
    if _HAS_PYDANTIC_V2:
        @_field_validator("name", mode="after")  # type: ignore[misc]
        @classmethod
        def _name_required_when_not_finish_v2(cls, v, info):  # type: ignore[no-untyped-def]
            t = None
            try:
                t = (getattr(info, "data", None) or {}).get("type")
            except Exception:
                t = None
            # Allow specialist actions to omit name (they use target_specialist_id)
            if t not in ("finish", "specialist") and not v:
                raise ValueError("name is required for tool actions")
            return v
    else:
        @_validator("name", always=True)  # type: ignore[misc]
        def _name_required_when_not_finish_v1(cls, v, values):  # type: ignore[no-untyped-def]
            t = values.get("type")
            # Allow specialist actions to omit name (they use target_specialist_id)
            if t not in ("finish", "specialist") and not v:
                raise ValueError("name is required for tool actions")
            return v


class Plan(BaseModel):
    actions: List[Action] = Field(default_factory=list)

    def is_finish(self) -> bool:
        return any(a.type == "finish" for a in self.actions)


def parse_plan_dict(data: Dict[str, Any]) -> Plan:
    """Parse a dict into a Plan, compatible with Pydantic v1 and v2.

    Tries v2 `model_validate` first, then falls back to v1 `parse_obj`.
    """
    try:
        # Pydantic v2
        return Plan.model_validate(data)  # type: ignore[attr-defined]
    except Exception:
        # Pydantic v1
        return Plan.parse_obj(data)
