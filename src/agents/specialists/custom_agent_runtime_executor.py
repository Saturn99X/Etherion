from typing import Any, Dict, Optional


class CustomAgentRuntimeExecutor:
    def __init__(
        self,
        tenant_id: int = 0,
        job_id: str = "",
        custom_agent_id: str = "default_custom_agent",
    ):
        self.tenant_id = tenant_id
        self.job_id = job_id
        self.custom_agent_id = custom_agent_id

    async def ainvoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        instruction = payload.get("instruction") or payload.get("input") or ""
        return {
            "custom_agent_id": self.custom_agent_id,
            "output": str(instruction),
        }

    def get_schema_hints(self, max_ops: Optional[int] = None) -> Dict[str, Any]:
        return {
            "input_schema": {
                "type": "object",
                "properties": {
                    "instruction": {"type": "string"},
                    "input": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
            },
            "usage": "Provide an instruction to be executed by the selected custom agent runtime.",
        }
