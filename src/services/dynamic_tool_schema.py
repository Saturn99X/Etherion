import inspect
import json
from typing import Any, Dict, Optional, Tuple, Type

from pydantic import BaseModel, Field, create_model


def _py_type_to_json_schema(t: Any) -> Dict[str, Any]:
    if t in (str,):
        return {"type": "string"}
    if t in (int,):
        return {"type": "integer"}
    if t in (float,):
        return {"type": "number"}
    if t in (bool,):
        return {"type": "boolean"}
    if t in (dict,):
        return {"type": "object"}
    if t in (list, tuple):
        return {"type": "array"}
    if t in (bytes, bytearray):
        return {"type": "string", "contentEncoding": "base64"}
    return {}


def _callable_to_schema(func: Any, *, name: str) -> Dict[str, Any]:
    sig = inspect.signature(func)
    fields: Dict[str, Tuple[Any, Any]] = {}
    for p_name, p in sig.parameters.items():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if p_name in ("self", "cls"):
            continue
        ann = p.annotation if p.annotation is not inspect._empty else Any
        default = p.default if p.default is not inspect._empty else ...
        fields[p_name] = (ann, default)

    mdl: Type[BaseModel] = create_model(f"{name}Input", **fields)  # type: ignore
    try:
        return mdl.model_json_schema()
    except Exception:
        return mdl.schema()  # type: ignore


def _mcp_tool_to_schema(inst: Any, *, name: str) -> Dict[str, Any]:
    ops = []
    if hasattr(inst, "list_operations") and callable(getattr(inst, "list_operations")):
        ops = inst.list_operations(max_ops=200) or []

    if not ops:
        raise RuntimeError(f"Tool {name} exposes no operations")

    variants = []
    for op in ops:
        props: Dict[str, Any] = {"operation": {"const": op}}
        req = ["operation"]
        schema_map = None
        try:
            if hasattr(inst, "_get_operation_schema") and callable(getattr(inst, "_get_operation_schema")):
                schema_map = inst._get_operation_schema(op)
            elif hasattr(inst, "get_operation_schema") and callable(getattr(inst, "get_operation_schema")):
                schema_map = inst.get_operation_schema(op)
        except Exception:
            schema_map = None

        if isinstance(schema_map, dict):
            for k, cfg in schema_map.items():
                if not isinstance(cfg, dict):
                    continue
                t = cfg.get("type")
                if isinstance(t, tuple) and t:
                    t = t[0]
                js = _py_type_to_json_schema(t)
                if not js:
                    js = {}
                if "description" in cfg and isinstance(cfg.get("description"), str):
                    js["description"] = cfg.get("description")
                if "max_length" in cfg:
                    try:
                        js["maxLength"] = int(cfg.get("max_length"))
                    except Exception:
                        pass
                props[k] = js
                if bool(cfg.get("required")):
                    req.append(k)

        variants.append(
            {
                "type": "object",
                "properties": props,
                "required": req,
                "additionalProperties": True,
            }
        )

    return {"oneOf": variants}


def get_dynamic_input_schema(tool_name: str, inst: Any) -> Dict[str, Any]:
    if inst is None:
        raise RuntimeError(f"Tool {tool_name} instance is None")

    if hasattr(inst, "get_schema_hints") and callable(getattr(inst, "get_schema_hints")):
        hints = inst.get_schema_hints(max_ops=200)
        if isinstance(hints, dict) and isinstance(hints.get("input_schema"), dict):
            return hints["input_schema"]

    if hasattr(inst, "args_schema") and getattr(inst, "args_schema") is not None:
        schema_model = getattr(inst, "args_schema")
        try:
            return schema_model.model_json_schema()
        except Exception:
            return schema_model.schema()  # type: ignore

    if hasattr(inst, "list_operations") and callable(getattr(inst, "list_operations")):
        return _mcp_tool_to_schema(inst, name=tool_name)

    if callable(inst):
        return _callable_to_schema(inst, name=tool_name)

    raise RuntimeError(f"Unsupported tool instance type for schema: {tool_name}")


def get_dynamic_schema_hints(tool_name: str, inst: Any) -> Dict[str, Any]:
    schema = get_dynamic_input_schema(tool_name, inst)
    json.dumps(schema)
    return {"input_schema": schema}
