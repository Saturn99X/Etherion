import importlib
import json
import os


def test_all_registered_tools_have_dynamic_json_schema():
    from src.services.dynamic_tool_schema import get_dynamic_input_schema
    from src.tools.tool_manager import get_tool_manager

    tm = get_tool_manager()
    registry = (tm.get_tool_registry_info() or {}).get("registry") or {}

    only_raw = (os.getenv("TOOL_SCHEMA_ONLY") or "").strip()
    only_tools = {
        t.strip()
        for t in only_raw.split(",")
        if isinstance(t, str) and t.strip()
    }

    failures = []

    for tool_name, cfg in registry.items():
        if not tool_name or not isinstance(cfg, dict):
            continue

        if only_tools and tool_name not in only_tools:
            continue

        module_name = cfg.get("module")
        attr_name = cfg.get("class")
        ttype = cfg.get("type")

        try:
            mod = importlib.import_module(module_name)
            obj = getattr(mod, attr_name)

            if ttype == "class":
                inst = None
                for ctor in (
                    lambda: obj(),
                    lambda: obj(job_id="job_schema"),
                    lambda: obj(tenant_id=0, job_id="job_schema"),
                ):
                    try:
                        inst = ctor()
                        break
                    except TypeError:
                        inst = None
                if inst is None:
                    raise RuntimeError("could_not_instantiate")
            else:
                inst = obj

            schema = get_dynamic_input_schema(tool_name, inst)
            json.dumps(schema)
        except Exception as e:
            failures.append({"tool": tool_name, "error": str(e)})

    if failures:
        print(json.dumps(failures, indent=2, sort_keys=True))
    assert failures == [], f"Dynamic schema failures: {failures}"
