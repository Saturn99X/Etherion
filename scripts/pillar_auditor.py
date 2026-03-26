#!/usr/bin/env python3
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Iterable

ROOT = Path(__file__).resolve().parents[1]
PILLARS_DIR = ROOT / "Z" / "Pillars"
SRC_DIR = ROOT / "src"
FRONTEND_DIR = ROOT / "frontend"
TERRAFORM_MODULES_DIR = ROOT / "terraform" / "modules"
INFRA_DIR = ROOT / "infrastructure"

# Mapping of pillar file name suffix -> search patterns (glob-style or keyword tags)
PILLAR_PATTERNS: Dict[str, Dict[str, List[str]]] = {
    "pillar-00-cross-cutting.md": {
        "paths": [
            "src/core/**",
            "src/middleware/**",
            "src/etherion_ai/app.py",
            "src/etherion_ai/graphql_schema/**",
            "src/tools/**",
            "src/utils/**",
            "src/config/**",
            "src/database/models/**",
        ]
    },
    "pillar-01-vision.md": {
        "paths": [
            "src/etherion_ai/app.py",
            "src/etherion_ai/graphql_schema/**",
            "src/services/platform_orchestrator.py",
            "src/services/goal_orchestrator.py",
            "src/services/team_orchestrator.py",
            "src/services/orchestrator_runtime.py",
            "src/services/orchestrator_error_handler.py",
            "src/services/orchestrator_security.py",
            "src/config/orchestrator_runtime.py",
            "frontend/components/vibe-code-studio.tsx",
            "frontend/components/agent-registry.tsx",
            "frontend/components/agent-blueprint-preview.tsx",
            "frontend/components/execution-trace-panel.tsx",
            "frontend/components/job-status-tracker.tsx",
        ]
    },
    "pillar-02-multi-tenancy.md": {
        "paths": [
            "src/etherion_ai/middleware/tenant_middleware.py",
            "src/security/tenant_isolation.py",
            "src/etherion_ai/middleware/auth_context.py",
            "src/auth/middleware.py",
            "src/auth/**",
            "src/utils/secrets_manager.py",
            "src/services/secure_credential_service.py",
            "src/database/models/**",
        ]
    },
    "pillar-03-orchestrator.md": {
        "paths": [
            "src/services/goal_orchestrator.py",
            "src/services/team_orchestrator.py",
            "src/services/platform_orchestrator.py",
            "src/services/orchestrator_runtime.py",
            "src/services/orchestrator_error_handler.py",
            "src/services/orchestrator_security.py",
            "src/tools/orchestrator_research.py",
            "src/tools/unified_research_tool.py",
            "src/tools/exa_search.py",
            "src/etherion_ai/graphql_schema/mutations.py",
        ]
    },
    "pillar-04-memory.md": {
        "paths": [
            "src/services/bigquery_service.py",
            "src/database/bigquery_schema.py",
            "src/services/bq_schema_manager.py",
            "src/services/kb_query_service.py",
            "src/services/vertex_cache_cdc.py",
            "src/tools/vertex_ai_search.py",
            "src/services/web_search_service.py",
            "src/core/gcs_client.py",
            "src/services/ingestion_service.py",
        ]
    },
    "pillar-05-mcp.md": {
        "paths": [
            "src/tools/mcp/**",
            "src/services/mcp_tool_manager.py",
            "src/tools/tool_manager.py",
            "src/utils/secrets_manager.py",
            "src/services/secure_credential_service.py",
            "src/tools/confirm_action_tool.py",
            "src/tools/ui_action_tool.py",
            "src/etherion_ai/app.py",  # webhook routes
        ]
    },
    "pillar-06-vibe-code.md": {
        "paths": [
            "src/database/models/custom_agent.py",
            "src/database/models/agent_team.py",
            "src/services/agent_loader.py",
            "src/services/platform_orchestrator.py",
            "src/etherion_ai/graphql_schema/**",
            "frontend/components/vibe-code-studio.tsx",
            "frontend/components/agent-registry.tsx",
            "frontend/components/agent-blueprint-preview.tsx",
        ]
    },
    "pillar-07-async-engine.md": {
        "paths": [
            "src/core/celery.py",
            "src/celery_worker.py",
            "src/core/redis.py",
            "src/scheduler/**",
            "src/core/tasks.py",
            "src/core/tenant_tasks.py",
            "src/database/models/job.py",
            "src/database/models/execution_trace.py",
            "src/etherion_ai/graphql_schema/subscriptions.py",
        ]
    },
    "pillar-08-economics.md": {
        "paths": [
            "src/services/pricing/**",
            "src/utils/token_counter.py",
            "src/services/tool_instrumentation.py",
            "src/utils/llm_wrapper.py",
            "src/utils/llm_loader.py",
            "src/services/goal_orchestrator.py",
        ]
    },
    "pillar-09-repository.md": {
        "paths": [
            "src/services/repository_service.py",
            "src/services/content_repository_service.py",
            "src/core/gcs_client.py",
            "src/tools/file_generation/**",
            "src/tools/save_to_gcs_tool.py",
            "frontend/components/repository-browser.tsx",
        ]
    },
    "pillar-10-feedback.md": {
        "paths": [
            "src/database/models/feedback.py",
            "src/services/feedback_service.py",
            "src/services/behavior_monitor.py",
            "src/services/observation_performance_monitor.py",
            "src/etherion_ai/graphql_schema/**",
            "frontend/components/feedback-form.tsx",
        ]
    },
    "pillar-11-security.md": {
        "paths": [
            "src/auth/**",
            "src/middleware/security_integration.py",
            "src/middleware/authorization.py",
            "src/middleware/csrf_protection.py",
            "src/middleware/security_headers.py",
            "src/middleware/rate_limiter.py",
            "src/etherion_ai/middleware/**",
            "src/security/tenant_isolation.py",
            "src/core/security/audit_logger.py",
            "src/services/prompt_security.py",
            "src/utils/input_sanitization.py",
            "src/utils/network_security.py",
        ]
    },
    "pillar-12-intelligence.md": {
        "paths": [
            "src/services/context_window_manager.py",
            "src/services/user_observation_service.py",
            "src/services/kb_query_service.py",
            "src/services/web_search_service.py",
            "src/tools/unified_research_tool.py",
            "src/tools/exa_search.py",
            "src/utils/llm_loader.py",
            "src/utils/llm_wrapper.py",
            "src/config/orchestrator_runtime.py",
        ]
    },
    "pillar-13-architecture.md": {
        "paths": [
            "src/database/bigquery_schema.py",
            "src/services/bq_schema_manager.py",
            "src/services/vertex_cache_cdc.py",
            "src/services/ingestion_service.py",
            "src/core/gcs_client.py",
            "src/services/repository_service.py",
            "src/services/content_repository_service.py",
        ]
    },
}


