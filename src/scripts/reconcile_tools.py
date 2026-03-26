import logging
from typing import List

from src.tools.tool_manager import get_tool_manager, ToolStatus
from src.database.db import session_scope
from src.database.models import Tool, CustomAgentDefinition, AgentTeam

logger = logging.getLogger(__name__)

CORE_STABLE = {
    "bigquery_vector_search",
    "orchestrator_research_tool",
    "image_search",
    "ConfirmActionTool",
    "custom_agent_runtime_executor",
    "ui_action_tool",
    "unified_research_tool",
    "exa_search",
}

MCP_PREFIX = "MCP"


def reconcile_tools(dry_run: bool = False, delete_only: bool = False) -> None:
    """
    Reconcile DB Tool rows with the canonical in-memory registry.
    - Seed missing canonical tools
    - Remove legacy tools not present in registry (per user directive)
    - Enforce statuses (core STABLE, MCP BETA by default)
    - Clean agent/team tool lists to only contain registered tools
    """
    tm = get_tool_manager()
    registry_info = tm.get_tool_registry_info()
    registry_names: List[str] = registry_info.get("tool_names", [])

    logger.info("Reconciling tools. Registry has %d tools", len(registry_names))

    with session_scope() as session:
        # 1) Delete legacy tools not in registry (do this first per user directive)
        legacy_tools = (
            session.query(Tool)
            .filter(~Tool.name.in_(registry_names))
            .all()
        )
        if legacy_tools:
            logger.info("Deleting %d legacy tools not in registry", len(legacy_tools))
            if not dry_run:
                for t in legacy_tools:
                    session.delete(t)

        if delete_only:
            # Skip seeding and inserts; proceed to cleanup references and status enforcement
            pass
        else:
            # 2) Seed defaults (idempotent)
            tm.initialize_default_tools()

            # 2b) Ensure every registry tool exists in DB (insert if missing), with description/category
            registry_map = registry_info.get("registry", {})
            existing_names = {t.name for t in session.query(Tool.name).all()}
            for name in registry_names:
                if name in existing_names:
                    continue
                # Determine status/category
                status = ToolStatus.BETA
                if name in CORE_STABLE:
                    status = ToolStatus.STABLE
                if name.startswith(MCP_PREFIX):
                    status = ToolStatus.BETA
                # Insert via ToolManager API to satisfy NOT NULL constraints
                cfg = registry_map.get(name, {}) if isinstance(registry_map, dict) else {}
                description = cfg.get("description") or f"{name} tool"
                category = cfg.get("category")
                logger.info("Inserting missing tool from registry: %s [%s]", name, status)
                if not dry_run:
                    tm.register_tool_in_database(
                        name=name,
                        description=description,
                        status=status,
                        category=category,
                    )

        # 3) Enforce statuses
        tools = session.query(Tool).all()
        for t in tools:
            desired = t.status
            if t.name in CORE_STABLE:
                desired = ToolStatus.STABLE
            elif t.name.startswith(MCP_PREFIX):
                # Globally available but keep BETA flag per alignment doc
                desired = ToolStatus.BETA
            # else: keep existing status
            if t.status != desired:
                logger.info("Setting status %s -> %s for %s", t.status, desired, t.name)
                if not dry_run:
                    t.status = desired
                    t.update_timestamp()

        # 4) Clean-up agent tool references (use model helpers to handle JSON correctly)
        agents = session.query(CustomAgentDefinition).all()
        for a in agents:
            # Ensure tool_names is a list, not a JSON string's character list
            try:
                original = a.get_tool_names()  # type: ignore[attr-defined]
            except Exception:
                # Fallback: parse JSON manually if helper not available
                import json as _json
                try:
                    original = _json.loads(a.tool_names) if a.tool_names else []  # type: ignore[attr-defined]
                except Exception:
                    original = []
            cleaned = [n for n in (original or []) if n in registry_names]
            if cleaned != original:
                logger.info("Agent %s: cleaned tools %s -> %s", a.custom_agent_id, original, cleaned)
                if not dry_run:
                    try:
                        a.set_tool_names(cleaned)  # type: ignore[attr-defined]
                    except Exception:
                        import json as _json
                        a.tool_names = _json.dumps(cleaned)  # type: ignore[attr-defined]

        # 5) Clean-up team pre-approved tool references (use model helpers)
        teams = session.query(AgentTeam).all()
        for team in teams:
            try:
                original = team.get_pre_approved_tool_names()  # type: ignore[attr-defined]
            except Exception:
                import json as _json
                try:
                    original = _json.loads(team.pre_approved_tool_names) if team.pre_approved_tool_names else []  # type: ignore[attr-defined]
                except Exception:
                    original = []
            cleaned = [n for n in (original or []) if n in registry_names]
            if cleaned != original:
                logger.info("Team %s: cleaned pre-approved tools %s -> %s", team.agent_team_id, original, cleaned)
                if not dry_run:
                    try:
                        team.set_pre_approved_tool_names(cleaned)  # type: ignore[attr-defined]
                    except Exception:
                        import json as _json
                        team.pre_approved_tool_names = _json.dumps(cleaned)  # type: ignore[attr-defined]

        if not dry_run:
            session.commit()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Reconcile Tool registry with DB")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument("--delete-only", action="store_true", help="Only delete legacy tools and clean references; skip inserts")
    args = parser.parse_args()

    reconcile_tools(dry_run=args.dry_run, delete_only=args.delete_only)
