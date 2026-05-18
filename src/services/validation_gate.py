"""
Validation Gate — every write/delete operation by IO requires user approval.

Flow:
1. IO calls propose() → creates a PENDING proposal in the DB
2. User reviews via API/TUI → calls approve() or reject()
3. Gate executes or discards the action

Bypass mode skips the gate entirely (configurable per team/tenant).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sa_text


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ProposalActionType(str, Enum):
    CREATE_TEAM = "create_team"
    UPDATE_TEAM = "update_team"
    DELETE_TEAM = "delete_team"
    ADD_TOOLS = "add_tools"
    REMOVE_TOOLS = "remove_tools"
    ADD_AGENTS = "add_agents"
    REMOVE_AGENTS = "remove_agents"
    UPDATE_INSTRUCTIONS = "update_instructions"
    EXECUTE_TOOL = "execute_tool"


class ValidationGate:
    """
    Stores proposals from IO and requires user approval before execution.
    
    Usage:
        gate = ValidationGate(tenant_id=34)
        pid = await gate.propose("create_team", {"name": "Research Team", ...})
        # User reviews...
        await gate.approve(pid, user_id=16)
    """

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

    async def propose(
        self,
        action_type: str,
        params: Dict[str, Any],
        proposer: str = "io",
        bypass: bool = False,
    ) -> Optional[str]:
        """
        Create a proposal. Returns proposal_id, or None if bypass.
        When bypass=True, immediately executes and returns None (no proposal stored).
        """
        if bypass:
            return None

        from src.database.db import get_db
        proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
        db = get_db()
        try:
            db.execute(
                sa_text("""
                    INSERT INTO proposal
                        (proposal_id, tenant_id, action_type, params, proposer, status, created_at)
                    VALUES
                        (:pid, :tid, :action, :params, :proposer, :status, :now)
                """),
                {
                    "pid": proposal_id,
                    "tid": self.tenant_id,
                    "action": action_type,
                    "params": json.dumps(params),
                    "proposer": proposer,
                    "status": ProposalStatus.PENDING.value,
                    "now": datetime.utcnow(),
                },
            )
            db.commit()
            return proposal_id
        finally:
            db.close()

    async def approve(self, proposal_id: str, user_id: int) -> bool:
        """Approve a proposal and execute the action."""
        from src.database.db import get_db
        db = get_db()
        try:
            row = db.execute(
                sa_text("SELECT action_type, params FROM proposal WHERE proposal_id=:pid AND tenant_id=:tid AND status=:s"),
                {"pid": proposal_id, "tid": self.tenant_id, "s": ProposalStatus.PENDING.value},
            ).fetchone()
            if not row:
                return False

            db.execute(
                sa_text("UPDATE proposal SET status=:s, approved_by=:uid, approved_at=:now WHERE proposal_id=:pid"),
                {"s": ProposalStatus.APPROVED.value, "uid": user_id, "now": datetime.utcnow(), "pid": proposal_id},
            )
            db.commit()
            await self._execute_action(row[0], json.loads(row[1]))
            return True
        finally:
            db.close()

    async def reject(self, proposal_id: str, user_id: int, reason: str = "") -> bool:
        from src.database.db import get_db
        db = get_db()
        try:
            db.execute(
                sa_text("UPDATE proposal SET status=:s, approved_by=:uid, rejection_reason=:reason, approved_at=:now WHERE proposal_id=:pid"),
                {"s": ProposalStatus.REJECTED.value, "uid": user_id, "reason": reason, "now": datetime.utcnow(), "pid": proposal_id},
            )
            db.commit()
            return True
        finally:
            db.close()

    async def list_pending(self) -> List[Dict[str, Any]]:
        from src.database.db import get_db
        db = get_db()
        try:
            rows = db.execute(
                sa_text("SELECT proposal_id, action_type, params, proposer, created_at FROM proposal WHERE tenant_id=:tid AND status=:s ORDER BY created_at ASC"),
                {"tid": self.tenant_id, "s": ProposalStatus.PENDING.value},
            ).fetchall()
            return [
                {
                    "proposal_id": r[0],
                    "action_type": r[1],
                    "params": json.loads(r[2]) if isinstance(r[2], str) else r[2],
                    "proposer": r[3],
                    "created_at": str(r[4]),
                }
                for r in rows
            ]
        finally:
            db.close()

    async def _execute_action(self, action_type: str, params: Dict[str, Any]) -> None:
        """Execute the approved action (delegates to helper methods)."""
        from src.database.db import get_db
        db = get_db()
        try:
            if action_type == "create_team":
                from src.database.models.agent_team import AgentTeam
                team = AgentTeam(
                    agent_team_id=AgentTeam.generate_agent_team_id(),
                    tenant_id=self.tenant_id,
                    name=params.get("name", "New Team"),
                    description=params.get("description", ""),
                    is_active=True,
                )
                tools = params.get("tool_names", [])
                if tools:
                    team.set_pre_approved_tool_names(tools)
                db.add(team)
                db.commit()
            elif action_type == "delete_team":
                team_id = params.get("team_id")
                if team_id:
                    db.execute(sa_text("DELETE FROM agentteam WHERE agent_team_id=:aid AND tenant_id=:tid"),
                               {"aid": team_id, "tid": self.tenant_id})
                    db.commit()
            elif action_type in ("add_tools", "remove_tools"):
                team_id = params.get("team_id")
                tools = params.get("tool_names", [])
                if team_id and tools:
                    from src.database.models.agent_team import AgentTeam
                    team = db.query(AgentTeam).filter(
                        AgentTeam.agent_team_id == team_id,
                        AgentTeam.tenant_id == self.tenant_id,
                    ).first()
                    if team:
                        current = set(team.get_pre_approved_tool_names() or [])
                        if action_type == "add_tools":
                            current.update(tools)
                        else:
                            current.difference_update(tools)
                        team.set_pre_approved_tool_names(list(current))
                        db.commit()
            elif action_type == "update_instructions":
                team_id = params.get("team_id")
                instructions = params.get("system_prompt", "")
                if team_id:
                    from src.database.models.agent_team import AgentTeam
                    team = db.query(AgentTeam).filter(
                        AgentTeam.agent_team_id == team_id,
                        AgentTeam.tenant_id == self.tenant_id,
                    ).first()
                    if team:
                        team.description = instructions[:500] if instructions else team.description
                        db.commit()
        finally:
            db.close()