def _glob_many(patterns: Iterable[str]) -> List[Path]:
    out: List[Path] = []
    for pat in patterns:
        base = ROOT / pat
        if "**" in pat or base.name in ("*", "**"):
            out.extend(Path(ROOT).glob(pat))
        else:
            out.extend(Path(ROOT).glob(pat))
    # Normalize and filter to files that exist
    files = []
    for p in out:
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend([f for f in p.rglob("*") if f.is_file()])
    # Deduplicate and sort
    uniq = sorted({str(p.relative_to(ROOT)) for p in files})
    return [ROOT / u for u in uniq]


def _extract_modules_from_doc(doc_text: str) -> List[Path]:
    modules: List[Path] = []
    for line in doc_text.splitlines():
        line = line.strip()
        if line.startswith("-") or line.startswith("*"):
            if "terraform/modules/" in line:
                start = line.find("terraform/modules/")
                # capture token until space, backtick, or '('
                raw = line[start:]
                raw = raw.split("`")[0]
                raw = raw.split("(")[0]
                path = raw.strip().split()[0]
                mod_dir = ROOT / path
                if mod_dir.exists():
                    modules.append(mod_dir)
            if "infrastructure/" in line:
                start = line.find("infrastructure/")
                raw = line[start:]
                raw = raw.split("`")[0]
                raw = raw.split("(")[0]
                path = raw.strip().split()[0]
                mod_dir = ROOT / path
                if mod_dir.exists():
                    modules.append(mod_dir)
    return modules


_VAR_RE = re.compile(r"\bvariable\s+\"([^\"]+)\"")
_OUT_RE = re.compile(r"\boutput\s+\"([^\"]+)\"")


