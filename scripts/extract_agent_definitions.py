#!/usr/bin/env python3
"""
One-time utility to extract system agent definitions from src/agents/** using AST.
Writes prompts and tool names to scripts/system_agent_definitions.json
"""
import ast
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = PROJECT_ROOT / "src" / "agents"
OUTPUT_JSON = Path(__file__).resolve().parent / "system_agent_definitions.json"


def _stringify_expr(expr: ast.AST) -> str | None:
    """Return a string if expr is (or resolves to) a static string (Constant/Str/BinOp of strings)."""
    if isinstance(expr, (ast.Constant, ast.Str)) and isinstance(getattr(expr, "s", getattr(expr, "value", "")), str):
        return expr.s if hasattr(expr, "s") else expr.value
    if isinstance(expr, ast.JoinedStr):
        # f-strings without dynamic parts could be concatenated; if dynamic, skip
        parts = []
        for v in expr.values:
            if isinstance(v, ast.FormattedValue):
                return None
            if isinstance(v, (ast.Constant, ast.Str)):
                parts.append(v.s if hasattr(v, "s") else v.value)
        return "".join(parts)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        left = _stringify_expr(expr.left)
        right = _stringify_expr(expr.right)
        if left is not None and right is not None:
            return left + right
    return None


def extract_system_prompt(module_ast: ast.AST) -> str | None:
    """Extract a system prompt from module or create_*_agent function bodies."""
    # 1) Module-level *_SYSTEM_PROMPT or SYSTEM_PROMPT
    for node in module_ast.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and (
                    target.id.endswith("SYSTEM_PROMPT") or target.id == "SYSTEM_PROMPT" or target.id.endswith("_PROMPT")
                ):
                    s = _stringify_expr(node.value)
                    if s:
                        return s

    # 2) Inside create_*_agent: system_prompt = "..."
    for node in module_ast.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("create_") and node.name.endswith("_agent"):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assign):
                    for t in inner.targets:
                        if isinstance(t, ast.Name) and t.id == "system_prompt":
                            s = _stringify_expr(inner.value)
                            if s:
                                return s
            # 3) PromptTemplate.from_template("...")
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == "from_template":
                    if inner.args:
                        s = _stringify_expr(inner.args[0])
                        if s:
                            return s
            # 4) ChatPromptTemplate.from_messages([("system", "...") , ...])
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == "from_messages":
                    if inner.args and isinstance(inner.args[0], (ast.List, ast.Tuple)):
                        elts = inner.args[0].elts if isinstance(inner.args[0], ast.List) else inner.args[0].elts
                        for e in elts:
                            if isinstance(e, (ast.Tuple, ast.List)) and len(e.elts) >= 2:
                                role_node, content_node = e.elts[0], e.elts[1]
                                if isinstance(role_node, (ast.Constant, ast.Str)) and (getattr(role_node, "s", getattr(role_node, "value", None)) == "system"):
                                    s = _stringify_expr(content_node)
                                    if s:
                                        return s
    return None


def extract_tools(module_ast: ast.AST) -> list[str]:
    """Find list literal assigned to 'tools' inside create_*_agent function and extract names."""
    tool_names: list[str] = []
    for node in module_ast.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("create_") and node.name.endswith("_agent"):
            for inner in ast.walk(node):
                # Look for assignments to 'tools = [...]'
                if isinstance(inner, ast.Assign):
                    for t in inner.targets:
                        if isinstance(t, ast.Name) and t.id == "tools" and isinstance(inner.value, (ast.List, ast.Tuple)):
                            for elt in inner.value.elts:
                                # Tool instantiation like SomeTool()
                                if isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name):
                                    tool_names.append(elt.func.id)
                                elif isinstance(elt, ast.Call) and isinstance(elt.func, ast.Attribute):
                                    tool_names.append(elt.func.attr)
                                elif isinstance(elt, ast.Name):
                                    tool_names.append(elt.id)
            break
    return tool_names


def is_agent_file(path: Path) -> bool:
    if not path.name.endswith(".py"):
        return False
    if path.name in {"__init__.py", "registry.py"}:
        return False
    parts = path.parts
    # Exclude orchestrator internals and specialists/Utilities
    excluded = {"Orchestrator", "specialists", "Utilities"}
    return not any(p in excluded for p in parts)


def main():
    results: list[dict] = []
    for root, _, files in os.walk(AGENTS_DIR):
        for fname in files:
            fpath = Path(root) / fname
            if not is_agent_file(fpath):
                continue
            try:
                source = fpath.read_text(encoding="utf-8")
                module_ast = ast.parse(source)
                prompt = extract_system_prompt(module_ast)
                tools = extract_tools(module_ast)
                # Name derived from file stem; registry maps stem to user-facing shortname
                results.append({
                    "module": str(fpath.relative_to(PROJECT_ROOT)),
                    "name": fpath.stem,
                    "system_prompt": prompt or "",
                    "tool_names": tools,
                })
            except Exception as e:
                results.append({
                    "module": str(fpath.relative_to(PROJECT_ROOT)),
                    "name": fpath.stem,
                    "error": str(e)
                })

    OUTPUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} agent definitions to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()


