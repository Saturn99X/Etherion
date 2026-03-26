import json


def test_all_tools_schema_hints_are_json_serializable():
    """Regression test: tool schema exposure must be JSON-serializable.

    The orchestrator tooling block relies on per-tool schema hints being safely JSON
    serializable (no Python types, callables, objects, etc.).
    """

    from src.services.tool_schema_registry import get_tool_schema_hints, merge_runtime_hints
    from src.tools.tool_manager import get_tool_manager

    tm = get_tool_manager()
    registry_info = tm.get_tool_registry_info()
    registry = registry_info.get("registry") or {}

    failures = []

    for tool_name, cfg in registry.items():
        if not tool_name or not isinstance(cfg, dict):
            continue

        try:
            fallback_hints = get_tool_schema_hints(tool_name)
            hints = merge_runtime_hints(None, fallback_hints)

            # In production, runtime hints are only included if an instance is already attached
            # to the approved_tools entry. The safe baseline is the static registry fallback.
            json.dumps(hints)

            # Validate the schema entry shape used by OrchestratorRuntime
            schema_entry = {"name": tool_name, "type": cfg.get("type")}
            if "input_schema" in hints:
                schema_entry["input_schema"] = hints["input_schema"]
            if "usage" in hints:
                schema_entry["usage"] = hints["usage"]
            if "examples" in hints:
                schema_entry["examples"] = hints["examples"]
            json.dumps(schema_entry)
        except Exception as e:
            failures.append({"tool": tool_name, "phase": "schema_hints_json_serialize", "error": str(e)})

    assert failures == [], f"Tool schema exposure failures: {failures}"