def _tf_vars_outputs(mod_dir: Path) -> Tuple[List[str], List[str]]:
    vars_found: List[str] = []
    outs_found: List[str] = []
    for fname in ("variables.tf", "outputs.tf", "main.tf"):
        fpath = mod_dir / fname
        if not fpath.exists():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        vars_found.extend(_VAR_RE.findall(text))
        outs_found.extend(_OUT_RE.findall(text))
    # Dedup/sort
    return sorted(set(vars_found)), sorted(set(outs_found))


def _upsert_section(md_text: str, header: str, body: str) -> str:
    lines = md_text.splitlines()
    start_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == header.strip().lower():
            start_idx = i
            break
    if start_idx is None:
        # append with two newlines
        if not md_text.endswith("\n"):
            md_text += "\n"
        md_text += f"\n{header}\n{body}\n"
        return md_text
    # find next header of same or higher level (starts with ##)
    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        if lines[j].startswith("## ") or lines[j].startswith("# "):
            end_idx = j
            break
    new = lines[:start_idx]
    new.append(header)
    new.extend(body.splitlines())
    new.extend(lines[end_idx:])
    return "\n".join(new) + ("\n" if not "\n".endswith("\n") else "")


def generate_inventory() -> int:
    pillar_files = list(PILLARS_DIR.glob("pillar-*.md"))
    status = 0
    for pf in pillar_files:
        pats = PILLAR_PATTERNS.get(pf.name, {}).get("paths", [])
        files = _glob_many(pats)
        rels = [str(f.relative_to(ROOT)) for f in files]
        inv_body = ["", "- **Full Inventory (auto-generated)**"]
        if not rels:
            inv_body.append("  - (none matched)")
        else:
            for r in rels:
                inv_body.append(f"  - `{r}`")
        md = pf.read_text(encoding="utf-8")
        md2 = _upsert_section(md, "## Full Inventory", "\n".join(inv_body))
        if md2 != md:
            pf.write_text(md2, encoding="utf-8")
    return status


def crosslink_terraform() -> int:
    pillar_files = [p for p in PILLARS_DIR.glob("pillar-*.md")]
    for pf in pillar_files:
        md = pf.read_text(encoding="utf-8")
        mods = _extract_modules_from_doc(md)
        if not mods:
            # no terraform modules referenced in doc
            continue
        body_lines = ["", "- **Terraform Modules (variables/outputs)**"]
        for m in mods:
            vars_, outs_ = _tf_vars_outputs(m)
            rel = str(m.relative_to(ROOT))
            body_lines.append(f"  - `{rel}`")
            if vars_:
                body_lines.append("    - variables:")
                for v in vars_:
                    body_lines.append(f"      - `{v}`")
            if outs_:
                body_lines.append("    - outputs:")
                for o in outs_:
                    body_lines.append(f"      - `{o}`")
        md2 = _upsert_section(md, "### Terraform Module Variables/Outputs", "\n".join(body_lines))
        if md2 != md:
            pf.write_text(md2, encoding="utf-8")
    return 0


def validate_ci() -> int:
    # CI gate: ensure each pillar doc has Production Hardening and Full Inventory.
    # If terraform/infrastructure is referenced, ensure Terraform cross-links section exists.
    rc = 0
    failures: List[str] = []
    for pf in PILLARS_DIR.glob("pillar-*.md"):
        text = pf.read_text(encoding="utf-8")
        if "## Production Hardening" not in text:
            failures.append(f"{pf.name}: missing '## Production Hardening' section")
        if "## Full Inventory" not in text:
            failures.append(f"{pf.name}: missing '## Full Inventory' section (run generate-inventory)")
        if ("terraform/modules/" in text or "infrastructure/" in text) and "### Terraform Module Variables/Outputs" not in text:
            failures.append(f"{pf.name}: missing Terraform variables/outputs cross-links (run crosslink-terraform)")
    if failures:
        print("Pillar CI validation failures:\n" + "\n".join(f" - {m}" for m in failures))
        return 2
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Pillar auditor: inventories, terraform cross-links, CI validation")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate-inventory")
    sub.add_parser("crosslink-terraform")
    sub.add_parser("validate-ci")
    sub.add_parser("all")
    args = parser.parse_args(argv)

    if args.cmd == "generate-inventory":
        return generate_inventory()
    if args.cmd == "crosslink-terraform":
        return crosslink_terraform()
    if args.cmd == "validate-ci":
        return validate_ci()
    if args.cmd == "all":
        rc = generate_inventory()
        rc2 = crosslink_terraform()
        rc3 = validate_ci()
        return rc or rc2 or rc3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
