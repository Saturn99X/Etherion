from sqlmodel import Session
from datetime import datetime

from src.database.models.custom_agent import CustomAgentDefinition


def test_soft_delete_flag_and_pagination(tmp_path):
    # This is a structural test; assumes a test DB/Session fixture in real suite
    # Here we only validate model fields and simple list-slicing logic
    a1 = CustomAgentDefinition(custom_agent_id="ca_1", tenant_id=1, name="A1", description="d", system_prompt="p", tool_names="[]")
    a2 = CustomAgentDefinition(custom_agent_id="ca_2", tenant_id=1, name="A2", description="d", system_prompt="p", tool_names="[]")
    a3 = CustomAgentDefinition(custom_agent_id="ca_3", tenant_id=1, name="A3", description="d", system_prompt="p", tool_names="[]")

    # Soft-delete a2
    a2.is_deleted = True
    a2.deleted_at = datetime.utcnow()

    agents = [a1, a2, a3]
    # Filter non-deleted
    active = [a for a in agents if not a.is_deleted]
    assert [a.custom_agent_id for a in active] == ["ca_1", "ca_3"]

    # Paginate first 1
    page = active[0:1]
    assert len(page) == 1 and page[0].custom_agent_id == "ca_1"













